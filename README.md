# HiLabs Hackathon — Data Pipeline Curation for Provider Rates
## Centene California Commercial Group PPO Network Rate Curation, File Quality Grading, Address Verification, and Cost-Effectiveness Analysis

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/)
[![Tests Passing](https://img.shields.io/badge/tests-125%20passed-brightgreen.svg)](tests/)
[![File Quality Score](https://img.shields.io/badge/PTD%20Quality-82.17%20%2F%20100%20(Grade%20B)-blue.svg)](reports/c3_quality_methodology.md)
[![Address Verification](https://img.shields.io/badge/Address%20Verification-99.84%25%20(Rate--Level)-brightgreen.svg)](reports/c5_address_methodology.md)

---

## 1. Executive Summary & Problem Framing

Under the federal Transparency in Coverage (TiC) mandate, health plans must publish monthly machine-readable files (MRFs) detailing negotiated rates with in-network healthcare providers. Health plan contracting teams use competitors' Price Transparency Data (PTD) to establish market fee benchmarks, negotiate hospital contracts, and model rate parity.

However, raw payer transparency files present three severe data curation problems:
1. **Network Mapping:** Payer index files catalog thousands of plans across multiple states, brands, and market segments. Cryptic plan titles rarely reveal whether a contract belongs to a PPO, HMO, EPO, or POS network.
2. **File Quality & Trust:** Raw files contain $\$0.00$ rates, negative rates, orphan provider references, duplicate contracts, and missing procedure codes without standard grading.
3. **Provider Address & Identity Ambiguity:** Rates are linked only to a Tax ID (TIN) and a National Provider Identifier (NPI)—completely omitting physical practicing addresses and medical specialties. A single TIN may operate hundreds of facilities, and about 80% of CMS NPPES registry addresses represent administrative billing offices or PO Boxes.

### Our Solution
This repository contains an end-to-end, memory-safe data curation pipeline in Python that:
- **Discovers and isolates** Centene's California Commercial Group PPO network using official CMS HIOS registries and commercial employer group contracts (**Phase C1 & C2**).
- **Grades file quality** across 11 mathematically grounded dimensions with streaming `ijson`, scoring **82.17 / 100 (Grade B)** (**Phase C3**).
- **Extracts 1.51M negotiated rates** with peak RAM under 350 MB, enforcing a **non-collapsing rate context rule** to preserve Modifier 26 vs. global and POS 11 vs. 22 distinctions (**Phase C4**).
- **Verifies physical practicing locations** using a 4-stage multi-source address engine, a concurrent CMS NPPES client with disk caching (0.05s cached execution), and CDPH hospital rosters, achieving **99.84%** address verification at the rate-row level (**Phase C5**).
- **Curates an executive-grade deliverable** at the NPI, TIN, Address, Billing Code, Specialty, and Rate level, packaged into a 4-tab Excel workbook ([`curated_ppo_rates.xlsx`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/curated_ppo_rates.xlsx)) with procedure and specialty weights (**Phase C6**).
- **Analyzes rate cost-effectiveness** across 97 clinical peer groups using the Relative Price Index (RPI) and benchmark-weighted fee portfolios (**Phase C7**).

---

## 2. Key Metrics & Audit Reconciliation

```
================================== PIPELINE SCORECARD ==================================
Target Rate File:          2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json (701.6 MB)
Payer / Market Scope:      Centene / Health Net of California — Commercial Group, California
Target Network:            California Commercial Group PPO Network
----------------------------------------------------------------------------------------
Total Extracted Rates:     1,511,720 rows
Curated PPO Rates:         857,206 rows (56.70% of total; 654,514 non-PPO/HMO/Capitation excluded)
  - Confirmed PPO (HIOS):  1,431 rows (0.17% of curated dataset)
  - Probable PPO (Health): 855,775 rows (99.83% of curated dataset; major CA health systems FFS)
Benchmark Procedure Rates: 2,418 rows (134 matched procedure codes from hackathon workbook)
In-Network Providers:      1,230 unique clinical NPIs across 1,028 contracting TINs
Address Verification:
  - Rate-Row Level:        99.84% (855,809 / 857,206 rows verified or corroborated)
  - Provider-Tuple Level:  63.45% (3,599 / 5,672 tuples verified or corroborated)
  - Unique Clinician (NPI):56.49% (2,110 / 3,735 unique NPIs verified or corroborated)
  - Benchmark Row Level:   60.17% (1,455 / 2,418 benchmark procedure rows verified)
Quality Score (C3):        82.17 / 100 (Grade B, 0 negative rates, 0 zero rates, 0 orphan refs)
Cost-Effectiveness (C7):   96.73% of benchmark rates eligible across 63 peer groups (N >= 5)
Automated Test Suite:      125 passed in ~10.1s (100% pass rate across C1–C7 and regressions)
========================================================================================
```

---

## 3. Deliverables Inventory

| Deliverable | Format | Location | Description |
|:---|:---:|:---|:---|
| **Executive Excel Deliverable** | `.xlsx` | [`outputs/curated_ppo_rates.xlsx`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/curated_ppo_rates.xlsx) | Corporate Navy-styled 4-tab workbook: Executive Summary, All 2,418 Benchmark Rates, 5,000 PPO Cross-Section, Data Dictionary (1.07 MB). |
| **Curated Benchmark Rates** | `.csv` | [`outputs/c6_curated_benchmark_rates.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/c6_curated_benchmark_rates.csv) | 2,418 rows at NPI, TIN, Address, Code, Specialty, and Weight level (1.21 MB). |
| **Provider Cost-Effectiveness** | `.csv` | [`outputs/c7_provider_cost_effectiveness.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/c7_provider_cost_effectiveness.csv) | 2,418 rows with Peer Median, Relative Price Index (RPI), percentile rank, and potential price difference (1.21 MB). |
| **Peer Group Summary** | `.csv` | [`outputs/c7_peer_group_summary.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/c7_peer_group_summary.csv) | 97 clinical peer groups with sample size, quartiles, median, and IQR (16.6 KB). |
| **Provider Address Crosswalk** | `.csv` | [`outputs/c5_provider_address_crosswalk.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/c5_provider_address_crosswalk.csv) | 5,672 provider contracting tuples with verified addresses and taxonomy (1.93 MB). |
| **Address Conflicts Log** | `.csv` | [`outputs/c5_address_conflicts.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/c5_address_conflicts.csv) | 167 records documenting administrative PO Boxes, national labs, and border facilities (53 KB). |
| **Full Curated PPO Rates** | `.csv` | [`outputs/c6_curated_ppo_rates.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/c6_curated_ppo_rates.csv) | Full 857,206 curated PPO rate rows (417.9 MB; gitignored for GitHub hygiene). |
| **Full Curated Excel Deliverable** | `.xlsx` | `submission/full_curated_ppo_rates.xlsx` | Complete 857,206-row spreadsheet (74.8 MB; gitignored; submitted separately via submission link). |
| **Pipeline Summary JSON** | `.json` | [`outputs/c6_curation_summary.json`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/c6_curation_summary.json) | Complete metadata, rate distributions, and address verification percentages. |
| **Cost-Effectiveness JSON** | `.json` | [`outputs/c7_summary.json`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/c7_summary.json) | RPI tier distribution, top competitive providers, and top high-price outliers. |

---

## 4. Documentation & Methodology Reports

- [`reports/pre_github_test_report.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/pre_github_test_report.md): Pre-GitHub validation report covering environment, 119 tests, output schemas, and isolated E2E tests.
- [`reports/codebase_audit.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/codebase_audit.md): Comprehensive technical audit, 10 cataloged findings, reconciliations, and evaluator defense guide.
- [`reports/beginner_project_guide.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/beginner_project_guide.md): Plain-English technical explanation guide for healthcare pricing terminology.
- [`reports/c7_cost_effectiveness_methodology.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c7_cost_effectiveness_methodology.md): Peer group definitions, formulas for RPI, midpoint percentiles, and weighted portfolio index.
- [`reports/c6_pipeline_summary.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c6_pipeline_summary.md): End-to-end pipeline synthesis report.
- [`reports/c5_address_methodology.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c5_address_methodology.md): Address resolution engine, NPPES caching, and conflict resolution.
- [`reports/c4_extraction_methodology.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c4_extraction_methodology.md): Rate extraction, two-pass streaming, and non-collapsing rate context rules.
- [`reports/c3_quality_methodology.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c3_quality_methodology.md): 11 quality scoring dimensions and formula specifications.
- [`reports/c2_ppo_logic.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c2_ppo_logic.md): PPO network classification hierarchy and HIOS crosswalk.

---

## 5. Quick Start & Execution

### 5.1 Environment Setup
```bash
# Clone the repository
git clone https://github.com/Gopal1909/HiLabs-hackathon-project.git
cd HiLabs-hackathon-project

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows PowerShell
# source venv/bin/activate    # Linux/macOS

# Install dependencies (pandas>=1.1.5, openpyxl, ijson, pytest, requests, etc.)
pip install -r requirements.txt
```

### 5.2 Raw Data Acquisition & Ignored Datasets Policy

To keep the repository lightweight and adhere to GitHub's file size limits, large raw datasets and full-scale outputs are excluded via `.gitignore`. Place them in the following paths to rerun the full pipeline:

| Dataset | Expected Local Path | File Size | Acquisition Source & Notes |
|:---|:---|:---:|:---|
| **Centene Index Files** (11 files) | `data/raw/*.json` | ~40 MB | Automatically downloaded from Centene's portal (`https://www.centene.com/price-transparency-files.html`) during Phase 1. |
| **Target Rate File** | `data/raw/2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json` | 701.6 MB | Official Centene California commercial machine-readable file. Download from Centene portal URL identified in Phase 2. |
| **Benchmark Workbook** | `data/raw/Rate_Benchmarking_Individual_Weights_Hackathon.xlsx` | 134 KB | Official hackathon benchmark dataset containing `Spec-Proc Weights` and `Taxonomy-Spec Xwalk`. |
| **CMS NPPES Cache** | `data/processed/nppes_cache.json` | 5.8 MB | Auto-populated by `src/c5_address_mapper.py` from CMS NPPES Registry API v2.1. Once fetched, runs in 0.05s offline. |
| **Full Excel Deliverable** | `submission/full_curated_ppo_rates.xlsx` | 74.8 MB | Complete 857,206-row spreadsheet. Submitted separately via submission drive; can be regenerated via `python -m src.export_full_excel`. |

### 5.3 Run the Automated Test Suite (125 Tests)
```bash
python -m pytest tests -v
```

### 5.4 Run the Pipeline Stages (C1 through C7)
```bash
# Phase 1: Parse all Centene brand index files
python -m src.c1_index_parser

# Phase 2: Identify California Commercial Group PPO network
python -m src.c2_network_identifier

# Phase 3: Evaluate PTD file quality across 11 dimensions
python -m src.c3_file_grader

# Phase 4: Extract provider-negotiated rates (streaming)
python -m src.c4_rate_extractor

# Phase 5: Verify provider practicing addresses via NPPES & hospital rosters
python -m src.c5_address_mapper

# Phase 6: Final rate curation & executive Excel deliverable generation
python -m src.c6_rate_curator

# Phase 7: Rate cost-effectiveness & clinical peer group analysis
python -m src.c7_cost_effectiveness

# Optional: Generate full 857k-row Excel deliverable (submission/full_curated_ppo_rates.xlsx)
python -m src.export_full_excel
```

---

## 6. Project Architecture

```
intelligent-meitner/
├── config/
│   └── settings.yaml            # Configurable paths, URLs, weights, thresholds
├── data/
│   ├── raw/                     # Raw index JSONs & Benchmark workbook (gitignored)
│   └── processed/
│       └── nppes_cache.json     # CMS NPPES API v2.1 response disk cache (5.8 MB, gitignored)
├── outputs/
│   ├── curated_ppo_rates.xlsx   # Executive 4-tab Excel rate deliverable (1.07 MB)
│   ├── c6_curated_benchmark_rates.csv  # 2,418 benchmark procedure rates (1.21 MB)
│   ├── c6_curated_ppo_rates.csv # Full 857k curated PPO rate rows (gitignored)
│   ├── c7_provider_cost_effectiveness.csv # Provider RPI, percentiles & potential savings
│   ├── c7_peer_group_summary.csv # Peer group distribution summaries
│   ├── c5_provider_address_crosswalk.csv # Provider address verification crosswalk
│   ├── c5_address_conflicts.csv # Documented PO Box & out-of-state lab conflicts
│   ├── c3_file_quality_metrics.csv # 11-dimension quality metrics
│   └── *.json                   # Summary audit metadata files
├── reports/                     # Comprehensive methodology reports & final audit
│   ├── final_evaluation_scorecard.md # Official two-track rubric evaluation scorecard
│   ├── final_audit.md           # Cross-phase reconciliation & denominator audit
│   ├── codebase_audit.md        # Technical finding catalogue and defense guide
│   ├── c7_cost_effectiveness_methodology.md
│   ├── c6_pipeline_summary.md
│   ├── c5_address_methodology.md
│   ├── c4_extraction_methodology.md
│   ├── c3_quality_methodology.md
│   ├── c2_ppo_logic.md
│   ├── video_script.md          # 5-minute presentation script
│   └── demo_checklist.md        # Evaluator demonstration checklist
├── src/
│   ├── c1_index_parser.py       # Index ingestion & URL normalization
│   ├── c2_network_identifier.py # HIOS registry PPO network classification
│   ├── c3_file_grader.py        # 11-dimension streaming file quality grader
│   ├── c4_rate_extractor.py     # Two-pass streaming rate extractor & PPO tiering
│   ├── c5_address_mapper.py     # Concurrent NPPES address verification engine
│   ├── c6_rate_curator.py       # Final rate curation & multi-tab Excel generator
│   ├── c7_cost_effectiveness.py # Price competitiveness & peer group analyzer
│   ├── export_full_excel.py     # Comprehensive 857k-row Excel exporter
│   └── utils.py                 # Shared utilities, logging, config loader
├── tests/
│   ├── test_c1_parser.py        # 33 unit tests
│   ├── test_c2_network_identifier.py # 22 unit tests
│   ├── test_c3_file_grader.py   # 16 unit tests
│   ├── test_c4_rate_extractor.py # 10 unit tests
│   ├── test_c5_address_mapper.py # 10 unit tests
│   ├── test_c6_rate_curator.py  # 9 unit tests
│   ├── test_c7_cost_effectiveness.py # 9 unit tests
│   └── test_audit_regressions.py # 14 regression & invariant tests (123 total)
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 7. Core Engineering Decisions & Compliance Guarantees

1. **Zero Hallucination or Rate Fabrication:** Every negotiated rate, billing code, modifier, NPI, and TIN is derived directly from Centene's machine-readable file. Missing addresses are categorized as `UNRESOLVED` rather than fabricated.
2. **Strict Context Preservation:** Rates with different modifiers (e.g., Modifier `26` professional component vs. global) or places of service (POS `11` physician office vs. POS `22` hospital outpatient department) are preserved as distinct rows, preventing misleading averages.
3. **Memory Safety:** Streaming parsing with `ijson` and bounded chunked iterators ensures the entire 701.6 MB file is processed without out-of-memory spikes (peak RAM < 350 MB).
4. **Idempotent Caching:** The CMS NPPES API client utilizes a persistent local disk cache (`data/processed/nppes_cache.json`), allowing complete address resolution in **0.05 seconds** on subsequent runs while respecting CMS rate limits.
5. **Configurability:** All file paths, weights, API endpoints, thresholds, and brand targets are managed via [`config/settings.yaml`](file:///c:/Users/prani/antigravity/intelligent-meitner/config/settings.yaml) with relative paths resolved at runtime.
