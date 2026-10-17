"""
src/c1_index_parser.py
────────────────────────────────────────────────────────────────────────────────
Phase 1 – Parse Centene's Price Transparency Index Files

Objective:
  Produce a reliable, deduplicated inventory of every plan and rate file
  published across all Centene brand index files.  This is the prerequisite
  for C2 (PPO network identification) and C3 (rate extraction + address mapping).

What this module does
─────────────────────
  1. Reads brand/index-path entries from config/settings.yaml.
  2. Downloads each CMS TiC v2.0.0 JSON index file with retry/backoff.
  3. Parses the `reporting_structure` array into a flat plan-level table:
       brand | plan_name | plan_id | plan_id_type | plan_market_type |
       issuer_name | network_type | network_type_evidence |
       file_type | rate_file_url | file_description |
       source_index_url | retrieved_at | parse_status
  4. Normalises and deduplicates rate-file URLs by SHA-256 fingerprint;
     retains the full set of plans that reference each file.
  5. Writes three output artefacts:
       outputs/plan_index.csv
       outputs/unique_rate_files.csv
       outputs/index_parsing_summary.json
  6. Logs every skipped record and parsing error clearly.

Design decisions
────────────────
  • No PPO assumption from name alone: `network_type` is assigned as
    'PPO' only when "PPO" or "preferred provider" appears in plan_name
    or file description (case-insensitive).  Otherwise it is "UNKNOWN".
    `network_type_evidence` records the source string for auditing.

  • URL normalisation: strip trailing slash → decode %20 → re-encode →
    lowercase scheme+host → remove tracking params.  Then SHA-256 the
    canonical URL for deduplication.

  • Memory efficiency: the largest index files can be tens of MB of JSON
    (not multi-GB rate files).  We load them fully but with streaming HTTP
    so we don't keep raw bytes and parsed object simultaneously.

  • Rerunnability: outputs are overwritten; raw JSON index files are saved
    to data/raw/ for reproducibility and cached on reruns if
    use_cached_index: true is set in config.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import urllib.parse

import pandas as pd

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (
    HttpClient,
    ensure_directories,
    load_config,
    normalize_url,
    setup_logging,
    url_fingerprint,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
# Regex patterns used to infer network type from plan name / file description
_PPO_RE = re.compile(r'\bppo\b|preferred\s+provider', re.IGNORECASE)
_HMO_RE = re.compile(r'\bhmo\b|health\s+maintenance', re.IGNORECASE)
_EPO_RE = re.compile(r'\bepo\b|exclusive\s+provider', re.IGNORECASE)
_POS_RE = re.compile(r'\bpos\b|point\s+of\s+service', re.IGNORECASE)

# CMS TiC index file types
_IN_NETWORK = "in_network"
_ALLOWED_AMOUNTS = "allowed_amounts"


# ── Network type inference ────────────────────────────────────────────────────

def infer_network_type(text: str) -> Tuple[str, str]:
    """
    Attempt to infer network type from free-text (plan name or file description).

    Returns
    -------
    (network_type, evidence)
        network_type : one of 'PPO', 'HMO', 'EPO', 'POS', 'UNKNOWN'
        evidence     : the matched pattern string, empty if UNKNOWN
    """
    for pattern, label in (
        (_PPO_RE, "PPO"),
        (_HMO_RE, "HMO"),
        (_EPO_RE, "EPO"),
        (_POS_RE, "POS"),
    ):
        m = pattern.search(text)
        if m:
            return label, m.group(0)
    return "UNKNOWN", ""


# ── Per-index parsing ─────────────────────────────────────────────────────────

def _safe_str(val: Any, default: str = "") -> str:
    """Return stripped string; default on None/non-string."""
    if val is None:
        return default
    return str(val).strip()


def parse_index_entry(
    brand: str,
    source_index_url: str,
    index_data: Dict[str, Any],
    retrieved_at: str,
    strip_params: Optional[List[str]] = None,
) -> Tuple[List[Dict], List[str]]:
    """
    Parse one CMS TiC v2.0.0 index JSON object into flat row dicts.

    Parameters
    ----------
    brand            : Brand label from config (e.g. 'Health Net')
    source_index_url : Canonical URL the index was fetched from
    index_data       : Parsed JSON dict from the index file
    retrieved_at     : ISO-8601 timestamp string of retrieval
    strip_params     : Query-string params to strip during URL normalization

    Returns
    -------
    (rows, skipped_messages)
        rows             : list of flat row dicts ready for DataFrame
        skipped_messages : list of human-readable skip/error strings
    """
    rows: List[Dict] = []
    skipped: List[str] = []

    reporting_entity = _safe_str(index_data.get("reporting_entity_name"))
    reporting_type = _safe_str(index_data.get("reporting_entity_type"))
    last_updated = _safe_str(index_data.get("last_updated_on"))
    schema_version = _safe_str(index_data.get("version"))

    structures = index_data.get("reporting_structure")
    if not isinstance(structures, list):
        skipped.append(f"[{brand}] 'reporting_structure' missing or not a list; skipping entire index.")
        return rows, skipped

    for struct_idx, structure in enumerate(structures):
        if not isinstance(structure, dict):
            skipped.append(f"[{brand}] reporting_structure[{struct_idx}] is not a dict; skipped.")
            continue

        # Plans
        reporting_plans = structure.get("reporting_plans") or []
        if not isinstance(reporting_plans, list):
            skipped.append(f"[{brand}] reporting_structure[{struct_idx}].reporting_plans not a list; skipped.")
            reporting_plans = []

        # Rate files: in-network and allowed-amounts
        file_groups: List[Tuple[str, List[Any]]] = [
            (_IN_NETWORK, structure.get("in_network_files") or []),
            (_ALLOWED_AMOUNTS, structure.get("allowed_amounts_files") or []),
        ]

        # For each plan × rate file combination
        for file_type, file_list in file_groups:
            if not isinstance(file_list, list):
                skipped.append(
                    f"[{brand}] struct[{struct_idx}].{file_type}_files not a list; skipped."
                )
                continue

            for file_idx, rate_file in enumerate(file_list):
                if not isinstance(rate_file, dict):
                    skipped.append(
                        f"[{brand}] struct[{struct_idx}].{file_type}[{file_idx}] not a dict; skipped."
                    )
                    continue

                raw_url = _safe_str(rate_file.get("location"))
                file_desc = _safe_str(rate_file.get("description"))

                if not raw_url:
                    skipped.append(
                        f"[{brand}] struct[{struct_idx}].{file_type}[{file_idx}] "
                        f"missing 'location'; skipped."
                    )
                    continue

                norm_url = normalize_url(raw_url, strip_params=strip_params)
                url_fp = url_fingerprint(norm_url)

                # Infer network type from file description first, then fall back to plan names
                net_type, net_evidence = infer_network_type(file_desc)

                if not reporting_plans:
                    # Rate file without any plan — record with empty plan fields
                    net_t, net_e = net_type, net_evidence
                    rows.append({
                        "brand": brand,
                        "plan_name": "",
                        "plan_id": "",
                        "plan_id_type": "",
                        "plan_market_type": "",
                        "issuer_name": "",
                        "network_type": net_t,
                        "network_type_source": "file_description" if net_e else "none",
                        "network_type_evidence": net_e,
                        "file_type": file_type,
                        "rate_file_url": norm_url,
                        "rate_file_url_raw": raw_url,
                        "rate_file_fingerprint": url_fp,
                        "file_description": file_desc,
                        "reporting_entity_name": reporting_entity,
                        "reporting_entity_type": reporting_type,
                        "last_updated_on": last_updated,
                        "schema_version": schema_version,
                        "source_index_url": source_index_url,
                        "retrieved_at": retrieved_at,
                        "parse_status": "ok",
                    })
                    continue

                for plan in reporting_plans:
                    if not isinstance(plan, dict):
                        skipped.append(
                            f"[{brand}] struct[{struct_idx}] plan entry not a dict; skipped."
                        )
                        continue

                    plan_name = _safe_str(plan.get("plan_name"))
                    plan_id = _safe_str(plan.get("plan_id"))
                    plan_id_type = _safe_str(plan.get("plan_id_type"))
                    plan_market_type = _safe_str(plan.get("plan_market_type"))
                    issuer_name = _safe_str(plan.get("issuer_name"))

                    # Network type: file description wins; if UNKNOWN try plan name
                    if net_type == "UNKNOWN" and plan_name:
                        plan_net_type, plan_net_ev = infer_network_type(plan_name)
                        nt, ne, ns = (
                            (plan_net_type, plan_net_ev, "plan_name")
                            if plan_net_type != "UNKNOWN"
                            else ("UNKNOWN", "", "none")
                        )
                    elif net_type != "UNKNOWN":
                        nt, ne, ns = net_type, net_evidence, "file_description"
                    else:
                        nt, ne, ns = "UNKNOWN", "", "none"

                    rows.append({
                        "brand": brand,
                        "plan_name": plan_name,
                        "plan_id": plan_id,
                        "plan_id_type": plan_id_type,
                        "plan_market_type": plan_market_type,
                        "issuer_name": issuer_name,
                        "network_type": nt,
                        "network_type_source": ns,
                        "network_type_evidence": ne,
                        "file_type": file_type,
                        "rate_file_url": norm_url,
                        "rate_file_url_raw": raw_url,
                        "rate_file_fingerprint": url_fp,
                        "file_description": file_desc,
                        "reporting_entity_name": reporting_entity,
                        "reporting_entity_type": reporting_type,
                        "last_updated_on": last_updated,
                        "schema_version": schema_version,
                        "source_index_url": source_index_url,
                        "retrieved_at": retrieved_at,
                        "parse_status": "ok",
                    })

    return rows, skipped


# ── Deduplication helpers ─────────────────────────────────────────────────────

def build_unique_rate_files(plan_df: pd.DataFrame) -> pd.DataFrame:
    """
    From the full plan-level DataFrame, build a unique-rate-file table.

    Each row = one unique rate file URL.
    Columns:
      rate_file_fingerprint, rate_file_url, file_type, file_description,
      plan_count, brand_list, market_types, network_types,
      source_index_urls, last_updated_on
    """
    if plan_df.empty:
        return pd.DataFrame()

    agg = (
        plan_df.groupby("rate_file_fingerprint", as_index=False)
        .agg(
            rate_file_url=("rate_file_url", "first"),
            file_type=("file_type", "first"),
            file_description=("file_description", "first"),
            plan_count=("plan_name", "count"),
            brand_list=("brand", lambda s: "|".join(sorted(s.dropna().unique()))),
            market_types=(
                "plan_market_type",
                lambda s: "|".join(sorted(s.dropna().unique())),
            ),
            network_types=(
                "network_type",
                lambda s: "|".join(sorted(s.dropna().unique())),
            ),
            source_index_urls=(
                "source_index_url",
                lambda s: "|".join(sorted(s.dropna().unique())),
            ),
            last_updated_on=("last_updated_on", "first"),
        )
        .sort_values("plan_count", ascending=False)
    )
    return agg


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_c1(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Entry point for C1.

    Returns a summary dict (also written to outputs/index_parsing_summary.json).
    """
    cfg = load_config(config_path)
    ensure_directories(cfg)

    log_file = os.path.join(cfg.get("logs_dir", "logs"), "c1_index_parser.log")
    setup_logging(log_level="INFO", log_file=log_file)

    logger.info("=" * 70)
    logger.info("Phase 1: Centene Index Parsing")
    logger.info("=" * 70)

    client = HttpClient(cfg)
    strip_params: List[str] = cfg.get("url_strip_params", [])
    base_url: str = cfg.get("centene_base_url", "https://www.centene.com")
    use_cache: bool = cfg.get("use_cached_index", False)
    raw_dir = Path(cfg["raw_data_dir"])

    all_rows: List[Dict] = []
    all_skipped: List[str] = []
    index_results: List[Dict] = []

    index_configs = cfg.get("index_files", [])
    logger.info("Index files configured: %d", len(index_configs))

    for idx_cfg in index_configs:
        brand: str = idx_cfg.get("brand", "Unknown")
        path: str = idx_cfg.get("path", "")
        desc: str = idx_cfg.get("description", "")

        full_url = base_url + path
        norm_url = normalize_url(full_url)
        retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.info("Processing brand=%-20s  url=%s", brand, norm_url[-60:])

        # Cache path: strip query parameters to ensure safe filename on Windows/Linux
        clean_path = urllib.parse.urlparse(path).path
        filename = clean_path.split("/")[-1].replace("%20", "_")
        cache_path = raw_dir / filename

        index_data: Optional[Dict] = None
        fetch_status = "ok"
        fetch_error: Optional[str] = None

        # Try cache first
        if use_cache and cache_path.exists():
            logger.info("  Using cached file: %s", cache_path)
            try:
                with open(cache_path, "r", encoding="utf-8-sig") as fh:
                    index_data = json.load(fh)
                fetch_status = "cached"
            except Exception as exc:
                logger.warning("  Cache read failed (%s); re-downloading.", exc)
                index_data = None

        if index_data is None:
            index_data, fetch_error = client.get_json(norm_url)
            if fetch_error:
                logger.error("  FETCH FAILED: %s", fetch_error)
                fetch_status = "fetch_failed"
            else:
                fetch_status = "downloaded"
                # Save to cache
                try:
                    with open(cache_path, "w", encoding="utf-8") as fh:
                        json.dump(index_data, fh)
                    logger.info("  Cached to %s", cache_path)
                except OSError as exc:
                    logger.warning("  Could not write cache (%s).", exc)

        rows_before = len(all_rows)
        skipped_before = len(all_skipped)

        if index_data is not None:
            rows, skipped = parse_index_entry(
                brand=brand,
                source_index_url=norm_url,
                index_data=index_data,
                retrieved_at=retrieved_at,
                strip_params=strip_params,
            )
            all_rows.extend(rows)
            all_skipped.extend(skipped)
            logger.info(
                "  -> %d plan-file rows parsed, %d skipped",
                len(rows), len(skipped)
            )
            for s in skipped:
                logger.warning("  SKIP: %s", s)
        else:
            rows, skipped = [], []

        index_results.append({
            "brand": brand,
            "description": desc,
            "source_index_url": norm_url,
            "retrieved_at": retrieved_at,
            "fetch_status": fetch_status,
            "fetch_error": fetch_error,
            "rows_parsed": len(rows),
            "rows_skipped": len(skipped),
        })

    # ── Build DataFrames ──────────────────────────────────────────────────────

    if all_rows:
        plan_df = pd.DataFrame(all_rows)
    else:
        plan_df = pd.DataFrame(columns=[
            "brand", "plan_name", "plan_id", "plan_id_type", "plan_market_type",
            "issuer_name", "network_type", "network_type_source", "network_type_evidence",
            "file_type", "rate_file_url", "rate_file_url_raw", "rate_file_fingerprint",
            "file_description", "reporting_entity_name", "reporting_entity_type",
            "last_updated_on", "schema_version", "source_index_url", "retrieved_at",
            "parse_status",
        ])

    unique_df = build_unique_rate_files(plan_df)

    # ── Write outputs ─────────────────────────────────────────────────────────

    plan_csv = cfg["plan_index_csv"]
    unique_csv = cfg["unique_rate_files_csv"]
    summary_json = cfg["index_parsing_summary_json"]

    plan_df.to_csv(plan_csv, index=False, encoding="utf-8")
    logger.info("Written: %s  (%d rows)", plan_csv, len(plan_df))

    unique_df.to_csv(unique_csv, index=False, encoding="utf-8")
    logger.info("Written: %s  (%d rows)", unique_csv, len(unique_df))

    # ── Compute summary statistics ────────────────────────────────────────────

    n_unique_urls = plan_df["rate_file_fingerprint"].nunique() if not plan_df.empty else 0
    n_plans = len(plan_df)
    n_ppo = int((plan_df["network_type"] == "PPO").sum()) if not plan_df.empty else 0
    brand_counts: Dict[str, int] = {}
    if not plan_df.empty:
        brand_counts = plan_df.groupby("brand").size().to_dict()
        brand_counts = {k: int(v) for k, v in brand_counts.items()}

    market_counts: Dict[str, int] = {}
    if not plan_df.empty:
        market_counts = plan_df["plan_market_type"].value_counts().to_dict()
        market_counts = {k: int(v) for k, v in market_counts.items()}

    network_counts: Dict[str, int] = {}
    if not plan_df.empty:
        network_counts = plan_df["network_type"].value_counts().to_dict()
        network_counts = {k: int(v) for k, v in network_counts.items()}

    summary: Dict[str, Any] = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "C1 - Index Parsing",
        "payer": "Centene",
        "scope": "All brands (Ambetter, Health Net, Fidelis, QualChoice)",
        "index_files_attempted": len(index_configs),
        "index_files_ok": sum(1 for r in index_results if r["fetch_status"] in ("ok", "downloaded", "cached")),
        "index_files_failed": sum(1 for r in index_results if r["fetch_status"] == "fetch_failed"),
        "total_plan_file_rows": n_plans,
        "unique_rate_file_urls": n_unique_urls,
        "plan_rows_with_ppo": n_ppo,
        "rows_skipped": len(all_skipped),
        "brand_row_counts": brand_counts,
        "market_type_counts": market_counts,
        "network_type_counts": network_counts,
        "output_files": {
            "plan_index_csv": plan_csv,
            "unique_rate_files_csv": unique_csv,
            "index_parsing_summary_json": summary_json,
        },
        "index_file_results": index_results,
        "skipped_messages": all_skipped,
    }

    with open(summary_json, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    logger.info("Written: %s", summary_json)

    # ── Print human-readable summary ──────────────────────────────────────────
    logger.info("")
    logger.info("-" * 70)
    logger.info("C1 SUMMARY")
    logger.info("-" * 70)
    logger.info("Index files attempted : %d", summary["index_files_attempted"])
    logger.info("Index files fetched OK: %d", summary["index_files_ok"])
    logger.info("Index files failed    : %d", summary["index_files_failed"])
    logger.info("Total plan-file rows  : %d", summary["total_plan_file_rows"])
    logger.info("Unique rate-file URLs : %d", summary["unique_rate_file_urls"])
    logger.info("PPO-labeled rows      : %d", summary["plan_rows_with_ppo"])
    logger.info("Rows skipped/errors   : %d", summary["rows_skipped"])
    logger.info("Brand breakdown:")
    for b, c in sorted(brand_counts.items()):
        logger.info("  %-30s : %d", b, c)
    logger.info("Market type breakdown:")
    for m, c in sorted(market_counts.items()):
        logger.info("  %-30s : %d", m, c)
    logger.info("Network type breakdown:")
    for n, c in sorted(network_counts.items()):
        logger.info("  %-30s : %d", n, c)
    logger.info("-" * 70)

    return summary


# ── Script entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 1: Parse Centene price-transparency index files."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to settings.yaml (default: config/settings.yaml relative to project root)",
    )
    args = parser.parse_args()

    summary = run_c1(config_path=args.config)
    sys.exit(0 if summary.get("index_files_failed", 1) == 0 else 1)
