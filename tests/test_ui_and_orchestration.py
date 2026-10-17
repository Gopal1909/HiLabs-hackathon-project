"""
tests/test_ui_and_orchestration.py
Unit tests verifying the master pipeline runner, dashboard UI generation,
and standard 6-column Deliverable 1 export.
"""
from __future__ import annotations

import csv
import json
import os
import openpyxl
import pytest

from run_pipeline import STAGES, verify_deliverables
from src.export_standard_deliverable import export_standard_deliverables
from src.ui import generate_dashboard_html


def test_stages_dictionary_integrity():
    """Verify that all required pipeline stages are registered in STAGES."""
    expected_keys = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "export", "ui"]
    for k in expected_keys:
        assert k in STAGES
        assert "name" in STAGES[k]
        assert "module" in STAGES[k]
        assert "desc" in STAGES[k]


def test_standard_deliverables_export(tmp_path):
    """Verify export_standard_deliverables creates exact 6-column CSV and XLSX."""
    tmp_csv = str(tmp_path / "test_standard.csv")
    tmp_sub_csv = str(tmp_path / "test_sub_standard.csv")
    tmp_xlsx = str(tmp_path / "test_standard.xlsx")
    tmp_sub_xlsx = str(tmp_path / "test_sub_standard.xlsx")

    cnt = export_standard_deliverables(
        benchmark_csv_path="outputs/c6_curated_benchmark_rates.csv",
        output_xlsx_path=tmp_xlsx,
        output_csv_path=tmp_csv,
        submission_xlsx_path=tmp_sub_xlsx,
        submission_csv_path=tmp_sub_csv,
    )
    assert cnt == 2418

    # Verify CSV headers & row count
    with open(tmp_csv, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert reader[0] == ["NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate"]
        assert len(reader) == 2419

    # Verify XLSX headers, sheet name & row count
    wb = openpyxl.load_workbook(tmp_xlsx, data_only=True)
    assert wb.sheetnames == ["Standard Rate File"]
    ws = wb["Standard Rate File"]
    assert ws.max_row == 2419
    assert ws.max_column == 6
    assert [ws.cell(1, c).value for c in range(1, 7)] == ["NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate"]


def test_interactive_dashboard_html_generation(tmp_path):
    """Verify dashboard HTML generates with required components and embedded data."""
    tmp_html = str(tmp_path / "dashboard.html")
    tmp_sub_html = str(tmp_path / "sub_dashboard.html")

    html_content = generate_dashboard_html(
        c7_rates_csv="outputs/c7_provider_cost_effectiveness.csv",
        c6_bench_csv="outputs/c6_curated_benchmark_rates.csv",
        peer_group_csv="outputs/c7_peer_group_summary.csv",
        c3_metrics_csv="outputs/c3_metric_details.csv",
        conflicts_csv="outputs/c5_address_conflicts.csv",
        summary_json_path="submission/SUMMARY.json",
        output_html_path=tmp_html,
        submission_html_path=tmp_sub_html,
    )

    assert os.path.isfile(tmp_html)
    assert os.path.isfile(tmp_sub_html)
    assert len(html_content) > 500_000  # > 500 KB

    # Check key executive and analyst tokens in HTML
    assert "Centene California PPO Rate Intelligence" in html_content
    assert "Executive View" in html_content
    assert "Analyst Rate Explorer" in html_content
    assert "qualityChart" in html_content
    assert "addressChart" in html_content
    assert "tierChart" in html_content
    assert "funnelChart" in html_content
    assert "ratesTable" in html_content
    assert "peerSelect" in html_content
    assert "conflictsTbody" in html_content
    assert "qualityTbody" in html_content
    assert "dictTbody" in html_content


def test_submission_deliverables_completeness():
    """Verify all 12 official hackathon deliverables exist in submission/ and outputs/."""
    expected = [
        "submission/curated_ppo_rates.xlsx",
        "submission/standard_curated_rates.xlsx",
        "submission/c6_curated_standard_rates.csv",
        "submission/c6_curated_benchmark_rates.csv",
        "submission/LOGIC_FILE.md",
        "submission/c3_file_quality_metrics.csv",
        "submission/c3_metric_details.csv",
        "submission/SUMMARY.json",
        "submission/SUMMARY.md",
        "submission/interactive_dashboard.html",
        "submission/c7_provider_cost_effectiveness.csv",
        "submission/c7_peer_group_summary.csv",
        "submission/c5_provider_address_crosswalk.csv",
        "submission/c5_address_conflicts.csv",
    ]
    for p in expected:
        assert os.path.isfile(p), f"Missing submission deliverable: {p}"
        assert os.path.getsize(p) > 0, f"Empty submission deliverable: {p}"
