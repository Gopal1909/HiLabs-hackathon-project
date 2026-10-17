"""
src/c7_cost_effectiveness.py
Phase 7: Rate Cost-Effectiveness and Price Competitiveness Analysis.

Measures relative price competitiveness across defensible, clinically comparable
peer groups within Centene's California Commercial Group PPO network.

Defines peer groups using:
  - billing_code (CPT/HCPCS)
  - billing_code_modifier (e.g., 26, TC, 95, or GLOBAL)
  - billing_class (professional vs. institutional)
  - setting (outpatient vs. inpatient)
  - contract arrangement (fee-for-service negotiated dollar rates)

Computes:
  1. Peer-group median rate and distribution (IQR, percentiles)
  2. Relative Price Index (RPI = provider_rate / peer_median * 100)
  3. Peer Percentile (midpoint rank convention in [0.0, 100.0])
  4. Potential Price Difference (peer_median - provider_rate)
  5. Benchmark-Weighted Fee Index across multi-code provider portfolios

Outputs:
  - outputs/c7_provider_cost_effectiveness.csv
  - outputs/c7_peer_group_summary.csv
  - outputs/c7_summary.json
  - reports/c7_cost_effectiveness_methodology.md
"""
from __future__ import annotations

import csv
import json
import logging
import math
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.utils import get_project_root, load_config, setup_logging

logger = logging.getLogger("c7_cost_effectiveness")


def make_peer_group_id(
    billing_code: str,
    modifier: str,
    billing_class: str,
    setting: str,
) -> str:
    """Construct a canonical, clinical peer group identifier."""
    clean_code = (billing_code or "UNKNOWN").strip().upper()
    clean_mod = (modifier or "").strip().upper()
    if not clean_mod:
        clean_mod = "GLOBAL"
    clean_class = (billing_class or "UNKNOWN").strip().lower()
    clean_setting = (setting or "UNKNOWN").strip().lower()
    return f"{clean_code}|{clean_mod}|{clean_class}|{clean_setting}"


