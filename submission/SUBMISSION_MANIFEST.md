# HiLabs Hackathon Submission Manifest
## Data Pipeline Curation for Provider Rates — Centene California Commercial Group PPO Network

**Submission Date:** October 2026
**Payer / Market Scope:** Centene Corporation / Health Net of California — Commercial Group, California
**Target Network:** Commercial PPO Network
**Target Transparency File:** `2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json` (701.6 MB)
**Automated Tests:** 129 of 129 Passing (`python -m pytest tests -v`)

---

## 1. Official Hackathon Deliverables Mapping

| # | Official Deliverable | Primary Submission File | Format | Key Description |
|:---:|:---|:---|:---:|:---|
| **1** | **Rate File (Executive Excel)** | [`submission/curated_ppo_rates.xlsx`](curated_ppo_rates.xlsx) | `.xlsx` | Master 4-tab workbook: Executive Summary, All 2,418 Benchmark Rates, 5,000 PPO Cross-Section, and Data Dictionary (1.07 MB). |
| **1b** | **Rate File (Standard 6-Col)** | [`submission/standard_curated_rates.xlsx`](standard_curated_rates.xlsx) | `.xlsx` | Exact 6 columns: NPI, TIN, Address, Billing Code, Specialty, Rate. |
| **1c** | **Rate File (Standard CSV)** | [`submission/c6_curated_standard_rates.csv`](c6_curated_standard_rates.csv) | `.csv` | 2,418 rows with standard 6-column format. |
| **1d** | **Benchmark Rates (Rich CSV)** | [`submission/c6_curated_benchmark_rates.csv`](c6_curated_benchmark_rates.csv) | `.csv` | 2,418 rows with full 37-column clinical schema & weights. |
| **2** | **Logic File** | [`submission/LOGIC_FILE.md`](LOGIC_FILE.md) | `.md` | Systematic methodology for PPO network identification and TIN–NPI–Address mapping with conflict resolution. |
| **3** | **File Quality Metrics** | [`submission/c3_file_quality_metrics.csv`](c3_file_quality_metrics.csv) | `.csv` | 11-dimension quality scorecard scoring **82.17 / 100 (Grade B)**. |
| **3b** | **Quality Metric Details** | [`submission/c3_metric_details.csv`](c3_metric_details.csv) | `.csv` | Detailed 11-row table with weights, numerators, denominators, scores, and formulas. |
| **4** | **Summary File (JSON)** | [`submission/SUMMARY.json`](SUMMARY.json) | `.json` | Complete machine-readable run metrics: index files parsed, PPO plans, quality scores, rates extracted, and address shares. |
| **4b** | **Summary File (Markdown)** | [`submission/SUMMARY.md`](SUMMARY.md) | `.md` | Executive scorecard report with volume reconciliations and address percentage accounting. |
| **5** | **Video Presentation Script** | [`reports/video_script.md`](../reports/video_script.md) | `.md` | 5-minute timed presentation script with visual cues, slide prompts, and speaker timing. |
| **6** | **Code Repository** | [Root Directory](../) | Git | Clean execution via `python run_pipeline.py --all` or `python run_pipeline.py --verify`. |
| **7a** | **Brownie Point: Structured UI** | [`submission/interactive_dashboard.html`](interactive_dashboard.html) | `.html` | Standalone interactive web dashboard with Executive & Analyst views. Run live via `python run_ui.py`. |
| **7b** | **Brownie Point: Cost Analysis** | [`submission/c7_provider_cost_effectiveness.csv`](c7_provider_cost_effectiveness.csv) | `.csv` | 2,418 rows with Peer Median, Relative Price Index (RPI), percentile rank, and potential price difference. |
| **7c** | **Peer Group Summary** | [`submission/c7_peer_group_summary.csv`](c7_peer_group_summary.csv) | `.csv` | 97 clinical peer groups with sample size, quartiles, median, and IQR. |
| **Extra** | **Provider Address Crosswalk** | [`submission/c5_provider_address_crosswalk.csv`](c5_provider_address_crosswalk.csv) | `.csv` | 5,672 provider contracting tuples with verified addresses and NUCC taxonomies. |
| **Extra** | **Address Conflicts Audit Log** | [`submission/c5_address_conflicts.csv`](c5_address_conflicts.csv) | `.csv` | 167 records documenting administrative PO Boxes, national lab hubs, and border facilities. |

---

## 2. Core Documentation & Methodology Reports

The complete documentation suite is available in the [`reports/`](../reports/) directory:

- [`submission/LOGIC_FILE.md`](LOGIC_FILE.md) / [`reports/logic_file.md`](../reports/logic_file.md): Comprehensive logic file for PPO network identification and TIN–NPI–Address mapping (Deliverable 2).
- [`reports/c2_ppo_logic.md`](../reports/c2_ppo_logic.md): PPO network classification hierarchy and CMS HIOS registry crosswalk.
- [`reports/c3_quality_methodology.md`](../reports/c3_quality_methodology.md): 11 quality scoring dimensions and formula specifications.
- [`reports/c4_extraction_methodology.md`](../reports/c4_extraction_methodology.md): Streaming rate extraction, PPO attribution, and non-collapsing rate context rules.
- [`reports/c5_address_methodology.md`](../reports/c5_address_methodology.md): Address resolution engine, CMS NPPES caching, and CDPH hospital roster corroboration.
- [`reports/c6_pipeline_summary.md`](../reports/c6_pipeline_summary.md): End-to-end pipeline synthesis report.
- [`reports/c7_cost_effectiveness_methodology.md`](../reports/c7_cost_effectiveness_methodology.md): Peer group definitions, mathematical formulations for RPI, midpoint percentiles, and weighted portfolio fee index.
- [`README.md`](../README.md): Repository setup, architecture, and reproduction instructions.
- [`config/settings.yaml`](../config/settings.yaml): Master pipeline configuration file.

---

## 3. Automated Test Suite (129 Tests Passing)

To verify the pipeline from end to end:
```powershell
python -m pytest tests -v
```
- **129 passed in ~11.5 seconds** across all phases and regression suites:
  - `tests/test_c1_parser.py`: 33 tests (URL canonicalization, SHA-256 fingerprinting, network inference)
  - `tests/test_c2_network_identifier.py`: 22 tests (HIOS/EIN resolution, symmetric exclusion gates, PPO scoring)
  - `tests/test_c3_file_grader.py`: 16 tests (11 quality dimensions, Luhn checksums, streaming bounds)
  - `tests/test_c4_rate_extractor.py`: 10 tests (PPO attribution tiers, modifier preservation, capitation exclusion)
  - `tests/test_c5_address_mapper.py`: 10 tests (4-stage address resolution, PO Box conflicts, distance sanity)
  - `tests/test_c6_rate_curator.py`: 9 tests (benchmark procedure matching, Excel structure, summary schema)
  - `tests/test_c7_cost_effectiveness.py`: 9 tests (peer grouping, RPI index, midpoint percentiles, tiering)
  - `tests/test_audit_regressions.py`: 16 tests (canonical validators, symmetric gates, median formula, traceable sample extraction, invalid median handling, clinical deduplication contexts)
  - `tests/test_ui_and_orchestration.py`: 4 tests (pipeline stages registry, standard 6-column export, dashboard generation, deliverables completeness)
