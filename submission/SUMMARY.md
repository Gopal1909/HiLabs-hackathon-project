# HiLabs Hackathon Deliverable 4 — Executive Summary Report
## High-Level Run Metrics, Quality Scores, and Curation Reconciliation

- **Payer & Scope:** Centene Corporation / Health Net of California — California Commercial Group
- **Target Network:** Commercial PPO Network
- **Target Machine-Readable File:** `2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json` (701.6 MB)
- **Deliverable Type:** Official Hackathon Deliverable 4 (Summary File)
- **Audit Status:** 100% Mathematically Reconciled | 129 Automated Tests Passing

---

## 1. High-Level Pipeline Scorecard

```
=================================== HIGH-LEVEL METRICS SCORECARD ===================================
Index Files Ingested:          11 files across 4 Centene operating brands (5,630 endpoints scanned)
Unique Plan Offerings:         2,815 cataloged plans (1,312 California plans)
Identified PPO Network:        456 California Commercial Group PPO plans across 250 unique plan IDs
Regulatory Product:            CMS HIOS Product ID 67138CA073 (Health Net Small Group PPO)
PTD Overall Quality Score:     82.17 / 100 (Grade B, 11 distinct dimensions evaluated)
Total Extracted Rates:         1,511,720 rows (streaming memory footprint strictly < 350 MB RAM)
Curated PPO Rates:             857,206 rows (56.70% of total; 654,514 non-PPO/capitation excluded)
  - Confirmed PPO (HIOS):      1,431 rows (0.17% of curated dataset)
  - Probable PPO (Health Sys): 855,775 rows (99.83% of curated dataset; major CA health systems FFS)
Benchmark Procedure Rates:     2,418 rows (134 matched procedure codes from hackathon workbook)
Unique Providers & TINs:       3,735 clinician NPIs across 2,888 contracting TINs (5,672 tuples)
Address Verification:
  - Rate-Row Level:            99.84% (855,809 / 857,206 rows verified or corroborated)
  - Provider-Tuple Level:      63.45% (3,599 / 5,672 tuples verified or corroborated)
  - Unique Clinician (NPI):    56.49% (2,110 / 3,735 unique NPIs verified or corroborated)
  - Benchmark Row Level:       60.17% (1,455 / 2,418 benchmark procedure rows verified)
Cost-Effectiveness (C7):       96.73% of benchmark rates eligible across 63 peer groups (N >= 5)
Automated Test Suite:          129 passed in ~11.6s (100% pass rate across all suites)
====================================================================================================
```

---

## 2. In-Depth Operational Breakdown

### A. Index Ingestion & Network Isolation (C1 & C2)
- **11 Brand Index Files:** Ingested all corporate Centene price transparency index files: Ambetter, Health Net, Fidelis Care, and QualChoice (7 plan-specific indexes).
- **Index Canonicalization:** Normalization eliminated tracking parameters, canonicalized percent-encodings, and reduced 5,630 URL endpoints into **62 unique rate files**.
- **California Target File:** Identified `2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json` (701.6 MB) as the sole in-scope California commercial group file.
- **PPO Plan Resolution:** Identified 456 PPO plans (34 HIOS confirmed small group + 422 large group employer trusts). Excluded 719 HMO plans, 133 POS/EOA plans, 14 Oregon plans, and 320 individual market exchange plans.

### B. File Quality Grading (C3)
- Evaluated across 11 CMS TiC quality dimensions with streaming `ijson`:
  - **M01 Structural Validity:** 100.0% (Weight: 10.0) — All schema root keys present.
  - **M02 Field Completeness:** 100.0% (Weight: 10.0) — Complete codes and prices.
  - **M03 Provider Identifier Validity:** 99.96% (Weight: 10.0) — 10-digit Luhn NPIs & 9-digit EINs.
  - **M04 Reference Integrity:** 100.0% (Weight: 10.0) — 0 orphan provider references.
  - **M05 Benchmark Code Coverage:** 22.98% (Weight: 10.0) — 134 of 583 hackathon codes in this file.
  - **M06 Monetary Rate Validity:** 100.0% (Weight: 15.0) — 0 zero rates, 0 negative rates.
  - **M07 Rate Outlier Quality:** 100.0% (Weight: 5.0) — 0 non-credible extreme rates.
  - **M08 Deduplication Quality:** 98.65% (Weight: 10.0) — 20,317 exact duplicate records out of 1,500,288 prices (1,479,971 unique clinical fingerprints).
  - **M09 Rate Type Usability:** 100.0% (Weight: 5.0) — Direct negotiated dollar rates.
  - **M10 Freshness & Expiration:** 100.0% (Weight: 5.0) — Evergreen active contracts.
  - **M11 PPO Applicability:** 0.03% (Weight: 10.0) — Segregated PPO provider references.
  - **Composite Score:** **82.17 / 100 (Grade B)**.

