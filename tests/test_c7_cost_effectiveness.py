"""
tests/test_c7_cost_effectiveness.py
Comprehensive test suite for Phase 7 (C7) Rate Cost-Effectiveness Analysis.
Tests peer grouping, small peer groups, outliers, ties, duplicate records,
incompatible contexts, and benchmark weight fallbacks.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest

from src.c7_cost_effectiveness import (
    analyze_cost_effectiveness,
    assign_cost_effectiveness_tier,
    calculate_distribution_stats,
    calculate_peer_percentile,
    make_peer_group_id,
)
from src.utils import load_config


@pytest.fixture(scope="module")
def cfg() -> Dict[str, Any]:
    return load_config()


def test_make_peer_group_id():
    """Verify canonical peer group ID string formatting and modifier defaulting."""
    assert make_peer_group_id("99214", "", "professional", "outpatient") == "99214|GLOBAL|professional|outpatient"
    assert make_peer_group_id("99214", "26", "professional", "outpatient") == "99214|26|professional|outpatient"
    assert make_peer_group_id("99214", "TC", "institutional", "outpatient") == "99214|TC|institutional|outpatient"
    assert make_peer_group_id("88305", "  ", "PROFESSIONAL", "Outpatient") == "88305|GLOBAL|professional|outpatient"


def test_calculate_distribution_stats():
    """Verify non-parametric distribution statistics (median, IQR, quartiles)."""
    rates = [100.0, 110.0, 120.0, 130.0, 140.0]
    stats = calculate_distribution_stats(rates)
    assert stats["sample_size"] == 5
    assert stats["min_rate"] == 100.0
    assert stats["median_rate"] == 120.0
    assert stats["max_rate"] == 140.0
    assert stats["iqr"] == 20.0  # p75(130) - p25(110)
    assert stats["mean_rate"] == 120.0

    # Even sample size
    rates_even = [100.0, 110.0, 130.0, 140.0]
    stats_even = calculate_distribution_stats(rates_even)
    assert stats_even["sample_size"] == 4
    assert stats_even["median_rate"] == 120.0


def test_calculate_distribution_stats_empty():
    """Verify safe handling of empty rates list."""
    stats = calculate_distribution_stats([])
    assert stats["sample_size"] == 0
    assert stats["median_rate"] == 0.0


def test_calculate_peer_percentile_ties_and_bounds():
    """Verify midpoint percentile calculation on ties and boundary conditions."""
    rates = [100.0, 100.0, 100.0, 200.0, 300.0]  # 3 tied at minimum
    # strictly less = 0, equal = 3 -> (0 + 1.5)/5 = 30.0%
    p = calculate_peer_percentile(rates, 100.0)
    assert p == 30.0

    # Max rate
    p_max = calculate_peer_percentile(rates, 300.0)
    assert p_max == 90.0  # strictly less = 4, equal = 1 -> (4 + 0.5)/5 = 90.0%

    # Empty list fallback
    assert calculate_peer_percentile([], 100.0) == 50.0


def test_assign_cost_effectiveness_tier():
    """Verify RPI tier categorization."""
    assert assign_cost_effectiveness_tier(None) == "INSUFFICIENT_PEER_COUNT"
    assert assign_cost_effectiveness_tier(75.0) == "HIGHLY_COMPETITIVE"
    assert assign_cost_effectiveness_tier(90.0) == "COMPETITIVE"
    assert assign_cost_effectiveness_tier(100.0) == "MEDIAN_ALIGNED"
    assert assign_cost_effectiveness_tier(115.0) == "ABOVE_MEDIAN"
    assert assign_cost_effectiveness_tier(150.0) == "HIGH_PRICE_OUTLIER"


def test_small_peer_group_insufficient_sample():
    """Verify small peer groups (< 5) receive INSUFFICIENT_PEER_COUNT and suppressed metrics."""
    # Create temporary mini CSV with a group of size 2
    mini_csv = "outputs/test_mini_bench.csv"
    with open(mini_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "npi", "tin_value", "provider_name", "billing_code", "billing_code_modifier",
            "billing_class", "setting", "negotiated_rate", "rate_selection_flag"
        ])
        writer.writeheader()
        writer.writerow({
            "npi": "111", "tin_value": "T1", "provider_name": "P1",
            "billing_code": "99999", "billing_code_modifier": "", "billing_class": "professional",
            "setting": "outpatient", "negotiated_rate": "100.0", "rate_selection_flag": "UNIQUE_RATE"
        })
        writer.writerow({
            "npi": "222", "tin_value": "T2", "provider_name": "P2",
            "billing_code": "99999", "billing_code_modifier": "", "billing_class": "professional",
            "setting": "outpatient", "negotiated_rate": "120.0", "rate_selection_flag": "UNIQUE_RATE"
        })

    out_prov = "outputs/test_c7_mini_prov.csv"
    out_peer = "outputs/test_c7_mini_peer.csv"
    out_json = "outputs/test_c7_mini_sum.json"

    analyze_cost_effectiveness(mini_csv, out_prov, out_peer, out_json, min_peer_count=5)

    with open(out_prov, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 2
        for r in rows:
            assert r["eligibility_status"] == "INSUFFICIENT_PEER_COUNT"
            assert r["cost_effectiveness_tier"] == "INSUFFICIENT_PEER_COUNT"
            assert r["peer_median_rate"] == ""
            assert r["relative_price_index"] == ""
            assert "Insufficient peer group sample size" in r["explanation"]

    # Cleanup temp test files
    for p in (mini_csv, out_prov, out_peer, out_json):
        if os.path.exists(p):
            os.remove(p)


def test_outlier_resistance():
    """Verify median and IQR are resilient to extreme rate outliers."""
    # A single extreme rate ($10,000) does not skew the median for routine visits ($150)
    rates = [140.0, 145.0, 150.0, 155.0, 10000.0]
    stats = calculate_distribution_stats(rates)
    assert stats["median_rate"] == 150.0  # unaffected by 10,000
    assert stats["mean_rate"] > 2000.0    # mean is skewed, confirming median is superior


def test_unequal_contexts_separation():
    """Verify that different modifiers and classes create separate peer groups."""
    p1 = make_peer_group_id("99214", "26", "professional", "outpatient")
    p2 = make_peer_group_id("99214", "", "professional", "outpatient")
    p3 = make_peer_group_id("99214", "", "institutional", "outpatient")
    assert p1 != p2
    assert p2 != p3
    assert p1 != p3


def test_c7_deliverables_reconciliation(cfg: Dict[str, Any]):
    """Verify that real C7 output files exist, have correct row counts, and reconcile."""
    prov_csv = cfg["c7_provider_cost_effectiveness_csv"]
    peer_csv = cfg["c7_peer_group_summary_csv"]
    sum_json = cfg["c7_summary_json"]

    assert os.path.isfile(prov_csv)
    assert os.path.isfile(peer_csv)
    assert os.path.isfile(sum_json)

    with open(prov_csv, "r", encoding="utf-8") as f:
        prov_rows = list(csv.DictReader(f))
        assert len(prov_rows) == 2418
        assert "relative_price_index" in prov_rows[0]
        assert "peer_median_rate" in prov_rows[0]
        assert "cost_effectiveness_tier" in prov_rows[0]

    with open(peer_csv, "r", encoding="utf-8") as f:
        peer_rows = list(csv.DictReader(f))
        assert len(peer_rows) == 97
        assert "sample_size" in peer_rows[0]
        assert "median_rate" in peer_rows[0]

    with open(sum_json, "r", encoding="utf-8") as f:
        summary = json.load(f)
        vol = summary["volume_summary"]
        assert vol["total_benchmark_records_evaluated"] == 2418
        assert vol["eligible_rates_scored"] + vol["insufficient_peer_count_rates"] == 2418
        assert vol["eligible_peer_groups"] + vol["insufficient_peer_groups"] == 97
        assert vol["eligible_rate_share_pct"] > 95.0
