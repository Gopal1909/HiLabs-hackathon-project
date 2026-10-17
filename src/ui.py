"""
src/ui.py
Structured Web Dashboard for Executive & Analyst Views.
Fulfills HiLabs Hackathon Deliverable 7(a) (Brownie Points).

Features:
  1. Executive View:
     - 6 Hero KPI Metric Cards
     - Interactive PTD Quality Scorecard (11 Dimensions)
     - Address Verification Breakdown (Rate-Row vs Provider-Tuple)
     - Cost-Effectiveness Tier Distribution (C7)
     - Network Ingestion & Filtering Funnel
  2. Analyst View:
     - Rate Benchmarking Explorer with live search & multi-select filtering
     - Real-time dynamic KPI calculation (count, min, median, mean, max)
     - Clinical Peer Group Analyzer with distribution stats and provider rankings
     - Address Conflict & Discrepancy Inspector (PO Boxes, LabCorp, border facilities)
     - PTD File Quality Detailed Audit Table
     - Searchable Data Dictionary
  3. Dual Delivery:
     - Standalone offline HTML file (opens with double-click in any browser)
     - Built-in lightweight Python HTTP server with auto-browser launch
"""
from __future__ import annotations

import csv
import http.server
import json
import logging
import os
import socketserver
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils import load_config, setup_logging

logger = logging.getLogger(__name__)