### C. Rate Extraction & Context Rules (C4)
- **1,511,720 rates extracted** in a memory-safe two-pass streaming process.
- **Context Preservation Rule:** Maintained separate records for Modifier 26 (professional component) vs. global, and POS 11 (office) vs. POS 22 (hospital outpatient), preventing artificial rate blending.
- **Capitation Exclusion:** Completely excluded HMO capitation models without fee-for-service schedules.

### D. Provider Practicing Address Resolution (C5)
- Evaluated 5,672 provider contracting tuples using CMS NPPES API v2.1 (cached in 0.05s) and CDPH licensed hospital rosters.
- **Reconciled Verification Denominators:**
  1. Transaction Rate Rows: **99.84%** (855,809 / 857,206)
  2. Provider Contracting Tuples: **63.45%** (3,599 / 5,672)
  3. Unique Clinician NPIs: **56.49%** (2,110 / 3,735)
  4. Benchmark Procedure Rows: **60.17%** (1,455 / 2,418)
- **Address Conflicts:** 167 conflicts audited (42 administrative PO Boxes, 112 national lab hubs, 13 border district facilities). Zero addresses were fabricated.

### E. Rate Cost-Effectiveness & Peer Group Analysis (C7)
- Constructed 97 distinct clinical peer groups by Procedure Code, Specialty, Modifier, and Setting.
- **63 peer groups** met the minimum statistical sample size ($N \ge 5$).
- **96.73% of benchmark rates (2,339 / 2,418)** scored with Relative Price Index (RPI) and midpoint percentile ranking.
- **Tier Distribution:**
  - **Low Cost (RPI < 0.90):** 588 rates (25.14%)
  - **Fair Market (0.90 <= RPI <= 1.10):** 1,259 rates (53.83%)
  - **Premium (1.10 < RPI <= 1.30):** 416 rates (17.78%)
  - **Significant Outlier (RPI > 1.30):** 76 rates (3.25%)

---

## 3. Submission Deliverables Index

| # | Deliverable Name | File Path | Format | Notes |
|:---:|:---|:---|:---:|:---|
| **1** | **Executive Rate File** | [`submission/curated_ppo_rates.xlsx`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/curated_ppo_rates.xlsx) | `.xlsx` | 4-tab master workbook with Executive Summary, Benchmark Rates, 5,000 PPO Cross-Section, and Data Dictionary. |
| **1b** | **Standard Rate File (6 Col)** | [`submission/standard_curated_rates.xlsx`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/standard_curated_rates.xlsx) | `.xlsx` | Exact 6 columns: NPI, TIN, Address, Billing Code, Specialty, Rate. |
| **1c** | **Standard Rate CSV** | [`submission/c6_curated_standard_rates.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c6_curated_standard_rates.csv) | `.csv` | Lightweight CSV containing all 2,418 standard benchmark rates. |
| **2** | **Logic File** | [`submission/LOGIC_FILE.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/LOGIC_FILE.md) | `.md` | End-to-end methodology for PPO identification and TIN–NPI–Address mapping. |
| **3** | **File Quality Metrics** | [`submission/c3_file_quality_metrics.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c3_file_quality_metrics.csv) | `.csv` | 11-dimension quality metrics table with scores and weights. |
| **3b** | **Quality Metric Details** | [`submission/c3_metric_details.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c3_metric_details.csv) | `.csv` | 11-row detailed dimension audit with numerators and denominators. |
| **4** | **Summary Metrics (JSON)** | [`submission/SUMMARY.json`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/SUMMARY.json) | `.json` | Complete machine-readable run metrics. |
| **4b** | **Summary Metrics (MD)** | [`submission/SUMMARY.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/SUMMARY.md) | `.md` | This executive summary report. |
| **5** | **Presentation Video Script**| [`reports/video_script.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/video_script.md) | `.md` | 5-minute timed presentation script with cues. |
| **6** | **Code Repository** | [Root Directory](file:///c:/Users/prani/antigravity/intelligent-meitner/) | Git | Fully reproducible from `README.md` via `python run_pipeline.py`. |
| **7a**| **Interactive Dashboard UI** | [`submission/interactive_dashboard.html`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/interactive_dashboard.html) | `.html` | Standalone browser dashboard (Executive & Analyst views). Run with `python run_ui.py`. |
| **7b**| **Cost Effectiveness (C7)** | [`submission/c7_provider_cost_effectiveness.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/submission/c7_provider_cost_effectiveness.csv) | `.csv` | 2,418 scored rows with RPI, peer medians, and cost tiers. |
