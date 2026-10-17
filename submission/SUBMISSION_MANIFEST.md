# HiLabs Hackathon Submission Manifest
## Data Pipeline Curation for Provider Rates — Centene California Commercial Group PPO Network

**Submission Date:** October 17, 2026  
**Payer / Market Scope:** Centene Corporation / Health Net of California — Commercial Group, California  
**Target Network:** Commercial PPO Network  
**Target Transparency File:** `2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json` (701.6 MB)

---

## 1. Consolidated Submission Inventory

This `submission/` package contains the consolidated core deliverables, data files, and methodology documentation:

### Primary Deliverables in this Directory:
1. [`curated_ppo_rates.xlsx`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/curated_ppo_rates.xlsx) (1.07 MB)
   - The master 4-tab executive Excel workbook:
     - **Executive Summary:** High-level scorecard, network inclusion accounting, practicing address verification breakdown, top benchmark procedure fee ranges.
     - **Benchmark Rates:** All 2,418 benchmark procedure rates at NPI, TIN, Address, Code, Specialty, and Weight level with corporate Navy styling and currency formatting.
     - **PPO Rate Cross-Section:** 5,000 stratified representative sample rows spanning all 14 clinical specialties, inpatient/outpatient care settings, and professional/institutional billing classes.
     - **Data Dictionary:** Exhaustive documentation of all 36 fields, data types, allowed values, validation logic, and contracting guidance.
2. [`full_curated_ppo_rates.xlsx`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/full_curated_ppo_rates.xlsx) (71.33 MB)
   - **The Complete Full-Scale Excel Rate Deliverable:**
     - Exactly **857,206 data rows** (+ 1 header row = 857,207 total rows) containing every eligible curated California Commercial PPO rate.
     - Formatted across 19 core fields: NPI, NPI Type, TIN, Provider Name, Facility, Address Line 1, Address Line 2, City, State, ZIP, Address Status, Specialty, Billing Code, Modifier, Billing Class, Setting, Negotiated Rate ($), Rate Flag, PPO Status.
     - Generated via openpyxl streaming `write_only` mode (`python -m src.export_full_excel`).
3. [`c6_curated_benchmark_rates.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c6_curated_benchmark_rates.csv) (1.21 MB)
   - Clean, lightweight CSV containing all 2,418 benchmark procedure rates.
4. [`c7_provider_cost_effectiveness.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c7_provider_cost_effectiveness.csv) (1.21 MB)
   - Rate cost-effectiveness analysis for all 2,418 benchmark rate rows: Peer Group ID, Peer Count, Peer Median Rate, Relative Price Index (RPI), Peer Percentile, Potential Price Difference, and Cost-Effectiveness Tier.
5. [`c7_peer_group_summary.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c7_peer_group_summary.csv) (16.6 KB)
   - Summary of all 97 distinct clinical peer groups with sample size, quartiles (p25, median, p75), min, max, IQR, and eligibility status ($N \ge 5$).
6. [`c5_provider_address_crosswalk.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c5_provider_address_crosswalk.csv) (2.01 MB)
   - 5,672 provider contracting tuples with verified practicing addresses, verification tiers, confidence scores, and NUCC taxonomy mappings.
7. [`c5_address_conflicts.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c5_address_conflicts.csv) (53.0 KB)
   - Audit trail of 167 address edge cases: administrative PO Boxes, national lab facilities (LabCorp), and cross-border/border district facilities.
8. [`c3_file_quality_metrics.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c3_file_quality_metrics.csv) (1.5 KB)
   - 11-dimension quality scorecard scoring **82.17 / 100 (Grade B)**.
9. [`c6_curation_summary.json`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c6_curation_summary.json) (4.09 KB) & [`c7_summary.json`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c7_summary.json) (7.4 KB)
   - Structured JSON summaries with volume reconciliations, address percentages, and fee index rankings.

---

## 2. Core Documentation & Methodology Reports