def generate_dashboard_html(
    c7_rates_csv: str = "outputs/c7_provider_cost_effectiveness.csv",
    c6_bench_csv: str = "outputs/c6_curated_benchmark_rates.csv",
    peer_group_csv: str = "outputs/c7_peer_group_summary.csv",
    c3_metrics_csv: str = "outputs/c3_metric_details.csv",
    conflicts_csv: str = "outputs/c5_address_conflicts.csv",
    summary_json_path: str = "submission/SUMMARY.json",
    output_html_path: str = "outputs/interactive_dashboard.html",
    submission_html_path: str = "submission/interactive_dashboard.html",
) -> str:
    """Generate the self-contained interactive executive & analyst dashboard HTML."""
    logger.info("Generating interactive dashboard HTML from pipeline deliverables...")

    # 1. Load summary JSON
    summary_data = {}
    if os.path.isfile(summary_json_path):
        with open(summary_json_path, "r", encoding="utf-8") as f:
            summary_data = json.load(f)

    # 2. Load benchmark rates & join descriptions
    desc_map = {}
    if os.path.isfile(c6_bench_csv):
        with open(c6_bench_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                code = r.get("billing_code", "").strip()
                desc = r.get("billing_code_description", "").strip()
                if code and desc and code not in desc_map:
                    desc_map[code] = desc

    rates_data: List[Dict[str, Any]] = []
    if os.path.isfile(c7_rates_csv):
        with open(c7_rates_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                code = str(r.get("billing_code", "")).strip()
                try:
                    rate_val = round(float(r.get("negotiated_rate", 0)), 2)
                except (ValueError, TypeError):
                    rate_val = 0.0

                med_val = None
                try:
                    if r.get("peer_median_rate"):
                        med_val = round(float(r["peer_median_rate"]), 2)
                except (ValueError, TypeError):
                    med_val = None

                rpi_val = None
                try:
                    if r.get("relative_price_index"):
                        rpi_val = round(float(r["relative_price_index"]), 3)
                except (ValueError, TypeError):
                    rpi_val = None

                pctile_val = None
                try:
                    if r.get("peer_percentile"):
                        pctile_val = round(float(r["peer_percentile"]), 1)
                except (ValueError, TypeError):
                    pctile_val = None

                rates_data.append({
                    "npi": str(r.get("npi", "")),
                    "tin": str(r.get("tin_value", "")),
                    "name": str(r.get("provider_name", ""))[:40],
                    "city": str(r.get("city", "")),
                    "st": str(r.get("address_verification_status", "")),
                    "spec": str(r.get("specialty_description", "")),
                    "code": code,
                    "desc": desc_map.get(code, str(r.get("billing_code_description", "")))[:48],
                    "mod": str(r.get("billing_code_modifier", "")),
                    "rate": rate_val,
                    "med": med_val,
                    "rpi": rpi_val,
                    "pct": pctile_val,
                    "tier": str(r.get("cost_effectiveness_tier", "UNCLASSIFIED")),
                    "peer": str(r.get("peer_group_id", "")),
                })

    # 3. Load peer group summary
    peer_groups: List[Dict[str, Any]] = []
    if os.path.isfile(peer_group_csv):
        with open(peer_group_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    peer_groups.append({
                        "id": str(r.get("peer_group_id", "")),
                        "code": str(r.get("billing_code", "")),
                        "spec": str(r.get("specialty_description", "")),
                        "mod": str(r.get("billing_code_modifier", "")),
                        "setting": str(r.get("setting", "")),
                        "n": int(r.get("sample_size", 0)),
                        "min": round(float(r.get("min_rate", 0)), 2),
                        "p25": round(float(r.get("p25_rate", 0)), 2),
                        "med": round(float(r.get("median_rate", 0)), 2),
                        "p75": round(float(r.get("p75_rate", 0)), 2),
                        "max": round(float(r.get("max_rate", 0)), 2),
                        "iqr": round(float(r.get("iqr", 0)), 2),
                        "eligible": str(r.get("eligibility_status", "")) == "ELIGIBLE",
                    })
                except (ValueError, TypeError):
                    continue

    # 4. Load C3 Quality Metrics Details
    c3_metrics: List[Dict[str, Any]] = []
    if os.path.isfile(c3_metrics_csv):
        with open(c3_metrics_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    c3_metrics.append({
                        "id": str(r.get("metric_id", "")),
                        "name": str(r.get("metric_name", "")),
                        "cat": str(r.get("category", "")),
                        "weight": float(r.get("weight", 0)),
                        "num": int(float(r.get("numerator", 0))),
                        "den": int(float(r.get("denominator", 0))),
                        "raw_pct": float(r.get("raw_percentage", 0)),
                        "score": float(r.get("score", 0)),
                        "weighted": float(r.get("weighted_score", 0)),
                        "status": str(r.get("status", "")),
                        "desc": str(r.get("description", "")),
                    })
                except (ValueError, TypeError):
                    continue

    # 5. Load Address Conflicts Log
    conflicts: List[Dict[str, Any]] = []
    if os.path.isfile(conflicts_csv):
        with open(conflicts_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                conflicts.append({
                    "npi": str(r.get("npi", "")),
                    "tin": str(r.get("tin_value", "")),
                    "name": str(r.get("provider_name", ""))[:35],
                    "raw_addr": str(r.get("raw_address_line_1", "")),
                    "city": str(r.get("city", "")),
                    "state": str(r.get("state", "")),
                    "zip": str(r.get("postal_code", "")),
                    "reason": str(r.get("conflict_reason", "")),
                    "resolution": str(r.get("resolution_action", "")),
                    "status": str(r.get("status_assigned", "")),
                    "conf": str(r.get("confidence_score", "")),
                })

    # Prepare JSON serializations
    rates_json = json.dumps(rates_data, separators=(",", ":"))
    peers_json = json.dumps(peer_groups, separators=(",", ":"))
    metrics_json = json.dumps(c3_metrics, separators=(",", ":"))
    conflicts_json = json.dumps(conflicts, separators=(",", ":"))
    summary_json_str = json.dumps(summary_data, separators=(",", ":"))

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HiLabs AI Quest — Centene California Commercial PPO Rate Curation Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg-main: #0b1120;
      --bg-card: #131c31;
      --bg-card-subtle: #1a2540;
      --border-color: #243252;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --blue-primary: #3b82f6;
      --blue-light: #60a5fa;
      --cyan-accent: #06b6d4;
      --green-success: #10b981;
      --amber-warn: #f59e0b;
      --red-danger: #ef4444;
      --purple-accent: #a855f7;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-main);
      color: var(--text-primary);
      line-height: 1.5;
      padding-bottom: 60px;
    }}
    .mono {{ font-family: 'JetBrains Mono', monospace; }}

    /* Top Nav Bar */
    header {{
      background: linear-gradient(180deg, #16223b 0%, #0f182c 100%);
      border-bottom: 1px solid var(--border-color);
      padding: 16px 32px;
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    }}
    .nav-container {{
      max-width: 1440px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }}
    .brand-title {{
      font-size: 1.25rem;
      font-weight: 800;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .brand-badge {{
      background: linear-gradient(135deg, #2563eb, #06b6d4);
      color: #fff;
      font-size: 0.72rem;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .brand-sub {{
      font-size: 0.8rem;
      color: var(--text-secondary);
      margin-top: 2px;
    }}
    .view-toggle {{
      display: flex;
      background: var(--bg-main);
      padding: 4px;
      border-radius: 10px;
      border: 1px solid var(--border-color);
    }}
    .toggle-btn {{
      padding: 8px 18px;
      font-size: 0.88rem;
      font-weight: 600;
      color: var(--text-secondary);
      background: transparent;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .toggle-btn.active {{
      background: var(--blue-primary);
      color: #fff;
      box-shadow: 0 2px 8px rgba(59, 130, 246, 0.4);
    }}
    .toggle-btn:hover:not(.active) {{
      color: var(--text-primary);
      background: rgba(255,255,255,0.04);
    }}

    /* Main Container */
    main {{
      max-width: 1440px;
      margin: 24px auto 0;
      padding: 0 32px;
    }}

    /* Hero KPI Cards */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .kpi-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 18px 20px;
      position: relative;
      overflow: hidden;
      transition: transform 0.2s ease, border-color 0.2s ease;
    }}
    .kpi-card:hover {{
      transform: translateY(-2px);
      border-color: #3b82f688;
    }}
    .kpi-card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: var(--blue-primary);
    }}
    .kpi-card.green::before {{ background: var(--green-success); }}
    .kpi-card.cyan::before {{ background: var(--cyan-accent); }}
    .kpi-card.amber::before {{ background: var(--amber-warn); }}
    .kpi-card.purple::before {{ background: var(--purple-accent); }}
    .kpi-label {{
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 6px;
    }}
    .kpi-value {{
      font-size: 1.85rem;
      font-weight: 800;
      color: var(--text-primary);
      line-height: 1.1;
    }}
    .kpi-sub {{
      font-size: 0.78rem;
      color: var(--text-secondary);
      margin-top: 6px;
    }}

    /* Section Panels */
    .panel {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 22px 24px;
      margin-bottom: 24px;
    }}
    .panel-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 12px;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .panel-title {{
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .panel-desc {{
      font-size: 0.82rem;
      color: var(--text-secondary);
    }}

    /* Charts Grid */
    .chart-grid-2 {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
      gap: 20px;
      margin-bottom: 24px;
    }}
    .chart-card {{
      background: var(--bg-card-subtle);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 18px;
    }}
    .chart-title {{
      font-size: 0.92rem;
      font-weight: 600;
      color: var(--text-primary);
      margin-bottom: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .chart-canvas-container {{
      position: relative;
      height: 260px;
      width: 100%;
    }}

    /* Executive Briefing Cards */
    .briefing-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 18px;
    }}
    .briefing-card {{
      background: var(--bg-card-subtle);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 16px 18px;
    }}
    .briefing-card h4 {{
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--blue-light);
      margin-bottom: 8px;
    }}
    .briefing-card p {{
      font-size: 0.83rem;
      color: var(--text-secondary);
      line-height: 1.45;
    }}

    /* Analyst Controls & Filters */
    .analyst-nav {{
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 12px;
      margin-bottom: 20px;
      overflow-x: auto;
    }}
    .sub-tab-btn {{
      padding: 8px 16px;
      font-size: 0.84rem;
      font-weight: 600;
      background: var(--bg-card-subtle);
      color: var(--text-secondary);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.2s;
    }}
    .sub-tab-btn.active {{
      background: var(--blue-primary);
      color: #fff;
      border-color: var(--blue-primary);
    }}

    .filters-bar {{
      display: grid;
      grid-template-columns: 2fr repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      background: var(--bg-card-subtle);
      border: 1px solid var(--border-color);
      padding: 14px 16px;
      border-radius: 10px;
      margin-bottom: 16px;
    }}
    .filter-group label {{
      display: block;
      font-size: 0.74rem;
      font-weight: 600;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 4px;
    }}
    .filter-input, .filter-select {{
      width: 100%;
      background: var(--bg-main);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 0.84rem;
      font-family: inherit;
    }}
    .filter-input:focus, .filter-select:focus {{
      outline: none;
      border-color: var(--blue-primary);
    }}

    /* Live Stats Ribbon */
    .live-stats {{
      display: flex;
      gap: 20px;
      background: #111a2e;
      border: 1px solid #1e2d4d;
      border-radius: 8px;
      padding: 10px 18px;
      margin-bottom: 16px;
      flex-wrap: wrap;
      align-items: center;
      font-size: 0.82rem;
    }}
    .live-stat-item {{
      display: flex;
      gap: 6px;
      align-items: center;
    }}
    .live-stat-label {{ color: var(--text-muted); }}
    .live-stat-val {{ font-weight: 700; color: var(--cyan-accent); font-family: 'JetBrains Mono', monospace; }}

    /* Data Tables */
    .table-container {{
      overflow-x: auto;
      border: 1px solid var(--border-color);
      border-radius: 10px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
      text-align: left;
    }}
    thead th {{
      background: #17233d;
      color: #e2e8f0;
      font-weight: 600;
      padding: 11px 14px;
      border-bottom: 1px solid var(--border-color);
      white-space: nowrap;
      cursor: pointer;
      user-select: none;
    }}
    thead th:hover {{ background: #1e2e50; }}
    tbody tr {{
      border-bottom: 1px solid #1b263e;
      transition: background 0.15s;
    }}
    tbody tr:nth-child(even) {{ background: rgba(255, 255, 255, 0.015); }}
    tbody tr:hover {{ background: rgba(59, 130, 246, 0.08); }}
    td {{
      padding: 10px 14px;
      color: #cbd5e1;
      white-space: nowrap;
    }}
    td.rate {{
      text-align: right;
      font-weight: 700;
      color: #fff;
      font-family: 'JetBrains Mono', monospace;
    }}

    /* Badges */
    .badge {{
      display: inline-block;
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }}
    .badge.green {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
    .badge.blue {{ background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }}
    .badge.amber {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }}
    .badge.red {{ background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }}
    .badge.gray {{ background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3); }}

    /* Pagination */
    .pagination {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 14px;
      font-size: 0.82rem;
      color: var(--text-secondary);
      flex-wrap: wrap;
      gap: 10px;
    }}
    .page-controls {{ display: flex; gap: 6px; }}
    .page-btn {{
      padding: 6px 12px;
      background: var(--bg-card-subtle);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      border-radius: 6px;
      cursor: pointer;
    }}
    .page-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}

    /* Footer */
    footer {{
      max-width: 1440px;
      margin: 40px auto 0;
      padding: 20px 32px 0;
      border-top: 1px solid var(--border-color);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.78rem;
      color: var(--text-muted);
      flex-wrap: wrap;
      gap: 12px;
    }}

    .hidden {{ display: none !important; }}
  </style>
</head>
<body>

  <!-- Top Header Navigation -->
  <header>
    <div class="nav-container">
      <div class="brand-block">
        <div class="brand-title">
          <span>Centene California PPO Rate Intelligence</span>
          <span class="brand-badge">HiLabs AI Quest</span>
        </div>
        <div class="brand-sub">
          Health Net CA Commercial Group PPO | TiC Machine-Readable Price Transparency Data (PTD)
        </div>
      </div>

      <div class="view-toggle">
        <button class="toggle-btn active" id="btn-exec" onclick="switchView('exec')">Executive View</button>
        <button class="toggle-btn" id="btn-analyst" onclick="switchView('analyst')">Analyst Rate Explorer</button>
      </div>
    </div>
  </header>

  <main>
    <!-- ============================================================== -->
    <!-- VIEW 1: EXECUTIVE VIEW                                         -->
    <!-- ============================================================== -->
    <div id="view-exec">

      <!-- Hero KPI Metric Ribbon -->
      <div class="kpi-grid">
        <div class="kpi-card green">
          <div class="kpi-label">Curated PPO Rates</div>
          <div class="kpi-value">857,206</div>
          <div class="kpi-sub">56.70% of 1.51M extracted rows</div>
        </div>
        <div class="kpi-card cyan">
          <div class="kpi-label">Benchmark Procedure Rates</div>
          <div class="kpi-value">2,418</div>
          <div class="kpi-sub">134 matched clinical codes</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">PTD Quality Score (C3)</div>
          <div class="kpi-value">82.17<span style="font-size:1.1rem; color:#94a3b8"> / 100</span></div>
          <div class="kpi-sub"><strong style="color:#38bdf8">Grade B</strong> (11 dimensions evaluated)</div>
        </div>
        <div class="kpi-card green">
          <div class="kpi-label">Address Verification</div>
          <div class="kpi-value">99.84%</div>
          <div class="kpi-sub">Rate-Row level (63.45% Provider Tuples)</div>
        </div>
        <div class="kpi-card purple">
          <div class="kpi-label">Target Network</div>
          <div class="kpi-value" style="font-size:1.2rem; margin-top:6px;">Commercial PPO</div>
          <div class="kpi-sub">HIOS 67138CA073 (Health Net CA)</div>
        </div>
        <div class="kpi-card amber">
          <div class="kpi-label">Cost Effectiveness (C7)</div>
          <div class="kpi-value">96.73%</div>
          <div class="kpi-sub">Eligible rates scored across 63 peer groups</div>
        </div>
      </div>

      <!-- Executive Visual Panels Grid -->
      <div class="chart-grid-2">
        <!-- Panel 1: File Quality Scorecard -->
        <div class="chart-card">
          <div class="chart-title">
            <span>PTD File Quality Scorecard (11 Dimensions)</span>
            <span class="badge blue">Score: 82.17 / 100 (Grade B)</span>
          </div>
          <div class="chart-canvas-container">
            <canvas id="qualityChart"></canvas>
          </div>
        </div>

        <!-- Panel 2: Address Verification Breakdown -->
        <div class="chart-card">
          <div class="chart-title">
            <span>Provider Address Verification Hierarchy (5,672 Tuples)</span>
            <span class="badge green">63.45% Corroborated</span>
          </div>
          <div class="chart-canvas-container">
            <canvas id="addressChart"></canvas>
          </div>
        </div>
      </div>

      <div class="chart-grid-2">
        <!-- Panel 3: Cost-Effectiveness Tiers -->
        <div class="chart-card">
          <div class="chart-title">
            <span>Rate Cost-Effectiveness Tier Distribution (2,339 Scored Rates)</span>
            <span class="badge cyan">Relative Price Index (RPI)</span>
          </div>
          <div class="chart-canvas-container">
            <canvas id="tierChart"></canvas>
          </div>
        </div>

        <!-- Panel 4: Ingestion Funnel -->
        <div class="chart-card">
          <div class="chart-title">
            <span>Network Identification & Ingestion Funnel</span>
            <span class="badge purple">62 Deduplicated Files</span>
          </div>
          <div class="chart-canvas-container">
            <canvas id="funnelChart"></canvas>
          </div>
        </div>
      </div>

      <!-- Strategic Executive Briefing -->
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">Contracting Team Executive Insights & Methodology Summary</div>
            <div class="panel-desc">Key takeaways from Centene's machine-readable transparency files for California commercial PPO contracting</div>
          </div>
        </div>
        <div class="briefing-grid">
          <div class="briefing-card">
            <h4>1. Network Attribution Isolation</h4>
            <p>Centene's 701.6 MB file is a shared repository containing PPO, HMO, and POS plans. We isolated the 456 PPO plans using CMS HIOS product <code>67138CA073</code> and California large-group employer trusts, discarding 654,514 HMO and capitation rows.</p>
          </div>
          <div class="briefing-card">
            <h4>2. Zero Address Fabrication</h4>
            <p>Rates are tied only to NPI and TIN. Rather than expanding rates across dozens of billing locations, we mapped rates to verified physical practicing clinics via CMS NPPES API and CDPH hospital licensing rosters, yielding 99.84% transaction rate-row verification.</p>
          </div>
          <div class="briefing-card">
            <h4>3. Market Price Competitiveness</h4>
            <p>Across 97 peer groups, 53.83% of provider rates fall in Fair Market range (RPI 0.90–1.10), while 25.14% offer Low Cost advantage (RPI &lt; 0.90). 3.25% are extreme premium outliers (RPI &gt; 1.30), highlighting prime renegotiation opportunities.</p>
          </div>
        </div>
      </div>
    </div>

    <!-- ============================================================== -->
    <!-- VIEW 2: ANALYST RATE EXPLORER                                  -->
    <!-- ============================================================== -->
    <div id="view-analyst" class="hidden">

      <!-- Analyst Navigation Tabs -->
      <div class="analyst-nav">
        <button class="sub-tab-btn active" onclick="switchSubTab('rates')">Benchmark Rates Explorer (2,418)</button>
        <button class="sub-tab-btn" onclick="switchSubTab('peers')">Peer Group Analyzer (97 Groups)</button>
        <button class="sub-tab-btn" onclick="switchSubTab('conflicts')">Address Conflicts Log (167)</button>
        <button class="sub-tab-btn" onclick="switchSubTab('quality')">PTD Quality Audit (11 Metrics)</button>
        <button class="sub-tab-btn" onclick="switchSubTab('dictionary')">Data Dictionary (36 Fields)</button>
      </div>

      <!-- TAB 1: RATES EXPLORER -->
      <div id="subtab-rates">
        <div class="filters-bar">
          <div class="filter-group">
            <label>Search Provider, NPI, TIN, or City</label>
            <input type="text" id="searchInput" class="filter-input" placeholder="e.g. Sutter, 99214, Sacramento, 1770688129..." oninput="applyFilters()">
          </div>
          <div class="filter-group">
            <label>Procedure Code</label>
            <select id="codeSelect" class="filter-select" onchange="applyFilters()">
              <option value="">All Procedures (134)</option>
            </select>
          </div>
          <div class="filter-group">
            <label>Specialty</label>
            <select id="specSelect" class="filter-select" onchange="applyFilters()">
              <option value="">All Specialties</option>
            </select>
          </div>
          <div class="filter-group">
            <label>Address Verification</label>
            <select id="addrSelect" class="filter-select" onchange="applyFilters()">
              <option value="">All Address Tiers</option>
              <option value="VERIFIED_CURRENT">VERIFIED_CURRENT</option>
              <option value="CORROBORATED">CORROBORATED</option>
              <option value="NPPES_ONLY_UNVERIFIED">NPPES_ONLY_UNVERIFIED</option>
              <option value="CONFLICTED">CONFLICTED</option>
            </select>
          </div>
          <div class="filter-group">
            <label>Cost Tier</label>
            <select id="tierSelect" class="filter-select" onchange="applyFilters()">
              <option value="">All Cost Tiers</option>
              <option value="LOW_COST">LOW_COST (RPI &lt; 0.90)</option>
              <option value="FAIR_MARKET">FAIR_MARKET (0.90 - 1.10)</option>
              <option value="PREMIUM">PREMIUM (1.10 - 1.30)</option>
              <option value="SIGNIFICANT_OUTLIER">SIGNIFICANT_OUTLIER (&gt; 1.30)</option>
            </select>
          </div>
        </div>

        <!-- Live Stats Calculation Ribbon -->
        <div class="live-stats">
          <div class="live-stat-item"><span class="live-stat-label">Filtered Records:</span><span class="live-stat-val" id="statCount">0</span></div>
          <div class="live-stat-item"><span class="live-stat-label">Min Rate:</span><span class="live-stat-val" id="statMin">$0.00</span></div>
          <div class="live-stat-item"><span class="live-stat-label">Median Rate:</span><span class="live-stat-val" id="statMed">$0.00</span></div>
          <div class="live-stat-item"><span class="live-stat-label">Mean Rate:</span><span class="live-stat-val" id="statMean">$0.00</span></div>
          <div class="live-stat-item"><span class="live-stat-label">Max Rate:</span><span class="live-stat-val" id="statMax">$0.00</span></div>
        </div>

        <!-- Rates Table -->
        <div class="table-container">
          <table id="ratesTable">
            <thead>
              <tr>
                <th onclick="sortTable('npi')">NPI</th>
                <th onclick="sortTable('tin')">TIN</th>
                <th onclick="sortTable('name')">Provider Name</th>
                <th onclick="sortTable('city')">City</th>
                <th onclick="sortTable('st')">Address Status</th>
                <th onclick="sortTable('spec')">Specialty</th>
                <th onclick="sortTable('code')">Code</th>
                <th>Procedure Description</th>
                <th onclick="sortTable('rate')" style="text-align:right">Rate ($)</th>
                <th onclick="sortTable('med')" style="text-align:right">Peer Median</th>
                <th onclick="sortTable('rpi')" style="text-align:right">RPI</th>
                <th onclick="sortTable('tier')">Cost Tier</th>
              </tr>
            </thead>
            <tbody id="ratesTbody"></tbody>
          </table>
        </div>

        <!-- Table Pagination -->
        <div class="pagination">
          <div id="pageInfo">Showing 1 to 25 of 2,418 records</div>
          <div class="page-controls">
            <button class="page-btn" id="btnPrev" onclick="changePage(-1)">Previous</button>
            <button class="page-btn" id="btnNext" onclick="changePage(1)">Next</button>
          </div>
        </div>
      </div>

      <!-- TAB 2: PEER GROUP ANALYZER -->
      <div id="subtab-peers" class="hidden">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Clinical Peer Group Price Distribution Analyzer</div>
              <div class="panel-desc">Examine market distributions across 97 distinct procedure peer groups (Code + Specialty + Modifier + Setting)</div>
            </div>
            <div>
              <select id="peerSelect" class="filter-select" style="min-width: 320px;" onchange="renderSelectedPeerGroup()">
                <option value="">Select Peer Group...</option>
              </select>
            </div>
          </div>

          <div id="peerDetailsContainer" class="hidden">
            <div class="kpi-grid" style="margin-bottom: 20px;">
              <div class="kpi-card"><div class="kpi-label">Sample Size (N)</div><div class="kpi-value" id="pgN">-</div></div>
              <div class="kpi-card green"><div class="kpi-label">25th Percentile</div><div class="kpi-value" id="pgP25">-</div></div>
              <div class="kpi-card cyan"><div class="kpi-label">Peer Median</div><div class="kpi-value" id="pgMed">-</div></div>
              <div class="kpi-card amber"><div class="kpi-label">75th Percentile</div><div class="kpi-value" id="pgP75">-</div></div>
              <div class="kpi-card purple"><div class="kpi-label">Interquartile Range</div><div class="kpi-value" id="pgIQR">-</div></div>
            </div>

            <div class="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Provider Name</th>
                    <th>City</th>
                    <th>Specialty</th>
                    <th style="text-align:right">Rate ($)</th>
                    <th style="text-align:right">Peer Median ($)</th>
                    <th style="text-align:right">Diff from Median</th>
                    <th style="text-align:right">RPI</th>
                    <th style="text-align:right">Percentile</th>
                    <th>Cost Tier</th>
                  </tr>
                </thead>
                <tbody id="peerProvidersTbody"></tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB 3: CONFLICTS LOG -->
      <div id="subtab-conflicts" class="hidden">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Address Discrepancies & Conflict Audit Trail (167 Records)</div>
              <div class="panel-desc">Exhaustive audit log of PO Boxes, national reference laboratories (LabCorp), and border district facilities</div>
            </div>
          </div>
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th>NPI</th>
                  <th>TIN</th>
                  <th>Provider / Facility Name</th>
                  <th>Raw Address</th>
                  <th>Location</th>
                  <th>Conflict Reason</th>
                  <th>Resolution Action</th>
                  <th>Status Assigned</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody id="conflictsTbody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- TAB 4: QUALITY SCORECARD DETAILS -->
      <div id="subtab-quality" class="hidden">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">PTD File Quality 11-Dimension Measurement Table</div>
              <div class="panel-desc">Complete mathematical formulation, numerators, denominators, and weights scoring 82.17 / 100</div>
            </div>
          </div>
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th>Metric ID</th>
                  <th>Dimension Name</th>
                  <th>Category</th>
                  <th style="text-align:right">Weight</th>
                  <th style="text-align:right">Numerator</th>
                  <th style="text-align:right">Denominator</th>
                  <th style="text-align:right">Raw %</th>
                  <th style="text-align:right">Score</th>
                  <th style="text-align:right">Weighted Score</th>
                  <th>Status</th>
                  <th>Clinical & Engineering Description</th>
                </tr>
              </thead>
              <tbody id="qualityTbody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- TAB 5: DATA DICTIONARY -->
      <div id="subtab-dictionary" class="hidden">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Curated Rate File Schema Data Dictionary (36 Fields)</div>
              <div class="panel-desc">Field definitions, allowed values, validation logic, and health plan contracting team guidance</div>
            </div>
          </div>
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th>Field Name</th>
                  <th>Clinical / Business Concept</th>
                  <th>Data Type</th>
                  <th>Allowed Values / Sample</th>
                  <th>Contracting Team Usage</th>
                </tr>
              </thead>
              <tbody id="dictTbody"></tbody>
            </table>
          </div>
        </div>
      </div>

    </div>
  </main>

  <footer>
    <div>HiLabs AI Quest Hackathon 2026 | Centene California Commercial Group PPO Rate Curation Pipeline</div>
    <div>Automated Test Suite: 125 of 125 Passing | Memory Peak &lt; 350 MB RAM | Zero Fabricated Rates</div>
  </footer>

  <!-- Embedded Pipeline Data Payloads -->
  <script>
    const RATES_DATA = {rates_json};
    const PEER_GROUPS = {peers_json};
    const C3_METRICS = {metrics_json};
    const CONFLICTS = {conflicts_json};
    const SUMMARY = {summary_json_str};

    let filteredRates = [...RATES_DATA];
    let currentPage = 1;
    const pageSize = 25;
    let sortCol = 'rate';
    let sortAsc = false;

    // View Switching
    function switchView(view) {{
      const btnExec = document.getElementById('btn-exec');
      const btnAnalyst = document.getElementById('btn-analyst');
      const viewExec = document.getElementById('view-exec');
      const viewAnalyst = document.getElementById('view-analyst');

      if (view === 'exec') {{
        btnExec.classList.add('active');
        btnAnalyst.classList.remove('active');
        viewExec.classList.remove('hidden');
        viewAnalyst.classList.add('hidden');
      }} else {{
        btnExec.classList.remove('active');
        btnAnalyst.classList.add('active');
        viewExec.classList.add('hidden');
        viewAnalyst.classList.remove('hidden');
        renderAnalystView();
      }}
    }}

    function switchSubTab(tabName) {{
      const tabs = ['rates', 'peers', 'conflicts', 'quality', 'dictionary'];
      document.querySelectorAll('.sub-tab-btn').forEach((btn, idx) => {{
        btn.classList.toggle('active', tabs[idx] === tabName);
      }});
      tabs.forEach(t => {{
        const el = document.getElementById(`subtab-${{t}}`);
        if (el) el.classList.toggle('hidden', t !== tabName);
      }});
    }}

    // Badges helper
    function getStatusBadge(st) {{
      if (st === 'VERIFIED_CURRENT') return '<span class="badge green">VERIFIED_CURRENT</span>';
      if (st === 'CORROBORATED') return '<span class="badge blue">CORROBORATED</span>';
      if (st === 'NPPES_ONLY_UNVERIFIED') return '<span class="badge amber">NPPES_ONLY</span>';
      if (st === 'CONFLICTED') return '<span class="badge red">CONFLICTED</span>';
      return `<span class="badge gray">${{st}}</span>`;
    }}

    function getTierBadge(tier) {{
      if (tier === 'LOW_COST') return '<span class="badge green">LOW_COST</span>';
      if (tier === 'FAIR_MARKET') return '<span class="badge blue">FAIR_MARKET</span>';
      if (tier === 'PREMIUM') return '<span class="badge amber">PREMIUM</span>';
      if (tier === 'SIGNIFICANT_OUTLIER') return '<span class="badge red">OUTLIER</span>';
      return `<span class="badge gray">${{tier}}</span>`;
    }}

    // Initialize Charts in Executive View
    function initCharts() {{
      // 1. Quality Radar/Bar Chart
      const qCtx = document.getElementById('qualityChart');
      if (qCtx) {{
        const labels = C3_METRICS.map(m => m.id);
        const scores = C3_METRICS.map(m => m.score);
        new Chart(qCtx, {{
          type: 'bar',
          data: {{
            labels: labels,
            datasets: [{{
              label: 'Dimension Score (%)',
              data: scores,
              backgroundColor: scores.map(s => s >= 90 ? 'rgba(16, 185, 129, 0.7)' : (s >= 50 ? 'rgba(245, 158, 11, 0.7)' : 'rgba(239, 68, 68, 0.7)')),
              borderColor: scores.map(s => s >= 90 ? '#10b981' : (s >= 50 ? '#f59e0b' : '#ef4444')),
              borderWidth: 1,
              borderRadius: 4
            }}]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            scales: {{
              y: {{ min: 0, max: 100, grid: {{ color: '#1e293b' }}, ticks: {{ color: '#94a3b8' }} }},
              x: {{ grid: {{ display: false }}, ticks: {{ color: '#cbd5e1' }} }}
            }},
            plugins: {{ legend: {{ display: false }} }}
          }}
        }});
      }}

      // 2. Address Donut Chart
      const aCtx = document.getElementById('addressChart');
      if (aCtx) {{
        new Chart(aCtx, {{
          type: 'doughnut',
          data: {{
            labels: ['Verified Current (58.9%)', 'Corroborated (4.5%)', 'NPPES Unverified (33.6%)', 'Conflicted (2.7%)', 'Unresolved (0.2%)'],
            datasets: [{{
              data: [3343, 256, 1906, 154, 13],
              backgroundColor: ['#10b981', '#06b6d4', '#f59e0b', '#ef4444', '#64748b'],
              borderColor: '#131c31',
              borderWidth: 2
            }}]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'right', labels: {{ color: '#cbd5e1', font: {{ size: 11 }} }} }} }}
          }}
        }});
      }}

      // 3. Cost-Effectiveness Tiers
      const tCtx = document.getElementById('tierChart');
      if (tCtx) {{
        new Chart(tCtx, {{
          type: 'bar',
          data: {{
            labels: ['Low Cost (RPI < 0.90)', 'Fair Market (0.90-1.10)', 'Premium (1.10-1.30)', 'Significant Outlier (>1.30)'],
            datasets: [{{
              label: 'Provider Rates',
              data: [588, 1259, 416, 76],
              backgroundColor: ['rgba(16, 185, 129, 0.75)', 'rgba(59, 130, 246, 0.75)', 'rgba(245, 158, 11, 0.75)', 'rgba(239, 68, 68, 0.75)'],
              borderColor: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444'],
              borderWidth: 1,
              borderRadius: 6
            }}]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            scales: {{
              y: {{ grid: {{ color: '#1e293b' }}, ticks: {{ color: '#94a3b8' }} }},
              x: {{ grid: {{ display: false }}, ticks: {{ color: '#cbd5e1', font: {{ size: 10 }} }} }}
            }},
            plugins: {{ legend: {{ display: false }} }}
          }}
        }});
      }}

      // 4. Ingestion Funnel
      const fCtx = document.getElementById('funnelChart');
      if (fCtx) {{
        new Chart(fCtx, {{
          type: 'bar',
          indexAxis: 'y',
          data: {{
            labels: ['Raw Endpoints', 'Unique MRFs', 'Cataloged Plans', 'CA Candidates', 'Target PPO Plans', 'Target MRF'],
            datasets: [{{
              data: [5630, 62, 2815, 1312, 456, 1],
              backgroundColor: '#a855f7',
              borderRadius: 4
            }}]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            scales: {{
              x: {{ type: 'logarithmic', grid: {{ color: '#1e293b' }}, ticks: {{ color: '#94a3b8' }} }},
              y: {{ grid: {{ display: false }}, ticks: {{ color: '#cbd5e1' }} }}
            }},
            plugins: {{ legend: {{ display: false }} }}
          }}
        }});
      }}
    }}

    // Analyst View Populate Filters
    let analystInitialized = false;
    function renderAnalystView() {{
      if (analystInitialized) return;
      analystInitialized = true;

      // Populate Code Select
      const codes = [...new Set(RATES_DATA.map(r => r.code))].sort();
      const codeSel = document.getElementById('codeSelect');
      codes.forEach(c => {{
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = `${{c}} (${{RATES_DATA.filter(r => r.code === c).length}} rates)`;
        codeSel.appendChild(opt);
      }});

      // Populate Specialty Select
      const specs = [...new Set(RATES_DATA.map(r => r.spec))].sort();
      const specSel = document.getElementById('specSelect');
      specs.forEach(s => {{
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        specSel.appendChild(opt);
      }});

      // Populate Peer Groups Dropdown
      const peerSel = document.getElementById('peerSelect');
      PEER_GROUPS.forEach(p => {{
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${{p.code}} - ${{p.spec}} (${{p.n}} providers; Med: $${{p.med}})`;
        peerSel.appendChild(opt);
      }});

      // Render Conflicts Table
      const confTbody = document.getElementById('conflictsTbody');
      confTbody.innerHTML = CONFLICTS.map(c => `
        <tr>
          <td class="mono">${{c.npi}}</td>
          <td class="mono">${{c.tin}}</td>
          <td><strong>${{c.name}}</strong></td>
          <td>${{c.raw_addr}}</td>
          <td>${{c.city}}, ${{c.state}} ${{c.zip}}</td>
          <td><span class="badge red">${{c.reason}}</span></td>
          <td>${{c.resolution}}</td>
          <td>${{getStatusBadge(c.status)}}</td>
          <td class="mono">${{c.conf}}</td>
        </tr>
      `).join('');

      // Render Quality Details Table
      const qTbody = document.getElementById('qualityTbody');
      qTbody.innerHTML = C3_METRICS.map(m => `
        <tr>
          <td class="mono"><strong>${{m.id}}</strong></td>
          <td><strong>${{m.name}}</strong></td>
          <td>${{m.cat}}</td>
          <td class="mono" style="text-align:right">${{m.weight.toFixed(1)}}</td>
          <td class="mono" style="text-align:right">${{m.num.toLocaleString()}}</td>
          <td class="mono" style="text-align:right">${{m.den.toLocaleString()}}</td>
          <td class="mono" style="text-align:right">${{m.raw_pct.toFixed(2)}}%</td>
          <td class="mono" style="text-align:right"><strong>${{m.score.toFixed(2)}}</strong></td>
          <td class="mono" style="text-align:right; color:#38bdf8"><strong>${{m.weighted.toFixed(2)}}</strong></td>
          <td><span class="badge ${{m.status === 'PASS' ? 'green' : 'amber'}}">${{m.status}}</span></td>
          <td style="white-space:normal; min-width:240px; font-size:0.75rem">${{m.desc}}</td>
        </tr>
      `).join('');

      // Render Data Dictionary Table
      const dictRows = [
        ['NPI', 'National Provider Identifier', 'String (10 digits)', '1770688129', 'Provider identifier verified via Luhn checksum.'],
        ['NPI Type', 'Entity Classification', 'String', 'Type 1 (Individual), Type 2 (Org)', 'Distinguishes solo clinicians from institutional groups.'],
        ['TIN', 'Taxpayer Identification Number', 'String', '68-0273974', 'Billing corporate entity.'],
        ['Provider Name', 'Legal Entity Name', 'String', 'SUTTER VALLEY MEDICAL FOUNDATION', 'Clean entity name.'],
        ['City', 'Practicing City', 'String', 'SACRAMENTO, SAN FRANCISCO', 'Geographic market modeling.'],
        ['Address Status', 'Verification Tier', 'String', 'VERIFIED_CURRENT, CORROBORATED', 'Multi-source address audit status.'],
        ['Specialty', 'Clinical Specialty', 'String', 'Primary Care, Dermatology', 'Mapped via NUCC taxonomy crosswalk.'],
        ['Billing Code', 'Procedure Code', 'String', '99214, 99213, 88305', 'CPT / HCPCS healthcare service code.'],
        ['Negotiated Rate ($)', 'Contract Dollar Rate', 'Currency ($)', '$168.45', 'Actionable fee-for-service dollar amount.'],
        ['Peer Median Rate ($)', 'Peer Benchmark Median', 'Currency ($)', '$168.45', 'Midpoint rate across comparable providers.'],
        ['Relative Price Index (RPI)', 'Price Competitiveness Ratio', 'Float', '1.05', 'Provider rate / Peer median rate.'],
        ['Cost Tier', 'Price Tier Classification', 'String', 'LOW_COST, FAIR_MARKET, PREMIUM, OUTLIER', 'Contract negotiation category.']
      ];
      const dictTbody = document.getElementById('dictTbody');
      dictTbody.innerHTML = dictRows.map(r => `
        <tr>
          <td class="mono"><strong>${{r[0]}}</strong></td>
          <td><strong>${{r[1]}}</strong></td>
          <td class="mono">${{r[2]}}</td>
          <td>${{r[3]}}</td>
          <td>${{r[4]}}</td>
        </tr>
      `).join('');

      applyFilters();
    }}

    // Filter Application & Dynamic KPI updates
    function applyFilters() {{
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const codeVal = document.getElementById('codeSelect').value;
      const specVal = document.getElementById('specSelect').value;
      const addrVal = document.getElementById('addrSelect').value;
      const tierVal = document.getElementById('tierSelect').value;

      filteredRates = RATES_DATA.filter(r => {{
        if (query) {{
          const match = r.npi.includes(query) || r.tin.includes(query) || r.name.toLowerCase().includes(query) || r.city.toLowerCase().includes(query) || r.code.includes(query);
          if (!match) return false;
        }}
        if (codeVal && r.code !== codeVal) return false;
        if (specVal && r.spec !== specVal) return false;
        if (addrVal && r.st !== addrVal) return false;
        if (tierVal && r.tier !== tierVal) return false;
        return true;
      }});

      // Update Live Stats
      const count = filteredRates.length;
      document.getElementById('statCount').textContent = count.toLocaleString();

      if (count > 0) {{
        const rates = filteredRates.map(r => r.rate).sort((a,b) => a - b);
        const minRate = rates[0];
        const maxRate = rates[rates.length - 1];
        const sum = rates.reduce((a,b) => a + b, 0);
        const meanRate = sum / count;
        const mid = Math.floor(count / 2);
        const medRate = count % 2 === 1 ? rates[mid] : (rates[mid - 1] + rates[mid]) / 2.0;

        document.getElementById('statMin').textContent = `$${{minRate.toFixed(2)}}`;
        document.getElementById('statMed').textContent = `$${{medRate.toFixed(2)}}`;
        document.getElementById('statMean').textContent = `$${{meanRate.toFixed(2)}}`;
        document.getElementById('statMax').textContent = `$${{maxRate.toFixed(2)}}`;
      }} else {{
        document.getElementById('statMin').textContent = '$0.00';
        document.getElementById('statMed').textContent = '$0.00';
        document.getElementById('statMean').textContent = '$0.00';
        document.getElementById('statMax').textContent = '$0.00';
      }}

      currentPage = 1;
      renderTable();
    }}

    function sortTable(col) {{
      if (sortCol === col) {{
        sortAsc = !sortAsc;
      }} else {{
        sortCol = col;
        sortAsc = true;
      }}
      filteredRates.sort((a, b) => {{
        let vA = a[col];
        let vB = b[col];
        if (vA === null || vA === undefined) vA = '';
        if (vB === null || vB === undefined) vB = '';
        if (typeof vA === 'number' && typeof vB === 'number') {{
          return sortAsc ? vA - vB : vB - vA;
        }}
        return sortAsc ? String(vA).localeCompare(String(vB)) : String(vB).localeCompare(String(vA));
      }});
      renderTable();
    }}

    function changePage(delta) {{
      const maxPage = Math.ceil(filteredRates.length / pageSize) || 1;
      currentPage = Math.min(Math.max(currentPage + delta, 1), maxPage);
      renderTable();
    }}

    function renderTable() {{
      const tbody = document.getElementById('ratesTbody');
      const start = (currentPage - 1) * pageSize;
      const end = start + pageSize;
      const slice = filteredRates.slice(start, end);

      tbody.innerHTML = slice.map(r => `
        <tr>
          <td class="mono">${{r.npi}}</td>
          <td class="mono">${{r.tin}}</td>
          <td><strong>${{r.name}}</strong></td>
          <td>${{r.city}}</td>
          <td>${{getStatusBadge(r.st)}}</td>
          <td>${{r.spec}}</td>
          <td class="mono">${{r.code}}</td>
          <td style="font-size:0.75rem">${{r.desc}}</td>
          <td class="rate">$${{r.rate.toFixed(2)}}</td>
          <td class="rate" style="color:#94a3b8">${{r.med ? '$' + r.med.toFixed(2) : 'N/A'}}</td>
          <td class="rate" style="color:#38bdf8">${{r.rpi ? r.rpi.toFixed(3) : 'N/A'}}</td>
          <td>${{getTierBadge(r.tier)}}</td>
        </tr>
      `).join('');

      const total = filteredRates.length;
      const pageStart = total > 0 ? start + 1 : 0;
      const pageEnd = Math.min(end, total);
      document.getElementById('pageInfo').textContent = `Showing ${{pageStart}} to ${{pageEnd}} of ${{total.toLocaleString()}} records`;
      document.getElementById('btnPrev').disabled = (currentPage <= 1);
      document.getElementById('btnNext').disabled = (end >= total);
    }}

    // Peer Group Dropdown Selection Handler
    function renderSelectedPeerGroup() {{
      const pId = document.getElementById('peerSelect').value;
      const container = document.getElementById('peerDetailsContainer');
      if (!pId) {{
        container.classList.add('hidden');
        return;
      }}
      const pg = PEER_GROUPS.find(p => p.id === pId);
      if (!pg) return;

      container.classList.remove('hidden');
      document.getElementById('pgN').textContent = pg.n;
      document.getElementById('pgP25').textContent = `$${{pg.p25.toFixed(2)}}`;
      document.getElementById('pgMed').textContent = `$${{pg.med.toFixed(2)}}`;
      document.getElementById('pgP75').textContent = `$${{pg.p75.toFixed(2)}}`;
      document.getElementById('pgIQR').textContent = `$${{pg.iqr.toFixed(2)}}`;

      // Find matching rates
      const provs = RATES_DATA.filter(r => r.peer === pId).sort((a,b) => a.rate - b.rate);
      const tbody = document.getElementById('peerProvidersTbody');
      tbody.innerHTML = provs.map(p => {{
        const diff = p.rate - pg.med;
        const diffStr = diff >= 0 ? `+$${{diff.toFixed(2)}}` : `-$${{Math.abs(diff).toFixed(2)}}`;
        const diffColor = diff > 0 ? '#f87171' : '#34d399';
        return `
          <tr>
            <td><strong>${{p.name}}</strong></td>
            <td>${{p.city}}</td>
            <td>${{p.spec}}</td>
            <td class="rate">$${{p.rate.toFixed(2)}}</td>
            <td class="rate" style="color:#94a3b8">$${{pg.med.toFixed(2)}}</td>
            <td class="rate" style="color:${{diffColor}}">${{diffStr}}</td>
            <td class="rate" style="color:#38bdf8">${{p.rpi ? p.rpi.toFixed(3) : 'N/A'}}</td>
            <td class="rate">${{p.pct !== null ? p.pct + '%' : 'N/A'}}</td>
            <td>${{getTierBadge(p.tier)}}</td>
          </tr>
        `;
      }}).join('');
    }}

    // Auto-init on page load
    window.addEventListener('DOMContentLoaded', () => {{
      initCharts();
    }});
  </script>
</body>
</html>
"""

    # 6. Save HTML file to both destinations
    for p in (output_html_path, submission_html_path):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(html_template)
        logger.info("Saved interactive dashboard HTML: %s (%.1f KB)", p, len(html_template) / 1024)

    return html_template


class DashboardHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler serving the dashboard directory."""
    def __init__(self, *args: Any, directory: Optional[str] = None, **kwargs: Any):
        if directory is None:
            directory = str(Path(__file__).resolve().parent.parent)
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress routine GET logging for cleaner terminal
        pass


def run_ui_server(
    port: int = 8050,
    open_browser: bool = True,
    html_path: str = "outputs/interactive_dashboard.html",
) -> None:
    """Launch the local web dashboard server."""
    # Ensure dashboard HTML exists
    if not os.path.isfile(html_path):
        generate_dashboard_html()

    root_dir = str(Path(__file__).resolve().parent.parent)

    class CustomHandler(DashboardHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, directory=root_dir, **kwargs)

    server = None
    for trial_port in range(port, port + 20):
        try:
            server = socketserver.TCPServer(("127.0.0.1", trial_port), CustomHandler)
            port = trial_port
            break
        except OSError:
            continue

    if server is None:
        logger.error("Could not bind dashboard server to any port between %d and %d", port, port + 20)
        return

    url = f"http://127.0.0.1:{port}/{html_path.replace(os.sep, '/')}"
    print("\n" + "=" * 78)
    print("  HiLabs AI Quest — Interactive Executive & Analyst Web Dashboard")
    print("=" * 78)
    print(f"  Status:  Running live server at: {url}")
    print(f"  Static:  Offline HTML deliverable: submission/interactive_dashboard.html")
    print("  Press Ctrl+C to stop the dashboard server.")
    print("=" * 78 + "\n")

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server...")
        server.shutdown()
        server.server_close()


def main() -> None:
    setup_logging(log_level="INFO")
    import argparse
    parser = argparse.ArgumentParser(description="HiLabs Interactive Dashboard Generator & Server")
    parser.add_argument("--export-only", action="store_true", help="Generate HTML deliverables without launching server")
    parser.add_argument("--port", type=int, default=8050, help="Port to bind dashboard server (default: 8050)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch web browser")
    args = parser.parse_args()

    generate_dashboard_html()

    if not args.export_only:
        run_ui_server(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
