# HiLabs Hackathon — Demonstration & Evaluation Checklist
## Centene California Commercial Group PPO Rate Curation Pipeline

This checklist is provided for hackathon judges, evaluators, and peer reviewers to quickly verify all deliverables, test executions, and analytical claims.

---

### Phase-by-Phase Verification Checklist

- [x] **1. Test Suite Execution (125 Tests)**
  - Command: `python -m pytest tests -v`
  - Expected: `125 passed in ~10.1s` across C1, C2, C3, C4, C5, C6, C7, and regression test suites.
  - Verification: Zero test failures, zero warnings, clean virtual environment execution.

- [x] **2. C1: Index Parsing & Normalization**
  - Command: `python -m src.c1_index_parser`
  - Deliverables: `outputs/plan_index.csv` (3,275 rows), `outputs/unique_rate_files.csv` (33 files).
  - Key Check: URLs normalized (RFC 3986 percent-encoding, lowercased host, tracking parameters stripped).

- [x] **3. C2: PPO Network Identification**
  - Command: `python -m src.c2_network_identifier`
  - Deliverables: `outputs/ppo_plan_candidates.csv` (456 plans), `outputs/c2_evidence_log.csv`, `reports/c2_ppo_logic.md`.
  - Key Check: 34 Confirmed PPO plans (HIOS Issuer `67138`, Product `67138CA073`) and 422 Probable PPO plans (Health Net employer EIN contracts). 2,819 non-PPO plans cleanly excluded.

- [x] **4. C3: PTD File Quality Scorecard**
  - Command: `python -m src.c3_file_grader`
  - Deliverables: `outputs/c3_file_quality_metrics.csv` (Composite Score: **82.17 / 100**, Grade B), `reports/c3_quality_methodology.md`.
  - Key Check: 11 scoring dimensions evaluated in streaming mode; 0 negative rates, 0 zero rates, 99.96% Luhn valid NPIs.

- [x] **5. C4: Rate Extraction & PPO Attribution**
  - Command: `python -m src.c4_rate_extractor`
  - Deliverables: `outputs/c4_extracted_rates.csv` (1,511,720 rows), `outputs/c4_ppo_rate_classification.csv`, `reports/c4_extraction_methodology.md`.
  - Key Check: Two-pass streaming `ijson` parser completes in 23.7s; non-collapsing rate context rule preserves Modifier 26 vs. global and POS 11 vs. 22.

- [x] **6. C5: Provider Practicing Address Verification**
  - Command: `python -m src.c5_address_mapper`
  - Deliverables: `outputs/c5_provider_address_crosswalk.csv` (5,672 rows), `outputs/c5_address_conflicts.csv` (167 records), `reports/c5_address_methodology.md`.
  - Key Check: Concurrent CMS NPPES v2.1 client with persistent disk cache (`data/processed/nppes_cache.json`, 0.05s cached execution); PO Boxes decoupled and flagged as CONFLICTED; 99.84% rate-row level verification.

- [x] **7. C6: Curated Rate File & Executive Excel Deliverable**
  - Command: `python -m src.c6_rate_curator`
  - Deliverables: `outputs/curated_ppo_rates.xlsx` (1.07 MB, 4 tabs), `outputs/c6_curated_benchmark_rates.csv` (2,418 rows), `outputs/c6_curation_summary.json`, `reports/c6_pipeline_summary.md`.
  - Key Check: Workbook contains Executive Summary, All 2,418 Benchmark Rates, 5,000 PPO Cross-Section, and Data Dictionary with corporate navy styling and currency formatting.

- [x] **8. C7: Rate Cost-Effectiveness Analysis**
  - Command: `python -m src.c7_cost_effectiveness`
  - Deliverables: `outputs/c7_provider_cost_effectiveness.csv` (2,418 rows), `outputs/c7_peer_group_summary.csv` (97 peer groups), `outputs/c7_summary.json`, `reports/c7_cost_effectiveness_methodology.md`.
  - Key Check: 97 distinct clinical peer groups; minimum peer threshold $N \ge 5$ enforced (96.73% eligible); Relative Price Index (RPI), percentile rank, and benchmark-weighted portfolio index calculated.

- [x] **9. Comprehensive Cross-Phase Audit**
  - Deliverable: `reports/final_audit.md`.
  - Key Check: 100% mathematical reconciliation between C4 extracted rows (1,511,720) and C6 curated rows (857,206 PPO + 654,514 excluded); zero ambiguous rows converted into confirmed PPO rates; clear separation of rate-row level (99.84%) and provider-tuple level (63.45%) verification denominators.

---

### Quick Inspection Commands for Evaluators

```powershell
# 1. Run full automated test suite
pytest

# 2. View C7 Cost-Effectiveness Summary
Get-Content outputs/c7_summary.json | ConvertFrom-Json | Select-Object -ExpandProperty volume_summary

# 3. View C6 Pipeline Volume Reconciliation
Get-Content outputs/c6_curation_summary.json | ConvertFrom-Json | Select-Object -ExpandProperty curation_volume

# 4. View Top Cost-Competitive Providers
python -c "import json; s=json.load(open('outputs/c7_summary.json')); print([p['provider_name'] + ' (RPI: ' + str(p['benchmark_weighted_rpi']) + ')' for p in s['top_cost_competitive_providers'][:5]])"

# 5. View Top High-Price Outliers
python -c "import json; s=json.load(open('outputs/c7_summary.json')); print([p['provider_name'] + ' (RPI: ' + str(p['benchmark_weighted_rpi']) + ')' for p in s['top_high_price_providers'][:5]])"
```