The complete documentation suite is available in the [`reports/`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/) directory:

- [`reports/final_audit.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/final_audit.md): Complete cross-phase audit, 100% mathematical reconciliation of C4 to C6, and detailed audit of the 99.84% rate-row vs. 63.45% provider-tuple verification rates.
- [`reports/c7_cost_effectiveness_methodology.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c7_cost_effectiveness_methodology.md): Peer group definitions, mathematical formulations for RPI, midpoint percentiles, and weighted portfolio fee index.
- [`reports/final_evaluation_scorecard.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/final_evaluation_scorecard.md): Comprehensive two-track evaluation scorecard against official rubric.
- [`reports/final_audit.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/final_audit.md): Cross-phase audit, mathematical reconciliation, and denominator audit.
- [`reports/codebase_audit.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/codebase_audit.md): Deep technical audit of findings, reconciliations, and evaluator defense.
- [`reports/c7_cost_effectiveness_methodology.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c7_cost_effectiveness_methodology.md): Peer group definitions, formulas for RPI, midpoint percentiles, and weighted portfolio index.
- [`reports/c6_pipeline_summary.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c6_pipeline_summary.md): End-to-end pipeline synthesis report.
- [`reports/c5_address_methodology.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c5_address_methodology.md): Address resolution engine, CMS NPPES caching, and CDPH hospital roster corroboration.
- [`reports/c4_extraction_methodology.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c4_extraction_methodology.md): Streaming rate extraction, PPO attribution, and non-collapsing rate context rules.
- [`reports/c3_quality_methodology.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c3_quality_methodology.md): 11 quality scoring dimensions and formula specifications.
- [`reports/c2_ppo_logic.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c2_ppo_logic.md): PPO network classification hierarchy and CMS HIOS registry crosswalk.
- [`reports/beginner_project_guide.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/beginner_project_guide.md): Plain-English healthcare pricing terminology and evaluator defense guide.
- [`reports/data_acquisition_audit.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/data_acquisition_audit.md): Full dataset availability audit and provenance manifest.
- [`reports/pre_github_test_report.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/pre_github_test_report.md): Pre-GitHub validation report covering environment, outputs, and E2E tests.
- [`reports/video_script.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/video_script.md): 5-minute presentation script with speaker cues and timestamps.
- [`reports/demo_checklist.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/demo_checklist.md): Evaluator demonstration checklist and verification commands.
- [`README.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/README.md): Repository setup, architecture, and reproduction instructions.
- [`config/settings.yaml`](file:///c:/Users/prani/antigravity/intelligent-meitner/config/settings.yaml): Master pipeline configuration file.

---

## 3. Automated Test Suite (125 Tests Passing)

To verify the pipeline from end to end:
```powershell
python -m pytest tests -v
```
- **125 passed in ~10.1 seconds** across all phases and regression suites:
  - `tests/test_c1_parser.py`: 33 tests (URL canonicalization, SHA-256 fingerprinting, network inference)
  - `tests/test_c2_network_identifier.py`: 22 tests (HIOS/EIN resolution, symmetric exclusion gates, PPO scoring)
  - `tests/test_c3_file_grader.py`: 16 tests (11 quality dimensions, Luhn checksums, streaming bounds)
  - `tests/test_c4_rate_extractor.py`: 10 tests (PPO attribution tiers, modifier preservation, capitation exclusion)
  - `tests/test_c5_address_mapper.py`: 10 tests (4-stage address resolution, PO Box conflicts, distance sanity)
  - `tests/test_c6_rate_curator.py`: 9 tests (benchmark procedure matching, Excel structure, summary schema)
  - `tests/test_c7_cost_effectiveness.py`: 9 tests (peer grouping, RPI index, midpoint percentiles, tiering)
  - `tests/test_audit_regressions.py`: 16 tests (canonical validators, symmetric gates, median formula, traceable sample extraction, invalid median handling, clinical deduplication contexts)