def calculate_distribution_stats(rates: List[float]) -> Dict[str, Any]:
    """Compute non-parametric distribution statistics for a list of rates."""
    if not rates:
        return {
            "sample_size": 0,
            "min_rate": 0.0,
            "p25_rate": 0.0,
            "median_rate": 0.0,
            "mean_rate": 0.0,
            "p75_rate": 0.0,
            "max_rate": 0.0,
            "iqr": 0.0,
            "std_dev": 0.0,
        }

    s = sorted(rates)
    n = len(s)
    mean_val = sum(s) / n
    variance = sum((x - mean_val) ** 2 for x in s) / n if n > 1 else 0.0

    def get_p(p: float) -> float:
        idx = int(n * p)
        return s[min(idx, n - 1)]

    p25 = get_p(0.25)
    median = s[n // 2] if n % 2 == 1 else (s[(n // 2) - 1] + s[n // 2]) / 2.0
    p75 = get_p(0.75)

    return {
        "sample_size": n,
        "min_rate": round(s[0], 2),
        "p25_rate": round(p25, 2),
        "median_rate": round(median, 2),
        "mean_rate": round(mean_val, 2),
        "p75_rate": round(p75, 2),
        "max_rate": round(s[-1], 2),
        "iqr": round(p75 - p25, 2),
        "std_dev": round(math.sqrt(variance), 2),
    }


def calculate_peer_percentile(sorted_peer_rates: List[float], provider_rate: float) -> float:
    """
    Calculate the percentile rank using the standard actuarial midpoint tie convention:
      Percentile = (count(r < rate) + 0.5 * count(r == rate)) / N * 100
    Yields values in [0.0, 100.0].
    """
    n = len(sorted_peer_rates)
    if n == 0:
        return 50.0

    strictly_less = sum(1 for r in sorted_peer_rates if r < provider_rate)
    exact_equal = sum(1 for r in sorted_peer_rates if r == provider_rate)
    percentile = ((strictly_less + 0.5 * exact_equal) / n) * 100.0
    return round(percentile, 1)


def assign_cost_effectiveness_tier(rpi: Optional[float]) -> str:
    """Assign an interpretable price competitiveness category based on RPI."""
    if rpi is None:
        return "INSUFFICIENT_PEER_COUNT"
    if rpi <= 85.0:
        return "HIGHLY_COMPETITIVE"
    elif rpi <= 95.0:
        return "COMPETITIVE"
    elif rpi <= 105.0:
        return "MEDIAN_ALIGNED"
    elif rpi <= 125.0:
        return "ABOVE_MEDIAN"
    else:
        return "HIGH_PRICE_OUTLIER"


def analyze_cost_effectiveness(
    curated_benchmark_csv: str,
    output_provider_csv: str,
    output_peer_summary_csv: str,
    output_summary_json: str,
    min_peer_count: int = 5,
) -> Dict[str, Any]:
    """
    Main execution pipeline for Phase 7 (C7).
    Loads curated benchmark rates, constructs clinical peer groups, calculates
    comparative price metrics, and exports all deliverables.
    """
    t0 = time.time()
    logger.info("Starting C7 Rate Cost-Effectiveness Analysis with min_peer_count=%d", min_peer_count)

    bench_path = Path(curated_benchmark_csv)
    if not bench_path.is_file():
        raise FileNotFoundError(f"Input curated benchmark file not found: {bench_path}")

    # Ensure parent output directories exist
    for p in (output_provider_csv, output_peer_summary_csv, output_summary_json):
        Path(p).parent.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Ingest rates and group by clinical peer group ─────────────────
    records: List[Dict[str, Any]] = []
    peer_rates: Dict[str, List[float]] = defaultdict(list)
    peer_metadata: Dict[str, Dict[str, Any]] = {}

    with open(bench_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rate_val = float(row.get("negotiated_rate", "0.0") or "0.0")
            code = row.get("billing_code", "").strip()
            mod = row.get("billing_code_modifier", "").strip()
            b_class = row.get("billing_class", "").strip()
            setting = row.get("setting", "").strip()

            peer_id = make_peer_group_id(code, mod, b_class, setting)
            peer_rates[peer_id].append(rate_val)

            if peer_id not in peer_metadata:
                peer_metadata[peer_id] = {
                    "billing_code": code,
                    "billing_code_modifier": mod if mod else "GLOBAL",
                    "billing_class": b_class,
                    "setting": setting,
                    "specialty_description": row.get("specialty_description", ""),
                    "benchmark_procedure_weight": row.get("benchmark_procedure_weight", ""),
                }

            row["peer_group_id"] = peer_id
            row["_float_rate"] = rate_val
            records.append(row)

    logger.info("Loaded %d records across %d peer groups.", len(records), len(peer_rates))

    # ── Step 2: Calculate peer group distribution statistics ──────────────────
    peer_stats: Dict[str, Dict[str, Any]] = {}
    eligible_peer_groups = 0
    ineligible_peer_groups = 0

    for peer_id, rates in peer_rates.items():
        stats = calculate_distribution_stats(rates)
        is_eligible = stats["sample_size"] >= min_peer_count
        stats["eligibility_status"] = "ELIGIBLE" if is_eligible else "INSUFFICIENT_PEER_COUNT"
        peer_stats[peer_id] = stats
        if is_eligible:
            eligible_peer_groups += 1
        else:
            ineligible_peer_groups += 1

    logger.info(
        "Peer groups: %d eligible (>= %d providers), %d insufficient sample size.",
        eligible_peer_groups,
        min_peer_count,
        ineligible_peer_groups,
    )

    # ── Step 3: Compute provider-level metrics and explanations ───────────────
    evaluated_records: List[Dict[str, Any]] = []
    tier_counts: Counter[str] = Counter()
    provider_rollups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)

    for r in records:
        peer_id = r["peer_group_id"]
        stats = peer_stats[peer_id]
        sorted_rates = sorted(peer_rates[peer_id])
        n = stats["sample_size"]
        rate = r["_float_rate"]
        code = r.get("billing_code", "")
        mod = r.get("billing_code_modifier", "") or "GLOBAL"

        if stats["eligibility_status"] == "ELIGIBLE":
            median_rate = stats["median_rate"]
            rpi = round((rate / median_rate) * 100.0, 2)
            percentile = calculate_peer_percentile(sorted_rates, rate)
            diff = round(median_rate - rate, 2)
            tier = assign_cost_effectiveness_tier(rpi)
            tier_counts[tier] += 1

            if diff > 0:
                rel_str = f"${diff:.2f} below"
            elif diff < 0:
                rel_str = f"${abs(diff):.2f} above"
            else:
                rel_str = "equal to"

            explanation = (
                f"Rate of ${rate:.2f} is {abs(rpi - 100.0):.1f}% {'below' if rpi < 100.0 else 'above' if rpi > 100.0 else 'aligned with'} "
                f"peer median (${median_rate:.2f}) across {n} comparable California Commercial PPO providers "
                f"({percentile:.1f}th percentile; {rel_str} median)."
            )
        else:
            median_rate = ""
            rpi = ""
            percentile = ""
            diff = ""
            tier = "INSUFFICIENT_PEER_COUNT"
            tier_counts[tier] += 1
            explanation = (
                f"Insufficient peer group sample size ({n} < {min_peer_count}) for code {code} ({mod}) "
                f"in California Commercial PPO market to establish reliable peer median comparison."
            )

        eval_rec = {
            "npi": r["npi"],
            "npi_type": r.get("npi_type", ""),
            "tin_value": r["tin_value"],
            "provider_name": r.get("provider_name", ""),
            "ptd_business_name": r.get("ptd_business_name", ""),
            "address_line_1": r.get("address_line_1", ""),
            "city": r.get("city", ""),
            "state": r.get("state", ""),
            "postal_code": r.get("postal_code", ""),
            "address_verification_status": r.get("address_verification_status", ""),
            "address_confidence": r.get("address_confidence", ""),
            "specialty_description": r.get("specialty_description", ""),
            "billing_code": code,
            "billing_code_modifier": r.get("billing_code_modifier", ""),
            "billing_class": r.get("billing_class", ""),
            "setting": r.get("setting", ""),
            "service_codes": r.get("service_codes", ""),
            "negotiated_rate": rate,
            "rate_selection_flag": r.get("rate_selection_flag", ""),
            "peer_group_id": peer_id,
            "peer_count": n,
            "peer_min_rate": stats["min_rate"],
            "peer_p25_rate": stats["p25_rate"],
            "peer_median_rate": median_rate,
            "peer_p75_rate": stats["p75_rate"],
            "peer_max_rate": stats["max_rate"],
            "peer_iqr": stats["iqr"],
            "relative_price_index": rpi,
            "peer_percentile": percentile,
            "potential_price_difference": diff,
            "benchmark_rank": r.get("benchmark_rank", ""),
            "benchmark_procedure_weight": r.get("benchmark_procedure_weight", ""),
            "benchmark_specialty_weight": r.get("benchmark_specialty_weight", ""),
            "eligibility_status": stats["eligibility_status"],
            "cost_effectiveness_tier": tier,
            "explanation": explanation,
        }
        evaluated_records.append(eval_rec)

        # Track provider portfolio for weighted rollup
        prov_key = (r["npi"], r["tin_value"], r.get("provider_name", ""))
        provider_rollups[prov_key].append(eval_rec)

    # ── Step 4: Write c7_provider_cost_effectiveness.csv ──────────────────────
    provider_fieldnames = [
        "npi",
        "npi_type",
        "tin_value",
        "provider_name",
        "ptd_business_name",
        "address_line_1",
        "city",
        "state",
        "postal_code",
        "address_verification_status",
        "address_confidence",
        "specialty_description",
        "billing_code",
        "billing_code_modifier",
        "billing_class",
        "setting",
        "service_codes",
        "negotiated_rate",
        "rate_selection_flag",
        "peer_group_id",
        "peer_count",
        "peer_min_rate",
        "peer_p25_rate",
        "peer_median_rate",
        "peer_p75_rate",
        "peer_max_rate",
        "peer_iqr",
        "relative_price_index",
        "peer_percentile",
        "potential_price_difference",
        "benchmark_rank",
        "benchmark_procedure_weight",
        "benchmark_specialty_weight",
        "eligibility_status",
        "cost_effectiveness_tier",
        "explanation",
    ]

    with open(output_provider_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=provider_fieldnames)
        writer.writeheader()
        writer.writerows(evaluated_records)

    logger.info("Wrote %d provider cost-effectiveness records to %s", len(evaluated_records), output_provider_csv)

    # ── Step 5: Write c7_peer_group_summary.csv ───────────────────────────────
    peer_summary_fieldnames = [
        "peer_group_id",
        "billing_code",
        "billing_code_modifier",
        "billing_class",
        "setting",
        "specialty_description",
        "sample_size",
        "min_rate",
        "p25_rate",
        "median_rate",
        "mean_rate",
        "p75_rate",
        "max_rate",
        "iqr",
        "std_dev",
        "benchmark_procedure_weight",
        "eligibility_status",
    ]

    peer_summary_rows: List[Dict[str, Any]] = []
    for peer_id, stats in sorted(peer_stats.items(), key=lambda x: -x[1]["sample_size"]):
        meta = peer_metadata[peer_id]
        row_dict = {
            "peer_group_id": peer_id,
            "billing_code": meta["billing_code"],
            "billing_code_modifier": meta["billing_code_modifier"],
            "billing_class": meta["billing_class"],
            "setting": meta["setting"],
            "specialty_description": meta["specialty_description"],
            "sample_size": stats["sample_size"],
            "min_rate": stats["min_rate"],
            "p25_rate": stats["p25_rate"],
            "median_rate": stats["median_rate"],
            "mean_rate": stats["mean_rate"],
            "p75_rate": stats["p75_rate"],
            "max_rate": stats["max_rate"],
            "iqr": stats["iqr"],
            "std_dev": stats["std_dev"],
            "benchmark_procedure_weight": meta["benchmark_procedure_weight"],
            "eligibility_status": stats["eligibility_status"],
        }
        peer_summary_rows.append(row_dict)

    with open(output_peer_summary_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=peer_summary_fieldnames)
        writer.writeheader()
        writer.writerows(peer_summary_rows)

    logger.info("Wrote %d peer group summaries to %s", len(peer_summary_rows), output_peer_summary_csv)

    # ── Step 6: Provider-Level Benchmark-Weighted Fee Index ───────────────────
    provider_indexes: List[Dict[str, Any]] = []
    for (npi, tin, pname), items in provider_rollups.items():
        eligible_items = [it for it in items if it["eligibility_status"] == "ELIGIBLE" and it["relative_price_index"] != ""]
        if not eligible_items:
            continue

        total_weight = 0
        weighted_rpi_sum = 0.0
        unweighted_rpi_sum = 0.0

        for it in eligible_items:
            rpi_val = float(it["relative_price_index"])
            unweighted_rpi_sum += rpi_val
            wt_raw = it.get("benchmark_procedure_weight")
            try:
                wt = int(float(str(wt_raw).strip())) if wt_raw is not None and str(wt_raw).strip() != "" else 1
            except (ValueError, TypeError):
                wt = 1
            if wt <= 0:
                wt = 1
            weighted_rpi_sum += (rpi_val * wt)
            total_weight += wt

        weighted_rpi = round(weighted_rpi_sum / total_weight, 2) if total_weight > 0 else round(unweighted_rpi_sum / len(eligible_items), 2)
        unweighted_rpi = round(unweighted_rpi_sum / len(eligible_items), 2)

        provider_indexes.append({
            "npi": npi,
            "tin_value": tin,
            "provider_name": pname,
            "eligible_service_count": len(eligible_items),
            "benchmark_weighted_rpi": weighted_rpi,
            "unweighted_rpi": unweighted_rpi,
            "portfolio_tier": assign_cost_effectiveness_tier(weighted_rpi),
        })

    # Sort provider indexes: most competitive first
    provider_indexes.sort(key=lambda x: x["benchmark_weighted_rpi"])

    # ── Step 7: Write c7_summary.json ─────────────────────────────────────────
    eligible_rpis = [float(r["relative_price_index"]) for r in evaluated_records if r["eligibility_status"] == "ELIGIBLE"]
    rpi_stats = calculate_distribution_stats(eligible_rpis) if eligible_rpis else {}

    elapsed = round(time.time() - t0, 2)
    summary_data = {
        "metadata": {
            "pipeline_stage": "C7_RATE_COST_EFFECTIVENESS",
            "payer": "Centene Corporation (Health Net of California)",
            "target_market": "Commercial Group, California",
            "target_network": "PPO Network",
            "min_peer_count_threshold": min_peer_count,
            "execution_duration_seconds": elapsed,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "volume_summary": {
            "total_benchmark_records_evaluated": len(evaluated_records),
            "eligible_rates_scored": len(eligible_rpis),
            "eligible_rate_share_pct": round((len(eligible_rpis) / len(evaluated_records)) * 100, 2),
            "insufficient_peer_count_rates": len(evaluated_records) - len(eligible_rpis),
            "total_distinct_peer_groups": len(peer_rates),
            "eligible_peer_groups": eligible_peer_groups,
            "insufficient_peer_groups": ineligible_peer_groups,
            "unique_providers_evaluated": len(provider_rollups),
            "unique_providers_with_weighted_index": len(provider_indexes),
        },
        "cost_effectiveness_tier_distribution": dict(tier_counts),
        "relative_price_index_distribution": rpi_stats,
        "top_cost_competitive_providers": provider_indexes[:10],
        "top_high_price_providers": provider_indexes[-10:][::-1],
        "deliverables": {
            "provider_cost_effectiveness_csv": output_provider_csv,
            "peer_group_summary_csv": output_peer_summary_csv,
            "summary_json": output_summary_json,
        },
    }

    with open(output_summary_json, "w", encoding="utf-8") as fh:
        json.dump(summary_data, fh, indent=2)

    logger.info("C7 analysis complete in %.2fs. Outputs generated successfully.", elapsed)
    return summary_data


def main() -> None:
    """CLI entrypoint for Phase 7 (C7)."""
    cfg = load_config()
    setup_logging(log_level="INFO")

    analyze_cost_effectiveness(
        curated_benchmark_csv=cfg["c6_curated_benchmark_rates_csv"],
        output_provider_csv=cfg["c7_provider_cost_effectiveness_csv"],
        output_peer_summary_csv=cfg["c7_peer_group_summary_csv"],
        output_summary_json=cfg["c7_summary_json"],
        min_peer_count=cfg.get("c7_min_peer_count", 5),
    )


if __name__ == "__main__":
    main()
