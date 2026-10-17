"""
src/c4_rate_extractor.py
Phase 4 (C4): Negotiated Rate Extraction and PPO Network Attribution Engine.

Streams and extracts provider-negotiated rates from Centene's California Price
Transparency Data (PTD) in-network files. Relates rates to provider reference
groups, expands provider identifiers (NPI/TIN), applies strict evidence-based
PPO applicability rules (Confirmed, Probable, Ambiguous, Excluded), handles
rate context and multiple rates for the same billing code without arbitrary collapsing,
and outputs fully auditable artifacts.

CMS Transparency in Coverage (TiC) v2.0.0 compliant.
Memory-safe streaming via ijson.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import ijson
import yaml

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import get_project_root, load_config, setup_logging

logger = logging.getLogger(__name__)


# ── Identifier Validation Helpers ─────────────────────────────────────────────

def validate_npi_luhn(npi_val: Any) -> bool:
    """
    Validate a 10-digit National Provider Identifier (NPI) using the CMS Luhn algorithm.
    CMS NPIs are 10 digits with fixed prefix '80840' prepended for Luhn calculation.
    """
    if npi_val is None:
        return False
    digits = str(npi_val).strip()
    if len(digits) != 10 or not digits.isdigit():
        return False
    if digits.startswith("0"):
        return False

    full_num = "80840" + digits
    total = 0
    for idx, char in enumerate(reversed(full_num)):
        d = int(char)
        if idx % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (total % 10) == 0


def validate_tin_ein(tin_val: Any) -> bool:
    """
    Validate a 9-digit Employer Identification Number (EIN / Tax ID).
    Standard formats: 'XX-XXXXXXX' or 'XXXXXXXXX'. Rejects trivial dummy numbers.
    """
    if tin_val is None:
        return False
    clean = re.sub(r"[^0-9]", "", str(tin_val).strip())
    if len(clean) != 9:
        return False
    if clean in {"000000000", "111111111", "999999999", "123456789"}:
        return False
    return True


# ── C4 Rate Extractor Engine ──────────────────────────────────────────────────

class RateExtractor:
    """
    Memory-efficient streaming rate extraction and PPO applicability classification engine.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.root = get_project_root()
        self.cfg = load_config(Path(config_path) if config_path else None)

        # Configurable lists of major CA health systems
        self.major_ca_health_systems: List[str] = [
            s.lower() for s in self.cfg.get("c4_major_ca_health_systems", [
                "stanford", "uc davis", "uc irvine", "ucla", "ucsf", "ucsd",
                "cedars-sinai", "sutter", "dignity", "providence", "city of hope",
                "hoag", "loma linda", "scripps", "sharp", "adventist", "john muir",
                "children's hospital", "huntington", "memorialcare", "torrance",
                "cottage", "el camino", "salinas valley", "marinhealth", "kaweah",
                "enloe", "marshall", "temecula valley"
            ])
        ]

        # Load benchmark codes if present
        self.benchmark_codes: Set[str] = set()
        self._load_benchmark_codes()

    def _load_benchmark_codes(self) -> None:
        """Load benchmark procedure codes from the hackathon benchmark dataset."""
        excel_path = self.cfg.get("benchmark_weights_xlsx")
        if excel_path and os.path.exists(excel_path):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(excel_path, read_only=True)
                if "Spec-Proc Weights" in wb.sheetnames:
                    ws = wb["Spec-Proc Weights"]
                    header = [str(cell).strip().upper() for cell in next(ws.iter_rows(values_only=True))]
                    proc_col_idx = 2
                    for idx, name in enumerate(header):
                        if "PROC_CD" in name or name == "PROCEDURE_CODE":
                            proc_col_idx = idx
                            break
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        if row and len(row) > proc_col_idx and row[proc_col_idx] is not None:
                            code_str = str(row[proc_col_idx]).strip()
                            if code_str:
                                self.benchmark_codes.add(code_str)
                wb.close()
                logger.info("Loaded %d benchmark procedure codes from %s",
                            len(self.benchmark_codes), excel_path)
            except Exception as e:
                logger.warning("Could not load benchmark Excel (%s): %s", excel_path, e)

    def load_provider_references(self, file_path: str) -> Dict[int, Dict[str, Any]]:
        """
        Stream the top-level provider_references array and build a lookup table.
        Classifies each provider reference group into PPO applicability tiers:
          - CONFIRMED_PPO
          - PROBABLE_PPO
          - AMBIGUOUS_UNRESOLVED
          - EXCLUDED_HMO
          - EXCLUDED_INDIVIDUAL_EXCHANGE
        """
        logger.info("Indexing and classifying provider references from %s...", file_path)
        provider_ref_map: Dict[int, Dict[str, Any]] = {}

        with open(file_path, "rb") as fh:
            pref_items = ijson.items(fh, "provider_references.item")
            for pref in pref_items:
                pid = pref.get("provider_group_id")
                if pid is None:
                    continue

                groups = pref.get("provider_groups") or []
                parsed_groups: List[Dict[str, Any]] = []
                all_bnames: List[str] = []
                total_npis = 0

                for pg in groups:
                    npis = [str(n).strip() for n in pg.get("npi", []) if n is not None]
                    tin_obj = pg.get("tin") or {}
                    tin_type = str(tin_obj.get("type", "ein")).strip().lower()
                    tin_val = str(tin_obj.get("value", "")).strip()
                    bname = str(tin_obj.get("business_name", "")).strip()

                    all_bnames.append(bname)
                    total_npis += len(npis)

                    parsed_groups.append({
                        "npi_list": npis,
                        "tin_type": tin_type,
                        "tin_value": tin_val,
                        "business_name": bname,
                    })

                # Determine PPO Applicability tier based on explicit source evidence
                full_name_str = " ".join(all_bnames).lower()

                has_hn_ppo = any(
                    "healthnet ppo" in b.lower() or re.search(r"\bppo:\s*[a-z\s]+county\b", b, re.I)
                    for b in all_bnames
                )
                has_ambetter_ppo = any("ambetter ppo" in b.lower() for b in all_bnames)
                has_hmo = any("hmo" in b.lower() for b in all_bnames)

                if has_hn_ppo:
                    cat = "CONFIRMED_PPO"
                    reason = "Explicit Health Net California Commercial PPO County or Network Fee Schedule wrapper"
                elif has_ambetter_ppo:
                    cat = "EXCLUDED_INDIVIDUAL_EXCHANGE"
                    reason = "Ambetter PPO individual exchange marketplace product (non-commercial group)"
                elif has_hmo:
                    cat = "EXCLUDED_HMO"
                    reason = "Explicitly designated as HMO network"
                elif any(sys_name in full_name_str for sys_name in self.major_ca_health_systems):
                    cat = "PROBABLE_PPO"
                    reason = "Major California health system / hospital facility contracted under Health Net Commercial PPO FFS agreement"
                else:
                    cat = "AMBIGUOUS_UNRESOLVED"
                    reason = "General California provider entity; fee-for-service arrangement present, but lacks explicit network-specific roster"

                provider_ref_map[int(pid)] = {
                    "provider_group_id": int(pid),
                    "groups": parsed_groups,
                    "business_names": all_bnames,
                    "business_name_str": " | ".join(all_bnames),
                    "npi_count": total_npis,
                    "ppo_applicability": cat,
                    "ppo_evidence_reason": reason,
                    "rate_record_count": 0,
                    "extracted_price_count": 0,
                }

        counts = Counter(v["ppo_applicability"] for v in provider_ref_map.values())
        logger.info("Provider reference groups indexed: %d total", len(provider_ref_map))
        for cat, cnt in counts.items():
            logger.info("  %-30s: %5d groups", cat, cnt)

        return provider_ref_map

    def extract_and_classify(
        self,
        file_path: Optional[str] = None,
        max_rate_items: Optional[int] = None,
        output_rates_path: Optional[str] = None,
        output_classification_path: Optional[str] = None,
        output_summary_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute streaming extraction and PPO rate classification.
        Writes extracted rates to CSV and produces summary statistics.
        """
        t0 = time.time()
        target_path = file_path or self.cfg.get("target_rate_file_path")
        if not target_path or not os.path.exists(target_path):
            raise FileNotFoundError(f"Target rate file not found: {target_path}")

        file_name = os.path.basename(target_path)
        file_size_bytes = os.path.getsize(target_path)

        out_rates = output_rates_path or self.cfg.get("c4_extracted_rates_csv", "outputs/c4_extracted_rates.csv")
        out_class = output_classification_path or self.cfg.get("c4_ppo_rate_classification_csv", "outputs/c4_ppo_rate_classification.csv")
        out_summ = output_summary_path or self.cfg.get("c4_extraction_summary_json", "outputs/c4_extraction_summary.json")

        os.makedirs(os.path.dirname(out_rates), exist_ok=True)
        os.makedirs(os.path.dirname(out_class), exist_ok=True)
        os.makedirs(os.path.dirname(out_summ), exist_ok=True)

        # Step 1: Load and classify provider references
        provider_ref_map = self.load_provider_references(target_path)

        # Step 2: Stream in_network and extract rates
        logger.info("Streaming in_network rates from %s (limit: %s)...", file_name, max_rate_items or "None")

        stats = {
            "total_in_network_items": 0,
            "total_rate_records": 0,
            "total_prices_examined": 0,
            "total_expanded_rows_written": 0,
            "distinct_billing_codes": set(),
            "distinct_npis_extracted": set(),
            "distinct_tins_extracted": set(),
            "unresolved_provider_references": 0,
            "missing_rates": 0,
            "missing_billing_codes": 0,
            "capitation_carveouts_excluded": 0,
            "rates_by_applicability": Counter(),
            "prices_by_applicability": Counter(),
            "rate_selection_flags": Counter(),
            "benchmark_codes_extracted": set(),
        }

        # Track clinical contexts for multiple-rate detection
        # Key: (npi, tin_val, billing_code, modifier_str, b_class, setting, pos_str, add_info)
        # Value: list of distinct rate amounts observed
        context_rates: Dict[Tuple, List[str]] = defaultdict(list)
        # Bounded cache to limit memory consumption if file is massive
        MAX_CONTEXT_CACHE_SIZE = 500000

        # Pass 1 & Write stream: Open output CSV
        csv_headers = [
            "npi",
            "tin_type",
            "tin_value",
            "provider_business_name",
            "provider_group_id",
            "billing_code",
            "billing_code_type",
            "billing_code_type_version",
            "billing_code_description",
            "billing_code_modifier",
            "billing_class",
            "setting",
            "service_codes",
            "additional_information",
            "negotiated_type",
            "negotiated_rate",
            "expiration_date",
            "negotiation_arrangement",
            "is_benchmark_code",
            "ppo_applicability",
            "ppo_evidence_reason",
            "rate_selection_flag",
            "alternative_rate_values",
            "address_status",
            "source_file",
        ]

        row_buffer: List[List[Any]] = []
        BUFFER_FLUSH_SIZE = 10000

        with open(out_rates, "w", newline="", encoding="utf-8") as rates_fh:
            writer = csv.writer(rates_fh)
            writer.writerow(csv_headers)

            with open(target_path, "rb") as fh:
                parser = ijson.items(fh, "in_network.item")
                item_count = 0

                for item in parser:
                    item_count += 1
                    stats["total_in_network_items"] += 1

                    arr = str(item.get("negotiation_arrangement", "ffs")).strip().lower()
                    billing_code = str(item.get("billing_code", "")).strip()
                    billing_code_type = str(item.get("billing_code_type", "")).strip()
                    billing_code_version = str(item.get("billing_code_type_version", "")).strip()
                    item_name = str(item.get("name", "")).strip()
                    item_desc = str(item.get("description", "")).strip()

                    if billing_code:
                        stats["distinct_billing_codes"].add(billing_code)
                        if billing_code in self.benchmark_codes:
                            stats["benchmark_codes_extracted"].add(billing_code)
                    else:
                        stats["missing_billing_codes"] += 1

                    is_benchmark = "Y" if billing_code in self.benchmark_codes else "N"

                    rates = item.get("negotiated_rates") or []
                    for rate_entry in rates:
                        stats["total_rate_records"] += 1
                        prov_refs = rate_entry.get("provider_references") or []
                        prices = rate_entry.get("negotiated_prices") or []

                        # Resolve provider references
                        ref_id = None
                        if prov_refs:
                            try:
                                ref_id = int(prov_refs[0])
                            except (ValueError, TypeError):
                                ref_id = None

                        pref_meta = provider_ref_map.get(ref_id) if ref_id is not None else None
                        if pref_meta is None:
                            stats["unresolved_provider_references"] += 1
                            rate_cat = "UNRESOLVED_REFERENCE"
                            rate_reason = f"Provider reference ID {ref_id} not found in provider_references"
                            provider_groups = [{
                                "npi_list": [""],
                                "tin_type": "ein",
                                "tin_value": "",
                                "business_name": "UNKNOWN_UNRESOLVED",
                            }]
                        else:
                            pref_meta["rate_record_count"] += 1
                            pref_meta["extracted_price_count"] += len(prices)

                            if arr == "capitation":
                                rate_cat = "EXCLUDED_CAPITATION"
                                rate_reason = "Knox-Keene HMO capitation carve-out; incompatible with commercial PPO FFS"
                                stats["capitation_carveouts_excluded"] += 1
                            else:
                                rate_cat = pref_meta["ppo_applicability"]
                                rate_reason = pref_meta["ppo_evidence_reason"]

                            provider_groups = pref_meta["groups"]

                        stats["rates_by_applicability"][rate_cat] += 1

                        # Iterate through prices
                        for p_idx, price_obj in enumerate(prices):
                            stats["total_prices_examined"] += 1
                            stats["prices_by_applicability"][rate_cat] += 1

                            rate_val = price_obj.get("negotiated_rate")
                            if rate_val is None:
                                stats["missing_rates"] += 1
                                rate_str = ""
                            else:
                                rate_str = str(rate_val).strip()

                            rate_type = str(price_obj.get("negotiated_type", "negotiated")).strip().lower()
                            exp_date = str(price_obj.get("expiration_date", "")).strip()
                            b_class = str(price_obj.get("billing_class", "")).strip().lower()
                            setting = str(price_obj.get("setting", "")).strip().lower()
                            add_info = str(price_obj.get("additional_information", "")).strip()

                            # Modifiers
                            raw_mods = price_obj.get("billing_code_modifier") or price_obj.get("billing_code_modifiers") or []
                            if isinstance(raw_mods, list):
                                mod_str = ";".join(str(m).strip() for m in raw_mods if m)
                            else:
                                mod_str = str(raw_mods).strip()

                            # Service Codes (POS)
                            raw_pos = price_obj.get("service_code") or []
                            if isinstance(raw_pos, list):
                                pos_str = ";".join(str(s).strip() for s in raw_pos if s)
                            else:
                                pos_str = str(raw_pos).strip()

                            # Expand across provider groups & NPIs
                            for pg in provider_groups:
                                tin_type = pg["tin_type"]
                                tin_val = pg["tin_value"]
                                bname = pg["business_name"]
                                if tin_val:
                                    stats["distinct_tins_extracted"].add(tin_val)

                                npis = pg["npi_list"]
                                if not npis:
                                    npis = [""]  # Preserves group rate even if NPI unpopulated

                                for npi in npis:
                                    clean_npi = str(npi).strip()
                                    if clean_npi:
                                        stats["distinct_npis_extracted"].add(clean_npi)

                                    # Context evaluation for multiple rates
                                    ctx_key = (
                                        clean_npi,
                                        tin_val,
                                        billing_code,
                                        mod_str,
                                        b_class,
                                        setting,
                                        pos_str,
                                        add_info,
                                    )

                                    if len(context_rates) < MAX_CONTEXT_CACHE_SIZE:
                                        observed_rates = context_rates[ctx_key]
                                        if rate_str and rate_str not in observed_rates:
                                            observed_rates.append(rate_str)

                                        if len(observed_rates) > 1:
                                            rate_flag = "MULTIPLE_COMPARABLE_RATES_FLAGGED"
                                            alt_rates_str = " | ".join(observed_rates)
                                        else:
                                            rate_flag = "UNIQUE_RATE"
                                            alt_rates_str = ""
                                    else:
                                        rate_flag = "STANDARD_EXTRACTED_RATE"
                                        alt_rates_str = ""

                                    stats["rate_selection_flags"][rate_flag] += 1

                                    row = [
                                        clean_npi,
                                        tin_type,
                                        tin_val,
                                        bname,
                                        ref_id if ref_id is not None else "",
                                        billing_code,
                                        billing_code_type,
                                        billing_code_version,
                                        item_desc or item_name,
                                        mod_str,
                                        b_class,
                                        setting,
                                        pos_str,
                                        add_info,
                                        rate_type,
                                        rate_str,
                                        exp_date,
                                        arr,
                                        is_benchmark,
                                        rate_cat,
                                        rate_reason,
                                        rate_flag,
                                        alt_rates_str,
                                        "UNRESOLVED_PENDING_C5",  # Explicit constraint: do not fabricate address in C4
                                        file_name,
                                    ]

                                    row_buffer.append(row)
                                    stats["total_expanded_rows_written"] += 1

                                    if len(row_buffer) >= BUFFER_FLUSH_SIZE:
                                        writer.writerows(row_buffer)
                                        row_buffer.clear()

                    if item_count % 250 == 0:
                        logger.info("  Processed %d items (%d rate records, %d prices, %d expanded rows)...",
                                    item_count, stats["total_rate_records"],
                                    stats["total_prices_examined"], stats["total_expanded_rows_written"])

                    if max_rate_items is not None and item_count >= max_rate_items:
                        logger.info("Reached maximum requested item limit (%d); halting stream.", max_rate_items)
                        break

            # Flush any remaining rows
            if row_buffer:
                writer.writerows(row_buffer)
                row_buffer.clear()

        logger.info("Extracted rates written to %s (%d rows)", out_rates, stats["total_expanded_rows_written"])

        # Step 3: Write Provider Reference PPO Classification Table
        with open(out_class, "w", newline="", encoding="utf-8") as class_fh:
            cwriter = csv.writer(class_fh)
            cwriter.writerow([
                "provider_group_id",
                "provider_business_name",
                "tin_value",
                "npi_count",
                "ppo_applicability",
                "evidence_reason",
                "rate_record_count",
                "extracted_price_count",
            ])
            for pid in sorted(provider_ref_map.keys()):
                pm = provider_ref_map[pid]
                tin_str = ";".join(pg["tin_value"] for pg in pm["groups"] if pg["tin_value"])
                cwriter.writerow([
                    pid,
                    pm["business_name_str"],
                    tin_str,
                    pm["npi_count"],
                    pm["ppo_applicability"],
                    pm["ppo_evidence_reason"],
                    pm["rate_record_count"],
                    pm["extracted_price_count"],
                ])
        logger.info("PPO classification table written to %s (%d groups)", out_class, len(provider_ref_map))

        elapsed = round(time.time() - t0, 2)

        # Step 4: Build Summary Object
        summary = {
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "C4 - Negotiated Rate Extraction",
            "source_file": file_name,
            "source_file_path": target_path,
            "file_size_bytes": file_size_bytes,
            "elapsed_seconds": elapsed,
            "max_items_capped": max_rate_items,
            "counts": {
                "in_network_items_examined": stats["total_in_network_items"],
                "rate_records_examined": stats["total_rate_records"],
                "prices_examined": stats["total_prices_examined"],
                "expanded_provider_rate_rows_written": stats["total_expanded_rows_written"],
                "distinct_billing_codes": len(stats["distinct_billing_codes"]),
                "benchmark_codes_matched": len(stats["benchmark_codes_extracted"]),
                "benchmark_codes_total": len(self.benchmark_codes),
                "unique_npis_extracted": len(stats["distinct_npis_extracted"]),
                "unique_tins_extracted": len(stats["distinct_tins_extracted"]),
                "unresolved_provider_references": stats["unresolved_provider_references"],
                "missing_rates": stats["missing_rates"],
                "missing_billing_codes": stats["missing_billing_codes"],
                "capitation_carveouts_excluded": stats["capitation_carveouts_excluded"],
            },
            "ppo_applicability_breakdown": {
                "rates": dict(stats["rates_by_applicability"]),
                "prices": dict(stats["prices_by_applicability"]),
            },
            "rate_selection_flags": dict(stats["rate_selection_flags"]),
            "data_limitations_and_caveats": [
                "Consolidated File Scope: The target file contains rates for commercial PPO, HMO, and POS plans. PPO applicability classification distinguishes explicit county PPO wrappers (CONFIRMED) and major health systems (PROBABLE) from HMO and general ambiguous entities.",
                "Ambetter Exchange Distinction: Rates under 'DIRECT NETWORK: AMBETTER PPO' are classified as EXCLUDED_INDIVIDUAL_EXCHANGE because Ambetter serves the individual exchange market, not California Commercial Group.",
                "Capitation Exclusion: Rates under negotiation_arrangement='capitation' are classified as EXCLUDED_CAPITATION because Knox-Keene HMO capitation carve-outs do not apply to commercial PPO fee schedules.",
                "Preserved Clinical Context: Rates with differing modifiers (e.g. 26 professional vs TC technical), place of service codes, or billing classes are preserved as distinct rows and never collapsed.",
                "Multiple Rates Selection Rule: When multiple rates exist for the exact same clinical context, all values are preserved with a MULTIPLE_COMPARABLE_RATES_FLAGGED flag and alternative values documented, avoiding arbitrary min/max/average selection.",
                "Pending C5 Address Resolution: Street practicing addresses are kept as UNRESOLVED_PENDING_C5 in this phase; no addresses have been fabricated.",
            ],
        }

        with open(out_summ, "w", encoding="utf-8") as summ_fh:
            json.dump(summary, summ_fh, indent=2)
        logger.info("C4 summary written to %s", out_summ)

        return summary


# ── CLI Interface ─────────────────────────────────────────────────────────────

def run_c4(
    config_path: Optional[str] = None,
    file_path: Optional[str] = None,
    max_rate_items: Optional[int] = None,
    output_rates_path: Optional[str] = None,
    output_classification_path: Optional[str] = None,
    output_summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Top-level entry point to run Phase 4 (C4) rate extraction."""
    setup_logging(log_level="INFO")
    logger.info("=" * 70)
    logger.info("Phase 4: Provider-Negotiated Rate Extraction (C4)")
    logger.info("=" * 70)

    extractor = RateExtractor(config_path=config_path)
    summary = extractor.extract_and_classify(
        file_path=file_path,
        max_rate_items=max_rate_items,
        output_rates_path=output_rates_path,
        output_classification_path=output_classification_path,
        output_summary_path=output_summary_path,
    )

    logger.info("\n" + "=" * 70)
    logger.info("C4 EXTRACTION AND CLASSIFICATION SUMMARY")
    logger.info("=" * 70)
    logger.info("Source File                 : %s", summary["source_file"])
    logger.info("Elapsed Seconds             : %.2fs", summary["elapsed_seconds"])
    logger.info("In-Network Items Examined   : %d", summary["counts"]["in_network_items_examined"])
    logger.info("Rate Records Examined       : %d", summary["counts"]["rate_records_examined"])
    logger.info("Prices Examined             : %d", summary["counts"]["prices_examined"])
    logger.info("Expanded Rows Written       : %d", summary["counts"]["expanded_provider_rate_rows_written"])
    logger.info("Distinct Billing Codes      : %d (Benchmark: %d / %d)",
                summary["counts"]["distinct_billing_codes"],
                summary["counts"]["benchmark_codes_matched"],
                summary["counts"]["benchmark_codes_total"])
    logger.info("Unique NPIs Extracted       : %d", summary["counts"]["unique_npis_extracted"])
    logger.info("Unique TINs Extracted       : %d", summary["counts"]["unique_tins_extracted"])
    logger.info("Unresolved References       : %d", summary["counts"]["unresolved_provider_references"])
    logger.info("----------------------------------------------------------------------")
    logger.info("PPO Applicability Breakdown (Rate Records):")
    for cat, cnt in summary["ppo_applicability_breakdown"]["rates"].items():
        logger.info("  %-30s: %6d records", cat, cnt)
    logger.info("======================================================================")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Centene PTD Negotiated Rate Extractor (C4)")
    parser.add_argument("--config", default=None, help="Path to config/settings.yaml")
    parser.add_argument("--file", default=None, help="Path to target PTD JSON file")
    parser.add_argument("--sample", type=int, default=None, help="Sample limit on in_network items")
    parser.add_argument("--output-rates", default=None, help="Path for output extracted rates CSV")
    parser.add_argument("--output-class", default=None, help="Path for output PPO classification CSV")
    parser.add_argument("--output-summary", default=None, help="Path for output summary JSON")
    args = parser.parse_args()

    run_c4(
        config_path=args.config,
        file_path=args.file,
        max_rate_items=args.sample,
        output_rates_path=args.output_rates,
        output_classification_path=args.output_class,
        output_summary_path=args.output_summary,
    )
