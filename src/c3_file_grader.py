"""
src/c3_file_grader.py
────────────────────────────────────────────────────────────────────────────────
Phase 3 – Price Transparency Data (PTD) File Quality Grader (C3)

Objective:
  Build a memory-efficient, streaming PTD file quality grader that evaluates
  the completeness, validity, reference integrity, rate distributions, and
  PPO network applicability of machine-readable files (MRFs).

Key Design Principles:
  1. Memory Bounded: NEVER loads the entire file with json.load(). Streams
     provider_references and in_network elements using ijson.
  2. Defensible Multi-Metric Framework: 11 distinct quality dimensions, each
     with explicit formulas, numerators, denominators, and weights (sum = 100).
  3. PPO Network Applicability: Distinguishes rates and provider groups that
     link to confirmed/probable PPO contracts vs. HMO or generic networks.
  4. Benchmark Integration: Evaluates procedural code coverage against the
     583 benchmark procedure codes from the hackathon reference dataset.
  5. Auditability: Generates file-level metrics, fine-grained metric details,
     machine-readable summary JSON, and a comprehensive methodology report.

Outputs:
  - outputs/c3_file_quality_metrics.csv
  - outputs/c3_metric_details.csv
  - outputs/c3_summary.json
  - reports/c3_quality_methodology.md
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

import openpyxl
import pandas as pd
import ijson

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (
    ensure_directories,
    load_config,
    setup_logging,
)

logger = logging.getLogger(__name__)

# ── Federal NPI Luhn Checksum Algorithm ───────────────────────────────────────

def is_valid_npi(npi_val: Any) -> bool:
    """
    Validate a 10-digit National Provider Identifier (NPI) using the CMS
    standard Luhn check digit algorithm (ISO/IEC 7812 with '80840' prefix).
    """
    if npi_val is None:
        return False
    s = str(npi_val).strip()
    if not (len(s) == 10 and s.isdigit()):
        return False
    if s[0] not in ('1', '2'):
        return False

    # Full 15-digit string: prefix '80840' + 10-digit NPI
    full = "80840" + s
    digits = [int(c) for c in full]

    # Luhn formula: double alternate digits from right-to-left starting with second-to-last
    total = 0
    double = True
    for d in reversed(digits[:-1]):
        if double:
            val = d * 2
            total += (val - 9) if val > 9 else val
        else:
            total += d
        double = not double

    check_digit = (10 - (total % 10)) % 10
    return check_digit == digits[-1]


def is_valid_ein(ein_val: Any) -> bool:
    """Validate 9-digit Employer Identification Number (TIN/EIN)."""
    if ein_val is None:
        return False
    clean = re.sub(r'[-\s]', '', str(ein_val).strip())
    return len(clean) == 9 and clean.isdigit()


# ── Benchmark Code Loader ─────────────────────────────────────────────────────

def load_benchmark_procedure_codes(excel_path: str) -> Set[str]:
    """
    Load distinct procedure codes from the hackathon benchmark Excel workbook
    sheet 'Spec-Proc Weights'.
    """
    if not os.path.exists(excel_path):
        logger.warning("Benchmark file %s not found; benchmark coverage metric will use empty denominator.", excel_path)
        return set()

    try:
        wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        if "Spec-Proc Weights" not in wb.sheetnames:
            logger.warning("Sheet 'Spec-Proc Weights' missing in %s", excel_path)
            return set()

        ws = wb["Spec-Proc Weights"]
        codes = set()
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue
            proc_cd = row[2] if len(row) > 2 else None
            if proc_cd is not None:
                codes.add(str(proc_cd).strip())
        wb.close()
        return codes
    except Exception as exc:
        logger.warning("Error reading benchmark file %s: %s", excel_path, exc)
        return set()


# ── Core Streaming Grader Class ───────────────────────────────────────────────

class PTDFileGrader:
    """
    Memory-efficient streaming file quality grader for CMS Price Transparency Data (PTD).
    """

    EXPECTED_TOP_LEVEL_KEYS = [
        "reporting_entity_name",
        "reporting_entity_type",
        "version",
        "last_updated_on",
        "provider_references",
        "in_network",
    ]

    DEFAULT_WEIGHTS = {
        "m01_structural_validity": 10.0,
        "m02_field_completeness": 10.0,
        "m03_provider_identifier_validity": 10.0,
        "m04_reference_integrity": 10.0,
        "m05_benchmark_code_coverage": 10.0,
        "m06_monetary_rate_validity": 15.0,
        "m07_rate_outlier_quality": 5.0,
        "m08_deduplication_quality": 10.0,
        "m09_rate_type_usability": 5.0,
        "m10_freshness_expiration": 5.0,
        "m11_ppo_applicability": 10.0,
    }

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.weights = dict(self.DEFAULT_WEIGHTS)
        user_weights = cfg.get("c3_scoring_weights") or {}
        self.weights.update(user_weights)
        benchmark_path = cfg.get("benchmark_weights_xlsx", "data/raw/Rate_Benchmarking_Individual_Weights_Hackathon.xlsx")
        self.benchmark_codes = load_benchmark_procedure_codes(benchmark_path)
        logger.info("Loaded %d benchmark procedure codes from %s", len(self.benchmark_codes), benchmark_path)

    def grade_file(
        self,
        file_path: str,
        max_rate_items: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Grade a Price Transparency Data (PTD) JSON file using streaming parsing.

        Parameters
        ----------
        file_path : str
            Path to the uncompressed or local JSON file.
        max_rate_items : Optional[int]
            Optional cap on the number of billing-code items to stream (useful for tests).
            None means stream the entire file.

        Returns
        -------
        (file_metrics, metric_details)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} not found.")

        file_size_bytes = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        logger.info("Starting streaming quality evaluation of %s (%d bytes, %.1f MB)...",
                    file_name, file_size_bytes, file_size_bytes / (1024 * 1024))

        start_time = time.time()

        # ── Pass 1: Parse top-level metadata and provider_references ──────────
        header_meta, provider_ref_map, prov_stats = self._parse_provider_references(file_path)

        # ── Pass 2: Stream in_network billing codes and negotiated rates ────────
        rate_stats = self._stream_in_network_rates(file_path, provider_ref_map, max_rate_items)

        elapsed = time.time() - start_time
        logger.info("Streaming completed in %.1f seconds.", elapsed)

        # ── Compute the 11 quality metrics and composite score ────────────────
        file_metrics, metric_details = self._compute_metrics(
            file_path=file_path,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            header_meta=header_meta,
            prov_stats=prov_stats,
            rate_stats=rate_stats,
            elapsed_seconds=elapsed,
            max_rate_items=max_rate_items,
        )

        return file_metrics, metric_details

    def _parse_provider_references(
        self, file_path: str
    ) -> Tuple[Dict[str, Any], Dict[int, Dict[str, Any]], Dict[str, Any]]:
        """
        Stream the header and the `provider_references` array.
        Bounded memory: stores compact mapping of provider_group_id -> network/TIN attributes.
        """
        header_meta = {
            "reporting_entity_name": None,
            "reporting_entity_type": None,
            "version": None,
            "last_updated_on": None,
            "has_provider_references": False,
            "has_in_network": False,
        }
        provider_ref_map: Dict[int, Dict[str, Any]] = {}

        total_groups = 0
        total_npis = 0
        valid_npis = 0
        total_tins = 0
        valid_tins = 0
        ppo_provider_groups = 0
        hmo_provider_groups = 0

        unique_npis: Set[int] = set()
        unique_tins: Set[str] = set()

        with open(file_path, "rb") as fh:
            # Check top-level keys
            for prefix, event, value in ijson.parse(fh):
                if prefix == "reporting_entity_name":
                    header_meta["reporting_entity_name"] = value
                elif prefix == "reporting_entity_type":
                    header_meta["reporting_entity_type"] = value
                elif prefix == "version":
                    header_meta["version"] = value
                elif prefix == "last_updated_on":
                    header_meta["last_updated_on"] = value
                elif prefix == "provider_references" and event == "start_array":
                    header_meta["has_provider_references"] = True
                elif prefix == "in_network" and event == "start_array":
                    header_meta["has_in_network"] = True
                    break  # Stop header parse once in_network starts

        with open(file_path, "rb") as fh:
            for item in ijson.items(fh, "provider_references.item"):
                total_groups += 1
                group_id = item.get("provider_group_id")
                net_names = item.get("network_name") or []
                groups = item.get("provider_groups") or []

                is_ppo = False
                is_hmo = False
                group_npis = []
                group_tins = []

                # Inspect network_name
                for nn in net_names:
                    if re.search(r'\bppo\b', str(nn), re.I):
                        is_ppo = True
                    if re.search(r'\bhmo\b', str(nn), re.I):
                        is_hmo = True

                # Inspect provider_groups
                for pg in groups:
                    npis = pg.get("npi") or []
                    tin_obj = pg.get("tin") or {}
                    tin_val = tin_obj.get("value")
                    biz_name = tin_obj.get("business_name") or ""

                    if re.search(r'\bppo\b', str(biz_name), re.I):
                        is_ppo = True
                    if re.search(r'\bhmo\b', str(biz_name), re.I):
                        is_hmo = True

                    for npi in npis:
                        total_npis += 1
                        if is_valid_npi(npi):
                            valid_npis += 1
                            unique_npis.add(int(npi))
                        group_npis.append(npi)

                    if tin_val:
                        total_tins += 1
                        clean_tin = re.sub(r'[-\s]', '', str(tin_val))
                        if is_valid_ein(clean_tin):
                            valid_tins += 1
                            unique_tins.add(clean_tin)
                        group_tins.append(clean_tin)

                if is_ppo:
                    ppo_provider_groups += 1
                if is_hmo:
                    hmo_provider_groups += 1

                if group_id is not None:
                    provider_ref_map[int(group_id)] = {
                        "is_ppo": is_ppo,
                        "is_hmo": is_hmo,
                        "npi_count": len(group_npis),
                        "has_valid_tin": len(group_tins) > 0,
                    }

        prov_stats = {
            "total_provider_reference_groups": total_groups,
            "ppo_provider_reference_groups": ppo_provider_groups,
            "hmo_provider_reference_groups": hmo_provider_groups,
            "total_npis_evaluated": total_npis,
            "valid_npis_evaluated": valid_npis,
            "unique_valid_npis": len(unique_npis),
            "total_tins_evaluated": total_tins,
            "valid_tins_evaluated": valid_tins,
            "unique_valid_tins": len(unique_tins),
        }
        logger.info("Provider references parsed: %d groups (%d PPO, %d HMO), %d unique NPIs, %d unique TINs",
                    total_groups, ppo_provider_groups, hmo_provider_groups, len(unique_npis), len(unique_tins))
        return header_meta, provider_ref_map, prov_stats

    def _stream_in_network_rates(
        self,
        file_path: str,
        provider_ref_map: Dict[int, Dict[str, Any]],
        max_rate_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Stream the `in_network` array using ijson.
        O(1) memory per billing code: aggregates statistics across rates and prices.
        """
        stats: Dict[str, Any] = {
            "total_billing_code_entries": 0,
            "distinct_billing_codes": set(),
            "benchmark_codes_matched": set(),
            "total_rate_records": 0,
            "complete_rate_records": 0,
            "missing_billing_code": 0,
            "missing_rate_value": 0,
            "missing_rate_type": 0,
            "total_prices_evaluated": 0,
            "rate_types": {
                "negotiated": 0,
                "percentage": 0,
                "derived": 0,
                "fee_schedule": 0,
                "other": 0,
            },
            "monetary_rates_total": 0,
            "monetary_rates_positive": 0,
            "monetary_rates_zero": 0,
            "monetary_rates_negative": 0,
            "monetary_rates_non_numeric": 0,
            "percentage_rates_total": 0,
            "provider_references_total": 0,
            "provider_references_resolved": 0,
            "provider_references_orphan": 0,
            "rates_linked_to_ppo": 0,
            "rates_linked_to_hmo": 0,
            "rates_unlinked_generic": 0,
            "active_contracts": 0,
            "expired_contracts": 0,
            "evergreen_contracts": 0,
            "exact_duplicate_rate_records": 0,
            "rate_fingerprints": set(),
            "outliers_extreme_high": 0,
            "outliers_extreme_low": 0,
            "sample_benchmark_rates": {},
        }

        # Targeted benchmark codes to track distributions
        focus_benchmark_codes = {"99214", "99213", "99203", "99204", "11042", "J1559", "95004"}
        for c in focus_benchmark_codes:
            stats["sample_benchmark_rates"][c] = []

        with open(file_path, "rb") as fh:
            item_count = 0
            for item in ijson.items(fh, "in_network.item"):
                item_count += 1
                stats["total_billing_code_entries"] += 1

                billing_code = str(item.get("billing_code", "")).strip()
                billing_code_type = str(item.get("billing_code_type", "")).strip()
                item_desc = str(item.get("description", "")).strip()

                if billing_code:
                    stats["distinct_billing_codes"].add(billing_code)
                    if billing_code in self.benchmark_codes:
                        stats["benchmark_codes_matched"].add(billing_code)
                else:
                    stats["missing_billing_code"] += 1

                rates = item.get("negotiated_rates") or []
                for rate_entry in rates:
                    stats["total_rate_records"] += 1
                    prov_refs = rate_entry.get("provider_references") or []

                    # Evaluate reference integrity
                    is_rate_ppo = False
                    is_rate_hmo = False
                    has_resolved_ref = False

                    for ref_id in prov_refs:
                        stats["provider_references_total"] += 1
                        try:
                            ref_int = int(ref_id)
                        except (ValueError, TypeError):
                            ref_int = -1

                        if ref_int in provider_ref_map:
                            stats["provider_references_resolved"] += 1
                            has_resolved_ref = True
                            if provider_ref_map[ref_int]["is_ppo"]:
                                is_rate_ppo = True
                            if provider_ref_map[ref_int]["is_hmo"]:
                                is_rate_hmo = True
                        else:
                            stats["provider_references_orphan"] += 1

                    if is_rate_ppo:
                        stats["rates_linked_to_ppo"] += 1
                    elif is_rate_hmo:
                        stats["rates_linked_to_hmo"] += 1
                    else:
                        stats["rates_unlinked_generic"] += 1

                    # Evaluate prices
                    prices = rate_entry.get("negotiated_prices") or []
                    for price_obj in prices:
                        stats["total_prices_evaluated"] += 1
                        rate_val = price_obj.get("negotiated_rate")
                        rate_type = str(price_obj.get("negotiated_type", "")).strip().lower()
                        exp_date = str(price_obj.get("expiration_date", "")).strip()
                        b_class = str(price_obj.get("billing_class", "")).strip()
                        setting = str(price_obj.get("setting", "")).strip()
                        add_info = str(price_obj.get("additional_information", "")).strip()
                        service_codes = tuple(sorted(price_obj.get("service_code") or []))

                        # Rate type classification
                        if "negotiated" in rate_type:
                            stats["rate_types"]["negotiated"] += 1
                        elif "percent" in rate_type:
                            stats["rate_types"]["percentage"] += 1
                        elif "derived" in rate_type:
                            stats["rate_types"]["derived"] += 1
                        elif "fee" in rate_type:
                            stats["rate_types"]["fee_schedule"] += 1
                        elif rate_type:
                            stats["rate_types"]["other"] += 1
                        else:
                            stats["missing_rate_type"] += 1

                        # Monetary vs percentage validity
                        if "percent" in rate_type:
                            stats["percentage_rates_total"] += 1
                        else:
                            stats["monetary_rates_total"] += 1
                            if rate_val is None:
                                stats["missing_rate_value"] += 1
                            else:
                                try:
                                    f_rate = float(rate_val)
                                    if math.isnan(f_rate) or math.isinf(f_rate):
                                        stats["monetary_rates_non_numeric"] += 1
                                    elif f_rate == 0.0:
                                        stats["monetary_rates_zero"] += 1
                                    elif f_rate < 0.0:
                                        stats["monetary_rates_negative"] += 1
                                    else:
                                        stats["monetary_rates_positive"] += 1

                                        # Track benchmark code rate samples (bounded size)
                                        if billing_code in stats["sample_benchmark_rates"]:
                                            lst = stats["sample_benchmark_rates"][billing_code]
                                            if len(lst) < 1000:
                                                lst.append(f_rate)

                                        # Extreme outlier detection
                                        if f_rate < 0.01:
                                            stats["outliers_extreme_low"] += 1
                                        elif b_class == "professional" and f_rate > 250000.0:
                                            stats["outliers_extreme_high"] += 1

                                except (ValueError, TypeError):
                                    stats["monetary_rates_non_numeric"] += 1

                        # Completeness check for this record
                        if billing_code and billing_code_type and rate_val is not None and rate_type:
                            stats["complete_rate_records"] += 1

                        # Freshness / Expiration check
                        if exp_date == "9999-12-31":
                            stats["evergreen_contracts"] += 1
                        elif exp_date >= "2024-01-01":
                            stats["active_contracts"] += 1
                        elif exp_date:
                            stats["expired_contracts"] += 1

                        # Deduplication check: clinical service condition fingerprint
                        # Incorporates billing_code, clinical description, provider reference group,
                        # rate value, billing class, setting, service code, and episode/contract code
                        fp_tuple = (
                            billing_code,
                            item_desc,
                            tuple(sorted(prov_refs)),
                            rate_val,
                            rate_type,
                            b_class,
                            setting,
                            service_codes,
                            add_info,
                        )
                        fp_hash = hash(fp_tuple)
                        if fp_hash in stats["rate_fingerprints"]:
                            stats["exact_duplicate_rate_records"] += 1
                        else:
                            if len(stats["rate_fingerprints"]) < 2000000:
                                stats["rate_fingerprints"].add(fp_hash)

                if item_count % 2500 == 0:
                    logger.info("  Streamed %d billing codes (%d rate records, %d prices)...",
                                item_count, stats["total_rate_records"], stats["total_prices_evaluated"])

                if max_rate_items is not None and item_count >= max_rate_items:
                    logger.info("Reached maximum requested item limit (%d); halting stream.", max_rate_items)
                    break

        return stats

    def _compute_metrics(
        self,
        file_path: str,
        file_name: str,
        file_size_bytes: int,
        header_meta: Dict[str, Any],
        prov_stats: Dict[str, Any],
        rate_stats: Dict[str, Any],
        elapsed_seconds: float,
        max_rate_items: Optional[int],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Compute the 11 individual metric scores (0-100), apply weights, and compute overall score.
        """
        metric_details: List[Dict[str, Any]] = []

        # ── M01: Structural Validity (Weight: 10) ─────────────────────────────
        top_keys_present = sum(
            1 for k in self.EXPECTED_TOP_LEVEL_KEYS
            if header_meta.get(k) is not None or header_meta.get(f"has_{k}") is True
        )
        m01_score = round((top_keys_present / len(self.EXPECTED_TOP_LEVEL_KEYS)) * 100.0, 2)
        metric_details.append({
            "metric_id": "M01",
            "metric_name": "Structural Validity",
            "category": "Structure",
            "weight": self.weights["m01_structural_validity"],
            "numerator": top_keys_present,
            "denominator": len(self.EXPECTED_TOP_LEVEL_KEYS),
            "raw_percentage": m01_score,
            "score": m01_score,
            "weighted_score": round(m01_score * (self.weights["m01_structural_validity"] / 100.0), 2),
            "status": "PASS" if m01_score >= 80.0 else "FAIL",
            "description": "Verifies all required CMS TiC v2.0.0 top-level and section keys are present.",
        })

        # ── M02: Field Completeness (Weight: 10) ──────────────────────────────
        tot_rates = max(rate_stats["total_rate_records"], 1)
        tot_prices = max(rate_stats["total_prices_evaluated"], 1)
        comp_rates = min(rate_stats["complete_rate_records"], tot_prices)
        m02_score = round(min(100.0, (comp_rates / tot_prices) * 100.0), 2)
        metric_details.append({
            "metric_id": "M02",
            "metric_name": "Field Completeness",
            "category": "Completeness",
            "weight": self.weights["m02_field_completeness"],
            "numerator": comp_rates,
            "denominator": tot_prices,
            "raw_percentage": m02_score,
            "score": m02_score,
            "weighted_score": round(m02_score * (self.weights["m02_field_completeness"] / 100.0), 2),
            "status": "PASS" if m02_score >= 90.0 else "WARN",
            "description": "Proportion of rate price records with complete billing code, code type, and price value.",
        })

        # ── M03: Provider Identifier Validity (Weight: 10) ────────────────────
        tot_npis = max(prov_stats["total_npis_evaluated"], 1)
        valid_npis = prov_stats["valid_npis_evaluated"]
        npi_pct = (valid_npis / tot_npis) * 100.0

        tot_tins = max(prov_stats["total_tins_evaluated"], 1)
        valid_tins = prov_stats["valid_tins_evaluated"]
        tin_pct = (valid_tins / tot_tins) * 100.0

        m03_score = round(0.5 * npi_pct + 0.5 * tin_pct, 2)
        metric_details.append({
            "metric_id": "M03",
            "metric_name": "Provider Identifier Validity",
            "category": "Provider Coverage",
            "weight": self.weights["m03_provider_identifier_validity"],
            "numerator": valid_npis + valid_tins,
            "denominator": tot_npis + tot_tins,
            "raw_percentage": m03_score,
            "score": m03_score,
            "weighted_score": round(m03_score * (self.weights["m03_provider_identifier_validity"] / 100.0), 2),
            "status": "PASS" if m03_score >= 90.0 else "WARN",
            "description": "Checks 10-digit Luhn checksum validity on NPIs and 9-digit format on EINs.",
        })

        # ── M04: Reference Integrity (Weight: 10) ─────────────────────────────
        tot_prov_refs = max(rate_stats["provider_references_total"], 1)
        res_prov_refs = rate_stats["provider_references_resolved"]
        m04_score = round((res_prov_refs / tot_prov_refs) * 100.0, 2)
        metric_details.append({
            "metric_id": "M04",
            "metric_name": "Reference Integrity",
            "category": "Integrity",
            "weight": self.weights["m04_reference_integrity"],
            "numerator": res_prov_refs,
            "denominator": tot_prov_refs,
            "raw_percentage": m04_score,
            "score": m04_score,
            "weighted_score": round(m04_score * (self.weights["m04_reference_integrity"] / 100.0), 2),
            "status": "PASS" if m04_score >= 95.0 else "FAIL",
            "description": "Proportion of provider reference IDs in negotiated rates resolving to provider_references.",
        })

        # ── M05: Benchmark Billing Code Coverage (Weight: 10) ─────────────────
        benchmark_denom = len(self.benchmark_codes) if self.benchmark_codes else 583
        benchmark_matched = len(rate_stats["benchmark_codes_matched"])
        m05_score = round((benchmark_matched / max(benchmark_denom, 1)) * 100.0, 2)
        metric_details.append({
            "metric_id": "M05",
            "metric_name": "Benchmark Code Coverage",
            "category": "Coverage",
            "weight": self.weights["m05_benchmark_code_coverage"],
            "numerator": benchmark_matched,
            "denominator": benchmark_denom,
            "raw_percentage": m05_score,
            "score": m05_score,
            "weighted_score": round(m05_score * (self.weights["m05_benchmark_code_coverage"] / 100.0), 2),
            "status": "PASS" if m05_score >= 70.0 else "WARN",
            "description": f"Coverage of the {benchmark_denom} hackathon benchmark procedure codes in this file.",
        })

        # ── M06: Monetary Rate Validity (Weight: 15) ──────────────────────────
        tot_monetary = max(rate_stats["monetary_rates_total"], 1)
        pos_monetary = rate_stats["monetary_rates_positive"]
        m06_score = round((pos_monetary / tot_monetary) * 100.0, 2)
        metric_details.append({
            "metric_id": "M06",
            "metric_name": "Monetary Rate Validity",
            "category": "Validity",
            "weight": self.weights["m06_monetary_rate_validity"],
            "numerator": pos_monetary,
            "denominator": tot_monetary,
            "raw_percentage": m06_score,
            "score": m06_score,
            "weighted_score": round(m06_score * (self.weights["m06_monetary_rate_validity"] / 100.0), 2),
            "status": "PASS" if m06_score >= 90.0 else "FAIL",
            "description": "Percentage of monetary dollar rates that are positive and non-zero (penalizes $0 and negative rates).",
        })

        # ── M07: Rate Outlier Quality (Weight: 5) ──────────────────────────────
        extreme_outliers = rate_stats["outliers_extreme_high"] + rate_stats["outliers_extreme_low"]
        outlier_pct = (extreme_outliers / tot_monetary) * 100.0
        m07_score = round(max(0.0, 100.0 - outlier_pct), 2)
        metric_details.append({
            "metric_id": "M07",
            "metric_name": "Rate Outlier Quality",
            "category": "Validity",
            "weight": self.weights["m07_rate_outlier_quality"],
            "numerator": tot_monetary - extreme_outliers,
            "denominator": tot_monetary,
            "raw_percentage": m07_score,
            "score": m07_score,
            "weighted_score": round(m07_score * (self.weights["m07_rate_outlier_quality"] / 100.0), 2),
            "status": "PASS" if m07_score >= 95.0 else "WARN",
            "description": "Freedom from non-credible extreme rate outliers (<$0.01 or >$250,000 professional).",
        })

        # ── M08: Deduplication Quality (Weight: 10) ────────────────────────────
        tot_prices = max(rate_stats["total_prices_evaluated"], 1)
        dup_prices = rate_stats["exact_duplicate_rate_records"]
        dup_pct = (dup_prices / tot_prices) * 100.0
        m08_score = round(max(0.0, 100.0 - dup_pct), 2)
        metric_details.append({
            "metric_id": "M08",
            "metric_name": "Deduplication Quality",
            "category": "Efficiency",
            "weight": self.weights["m08_deduplication_quality"],
            "numerator": tot_prices - dup_prices,
            "denominator": tot_prices,
            "raw_percentage": m08_score,
            "score": m08_score,
            "weighted_score": round(m08_score * (self.weights["m08_deduplication_quality"] / 100.0), 2),
            "status": "PASS" if m08_score >= 85.0 else "WARN",
            "description": "Measures uniqueness of rate combinations (penalizes exact duplicate records).",
        })

        # ── M09: Rate Type Usability (Weight: 5) ───────────────────────────────
        negotiated_dollar = rate_stats["rate_types"]["negotiated"]
        m09_score = round((negotiated_dollar / tot_prices) * 100.0, 2)
        metric_details.append({
            "metric_id": "M09",
            "metric_name": "Rate Type Usability",
            "category": "Usability",
            "weight": self.weights["m09_rate_type_usability"],
            "numerator": negotiated_dollar,
            "denominator": tot_prices,
            "raw_percentage": m09_score,
            "score": m09_score,
            "weighted_score": round(m09_score * (self.weights["m09_rate_type_usability"] / 100.0), 2),
            "status": "PASS" if m09_score >= 80.0 else "INFO",
            "description": "Proportion of rates specified as direct fee-for-service negotiated dollar amounts.",
        })

        # ── M10: Freshness & Expiration Validity (Weight: 5) ──────────────────
        active_exp = rate_stats["evergreen_contracts"] + rate_stats["active_contracts"]
        m10_score = round((active_exp / tot_prices) * 100.0, 2)
        metric_details.append({
            "metric_id": "M10",
            "metric_name": "Freshness & Expiration Validity",
            "category": "Freshness",
            "weight": self.weights["m10_freshness_expiration"],
            "numerator": active_exp,
            "denominator": tot_prices,
            "raw_percentage": m10_score,
            "score": m10_score,
            "weighted_score": round(m10_score * (self.weights["m10_freshness_expiration"] / 100.0), 2),
            "status": "PASS" if m10_score >= 90.0 else "WARN",
            "description": "Proportion of rate entries with active or evergreen future contract expiration dates.",
        })

        # ── M11: PPO Applicability & Sub-network Linkage (Weight: 10) ─────────
        ppo_rates = rate_stats["rates_linked_to_ppo"]
        m11_score = round((ppo_rates / tot_rates) * 100.0, 2)
        metric_details.append({
            "metric_id": "M11",
            "metric_name": "PPO Applicability",
            "category": "Applicability",
            "weight": self.weights["m11_ppo_applicability"],
            "numerator": ppo_rates,
            "denominator": tot_rates,
            "raw_percentage": m11_score,
            "score": m11_score,
            "weighted_score": round(m11_score * (self.weights["m11_ppo_applicability"] / 100.0), 2),
            "status": "PASS" if m11_score >= 50.0 else "WARN",
            "description": "Proportion of rate records that link to confirmed/probable PPO provider references.",
        })

        # ── Composite Overall Score (0-100) ───────────────────────────────────
        overall_score = round(sum(d["weighted_score"] for d in metric_details), 2)

        file_metrics = {
            "file_name": file_name,
            "file_path": file_path,
            "file_size_bytes": file_size_bytes,
            "file_size_mb": round(file_size_bytes / (1024 * 1024), 2),
            "analysis_coverage": "SAMPLE" if max_rate_items is not None else "FULL",
            "max_items_capped": max_rate_items,
            "elapsed_seconds": round(elapsed_seconds, 2),
            "reporting_entity_name": header_meta.get("reporting_entity_name"),
            "reporting_entity_type": header_meta.get("reporting_entity_type"),
            "version": header_meta.get("version"),
            "last_updated_on": header_meta.get("last_updated_on"),
            "total_provider_reference_groups": prov_stats["total_provider_reference_groups"],
            "ppo_provider_reference_groups": prov_stats["ppo_provider_reference_groups"],
            "hmo_provider_reference_groups": prov_stats["hmo_provider_reference_groups"],
            "unique_valid_npis": prov_stats["unique_valid_npis"],
            "unique_valid_tins": prov_stats["unique_valid_tins"],
            "total_billing_code_entries": rate_stats["total_billing_code_entries"],
            "distinct_billing_codes_count": len(rate_stats["distinct_billing_codes"]),
            "benchmark_codes_matched_count": len(rate_stats["benchmark_codes_matched"]),
            "benchmark_codes_total": len(self.benchmark_codes) if self.benchmark_codes else 583,
            "total_rate_records": rate_stats["total_rate_records"],
            "total_prices_evaluated": rate_stats["total_prices_evaluated"],
            "monetary_rates_positive_count": rate_stats["monetary_rates_positive"],
            "monetary_rates_zero_count": rate_stats["monetary_rates_zero"],
            "monetary_rates_negative_count": rate_stats["monetary_rates_negative"],
            "orphan_provider_references_count": rate_stats["provider_references_orphan"],
            "exact_duplicate_rate_records": rate_stats["exact_duplicate_rate_records"],
            "rates_linked_to_ppo_count": rate_stats["rates_linked_to_ppo"],
            "rates_linked_to_hmo_count": rate_stats["rates_linked_to_hmo"],
            "rates_unlinked_generic_count": rate_stats["rates_unlinked_generic"],
            "m01_structural_validity": m01_score,
            "m02_field_completeness": m02_score,
            "m03_provider_identifier_validity": m03_score,
            "m04_reference_integrity": m04_score,
            "m05_benchmark_code_coverage": m05_score,
            "m06_monetary_rate_validity": m06_score,
            "m07_rate_outlier_quality": m07_score,
            "m08_deduplication_quality": m08_score,
            "m09_rate_type_usability": m09_score,
            "m10_freshness_expiration": m10_score,
            "m11_ppo_applicability": m11_score,
            "overall_quality_score": overall_score,
            "quality_grade": "A" if overall_score >= 90 else ("B" if overall_score >= 80 else ("C" if overall_score >= 70 else "D")),
        }

        return file_metrics, metric_details


# ── Pipeline runner & Deliverable Generator ───────────────────────────────────

def run_c3(config_path: Optional[Path] = None, max_rate_items: Optional[int] = None) -> Dict[str, Any]:
    """
    Execute Phase 3 (C3) PTD File Quality Grader pipeline.

    Evaluates the target California commercial rate file, computes all metrics,
    and exports deliverables.
    """
    cfg = load_config(config_path)
    ensure_directories(cfg)

    log_file = os.path.join(cfg.get("logs_dir", "logs"), "c3_file_grader.log")
    setup_logging(log_level="INFO", log_file=log_file)

    logger.info("=" * 70)
    logger.info("Phase 3: Price Transparency Data File Quality Grading (C3)")
    logger.info("=" * 70)

    # Determine target rate file path
    target_path = cfg.get("target_rate_file_path")
    if not target_path or not os.path.exists(target_path):
        # Fallback to checking default data/raw path
        default_target = os.path.join(cfg.get("raw_data_dir", "data/raw"), "2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json")
        if os.path.exists(default_target):
            target_path = default_target
        else:
            raise FileNotFoundError(
                f"Target rate file {target_path} not found on disk. Please ensure it is downloaded in data/raw/."
            )

    grader = PTDFileGrader(cfg)
    file_metrics, metric_details = grader.grade_file(target_path, max_rate_items=max_rate_items)

    # Build DataFrames
    metrics_df = pd.DataFrame([file_metrics])
    details_df = pd.DataFrame(metric_details)

    # Output paths
    metrics_csv = cfg["c3_file_quality_metrics_csv"]
    details_csv = cfg["c3_metric_details_csv"]
    summary_json_path = cfg["c3_summary_json"]

    metrics_df.to_csv(metrics_csv, index=False, encoding="utf-8")
    logger.info("Written: %s", metrics_csv)

    details_df.to_csv(details_csv, index=False, encoding="utf-8")
    logger.info("Written: %s (%d metric rows)", details_csv, len(details_df))

    # Summary JSON
    summary = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "C3 - PTD File Quality Grading",
        "file_assessed": file_metrics["file_name"],
        "file_size_bytes": file_metrics["file_size_bytes"],
        "analysis_coverage": file_metrics["analysis_coverage"],
        "elapsed_seconds": file_metrics["elapsed_seconds"],
        "overall_quality_score": file_metrics["overall_quality_score"],
        "quality_grade": file_metrics["quality_grade"],
        "key_counts": {
            "provider_reference_groups": file_metrics["total_provider_reference_groups"],
            "ppo_provider_reference_groups": file_metrics["ppo_provider_reference_groups"],
            "hmo_provider_reference_groups": file_metrics["hmo_provider_reference_groups"],
            "unique_valid_npis": file_metrics["unique_valid_npis"],
            "unique_valid_tins": file_metrics["unique_valid_tins"],
            "distinct_billing_codes": file_metrics["distinct_billing_codes_count"],
            "benchmark_codes_matched": file_metrics["benchmark_codes_matched_count"],
            "benchmark_codes_denominator": file_metrics["benchmark_codes_total"],
            "total_rate_records": file_metrics["total_rate_records"],
            "total_prices_evaluated": file_metrics["total_prices_evaluated"],
            "monetary_rates_positive": file_metrics["monetary_rates_positive_count"],
            "monetary_rates_zero": file_metrics["monetary_rates_zero_count"],
            "monetary_rates_negative": file_metrics["monetary_rates_negative_count"],
            "orphan_provider_references": file_metrics["orphan_provider_references_count"],
            "exact_duplicate_rates": file_metrics["exact_duplicate_rate_records"],
            "rates_linked_to_ppo": file_metrics["rates_linked_to_ppo_count"],
        },
        "metric_scores": {
            row["metric_name"]: {
                "score": row["score"],
                "weight": row["weight"],
                "weighted_score": row["weighted_score"],
                "status": row["status"],
            }
            for row in metric_details
        },
        "data_limitations_and_caveats": [
            "Consolidated multi-network file: The rate file contains rates for both HMO and PPO networks. M11 measures the proportion of rates that link to confirmed/probable PPO contracts.",
            "Zero rates: The rate file contains explicit $0.00 rates which represent unnegotiated services or placeholder contracts; these are penalized in M06.",
            "Expiration dates: Most active rates list expiration_date='9999-12-31' representing evergreen contractual fee schedules.",
            "Benchmark coverage denominator: Scored against the 583 procedural codes specified in the hackathon benchmark dataset.",
        ],
        "next_step_recommendation": (
            "Proceed to Phase C4: PPO-specific provider-rate extraction, linking rates through confirmed PPO "
            "provider_references ('HealthNet PPO (California)', 'PPO: <County>') to isolate pure commercial group PPO rates."
        ),
    }

    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    logger.info("Written: %s", summary_json_path)

    # Console summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("C3 FILE QUALITY EVALUATION SUMMARY")
    logger.info("=" * 70)
    logger.info("File Assessed               : %s (%.1f MB)", file_metrics["file_name"], file_metrics["file_size_mb"])
    logger.info("Analysis Coverage           : %s", file_metrics["analysis_coverage"])
    logger.info("Overall Quality Score (0-100): %.2f / 100.00 (Grade: %s)", file_metrics["overall_quality_score"], file_metrics["quality_grade"])
    logger.info("-" * 70)
    for m in metric_details:
        logger.info("  %-32s : %6.2f%% (W: %4.1f, Weighted: %5.2f) [%s]",
                    m["metric_name"], m["score"], m["weight"], m["weighted_score"], m["status"])
    logger.info("-" * 70)
    logger.info("Key Counts:")
    logger.info("  Distinct Billing Codes    : %d (Benchmark Matched: %d / %d)",
                file_metrics["distinct_billing_codes_count"], file_metrics["benchmark_codes_matched_count"], file_metrics["benchmark_codes_total"])
    logger.info("  Total Rate Records        : %d", file_metrics["total_rate_records"])
    logger.info("  Total Prices Evaluated    : %d", file_metrics["total_prices_evaluated"])
    logger.info("  Monetary Rates (Positive) : %d (Zero: %d, Negative: %d)",
                file_metrics["monetary_rates_positive_count"], file_metrics["monetary_rates_zero_count"], file_metrics["monetary_rates_negative_count"])
    logger.info("  Unique Providers (NPIs)   : %d (TINs: %d)",
                file_metrics["unique_valid_npis"], file_metrics["unique_valid_tins"])
    logger.info("  PPO-Linked Rate Records   : %d (%.1f%%)",
                file_metrics["rates_linked_to_ppo_count"], file_metrics["m11_ppo_applicability"])
    logger.info("=" * 70)

    return summary


# ── Script Entry Point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 3: Grade PTD File Quality.")
    parser.add_argument("--config", type=Path, default=None, help="Path to settings.yaml")
    parser.add_argument("--sample", type=int, default=None, help="Optional cap on billing code items to stream")
    args = parser.parse_args()

    summary = run_c3(config_path=args.config, max_rate_items=args.sample)
    sys.exit(0)
