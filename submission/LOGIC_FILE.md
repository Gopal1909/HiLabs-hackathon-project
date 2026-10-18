# HiLabs Hackathon Deliverable 2 — Comprehensive Logic File
## Systematic Methodology for PPO Network Identification and TIN–NPI–Address Resolution

- **Submission Track:** Data Pipeline Curation for Provider Rates
- **Payer / Market Scope:** Centene Corporation / Health Net of California — California Commercial Group
- **Target Network:** Preferred Provider Organization (PPO)
- **Deliverable Type:** Official Hackathon Deliverable 2 (Logic File)
- **Date of Audit:** October 2026

---

## Executive Overview

Health plan contracting teams utilize competitor Price Transparency Data (PTD) under the federal Transparency in Coverage (TiC) mandate to benchmark reimbursement rates, evaluate provider price variation, and negotiate hospital contracts. However, raw payer machine-readable files present two foundational data engineering hurdles:
1. **PPO Network Identification:** Centene publishes thousands of plan offerings across 11 brand index files. Plan titles are inconsistent, omit network designations, and mislabel plan identifier types.
2. **Provider Address & Identity Resolution:** Machine-readable rates link only to a Taxpayer Identification Number (TIN) and a National Provider Identifier (NPI)—completely omitting physical practicing addresses and medical specialties. A single TIN operates multiple facilities, an NPI can practice across multiple locations, and ~80% of CMS NPPES registry addresses represent administrative billing lockboxes.

This document formally presents the mathematical, regulatory, and architectural logic implemented across Phases C1 through C6 to solve both challenges with zero rate fabrication.

---

# PART 1: Logic for Identifying Centene's California Commercial Group PPO Network (C1 & C2)

### 1.1 Regulatory & Data Sources Used
- **Centene Portal Index Files (11 Files):** Ingested from Centene's price transparency portal covering all national subsidiaries: Ambetter, Health Net, Fidelis Care, and QualChoice.
- **CMS Health Insurance Oversight System (HIOS) Registry:** The official federal database of Qualified Health Plans (QHPs) and commercial health product filings. Used to validate 10-character Product and Plan Identifiers.
- **California Department of Managed Health Care (DMHC) & California Department of Insurance (CDI):** State regulatory licensing rosters establishing Health Net of California as Centene's licensed commercial full-service health plan in California.
- **CMS Machine-Readable File (MRF) Schema v2.0.0:** Federal JSON specification defining `in-network`, `provider-references`, and `negotiated-rates` structures.

---

### 1.2 Step-by-Step Network Identification Rules

#### Step 1: URL Canonicalization & Index Ingestion (C1)
Centene's index files contained 5,630 rate file references across 2,815 plan offerings. Many plan entries pointed to identical rate files with minor query-string or capitalization variations.
- **Normalization Pipeline:**
  1. Strip trailing slashes and normalize Unicode/URL encoding (`%20` $\to$ space).
  2. Lowercase URL scheme and host; preserve case on S3/Azure storage paths.
  3. Strip tracking parameters (`utm_*`, `ref`, `source`).
  4. Generate a deterministic SHA-256 content fingerprint for each unique endpoint.
- **Outcome:** Reduced 5,630 file references into **62 unique rate files**.

#### Step 2: Regulatory Identifier Crosswalk & Typo Resolution (C2)
In Centene's California index file (`2026-09-30_healthnet_index.json`), **100% of plans (1,312 / 1,312) were populated with `plan_id_type: "ein"`**. This schema mislabeling obscured whether plans were individual exchange products, small group products, or large group employer trusts.
- **Crosswalk Resolution:**
  - **154 plans** carried 10-character alphanumeric strings matching regex `^[0-9]{5}[A-Z]{2}[0-9]{3}$`. These were resolved as **CMS HIOS Product IDs**.
  - **1,158 plans** carried 9-digit numeric strings matching regex `^[0-9]{9}$`. These were resolved as **Employer Sponsor EINs**.
- **Typo-Tolerant Parsing:**
  Standard regex `\bppo\b` identified 455 California plans. Manual and automated string distance checks identified 1 plan with an unspaced typo: `"CA L CUSPPO 15/250/20% RAP"` (EIN `901704765`), adding it to the candidate pool (totaling 456 plans).

#### Step 3: Symmetric False-Positive Exclusion Gates
Plans and rate files were subjected to rigid exclusion gates to eliminate non-PPO and non-commercial products:
- **HMO Exclusion:** Rejects `\b(hmo|health maintenance organization|smartcare|communitycare|canopy)\b`.
- **EPO Exclusion:** Rejects `\b(epo|exclusive provider organization)\b`.
- **POS / Open Access Exclusion:** Rejects `\b(pos|point of service|eoa|elect open access|ec/eoa)\b`.
- **Cross-Border HMO Exclusion:** Rejects `\b(salud|salud con health net|salud mexico)\b`.
- **Individual Market Exclusion:** Rejects Ambetter individual exchange plans (`ambetter-ca`).
- **Out-of-State Jurisdiction:** Rejects Oregon plans (`healthnet-or`).

#### Step 4: Multi-Network Shared File Discovery
Inspection of the sole remaining California commercial file (`2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json`, 701.6 MB) revealed it was a **shared multi-network repository** containing:
- 456 PPO plans
- 719 HMO plans
- 133 POS / EOA plans

Inside this file, provider reference groups explicitly segregate networks (e.g. `"HealthNet PPO (California)"` vs. `"DIRECT NETWORK: AMBETTER HMO"`). Treating all rates in this file as PPO would severely contaminate the dataset.

#### Step 5: Two-Tier PPO Classification Hierarchy
Rates were classified into defensible confidence tiers:
1. **`CONFIRMED_PPO` (0.17% of curated dataset; 1,431 rows):** Directly linked via provider reference group IDs to HIOS Small Group PPO Product `67138CA073`.
2. **`PROBABLE_PPO` (99.83% of curated dataset; 855,775 rows):** Fee-for-service contracts between Health Net California commercial group plans and major California health systems (Sutter Health, UC Regents, Stanford Health Care, Dignity Health, Cedars-Sinai).
3. **`EXCLUDED` (654,514 rows):** Capitation contracts without fee schedules, explicit HMO provider references, individual market Ambetter plans, and ambiguous unlinked TINs.

---

# PART 2: Logic for Mapping TIN to NPI to Practicing Address (C5 & C6)

### 2.1 The Core Healthcare Identity Problem
- **The 80% NPPES Staleness Dilemma:** The CMS National Plan and Provider Enumeration System (NPPES) registry was designed for billing remittance, not physical patient navigation. Over 80% of addresses represent administrative billing departments, accounting firms, or PO Boxes.
- **Many-to-Many Relationships:**
  - One TIN (e.g., Sutter Valley Hospitals) operates hundreds of clinical physical addresses.
  - One NPI (e.g., an orthopedic surgeon) may practice at 3 hospital outpatient centers and 2 private clinics.
- **Cartesian Rate Explosion Hazard:** If an institutional rate for procedure `99214` is joined against all 45 physical addresses associated with a hospital TIN, the dataset expands by 4,500%, fabricating 44 duplicate rates and misrepresenting contract volume.

---

### 2.2 Data Sources Used for Address Verification
1. **CMS NPPES Registry API v2.1:** Live and cached endpoint providing Provider Type (1 vs 2), primary practice address, secondary practice locations, and taxonomy codes.
2. **California Department of Public Health (CDPH) Health Facility Roster:** Official state licensing registry of all 420+ licensed general acute care hospitals, ambulatory surgery centers, and specialty clinics.
3. **Centene PTD Machine-Readable Roster:** Legal business names and provider group naming strings embedded in the raw JSON file.
4. **NUCC Health Care Provider Taxonomy Code Set v24.0:** National taxonomy crosswalk resolving 10-character codes to clinical medical specialties.

---

### 2.3 Address Mapping Logic & Multi-Site Resolution Rules

#### Rule 1: Separation of Crosswalk from Rate Deliverable
- In [`outputs/c5_provider_address_crosswalk.csv`](../outputs/c5_provider_address_crosswalk.csv), **every distinct (NPI, TIN, Address)** tuple is preserved (5,672 tuples across 3,735 unique clinicians and 2,888 TINs).
- In [`outputs/c6_curated_benchmark_rates.csv`](../outputs/c6_curated_benchmark_rates.csv), each contracted rate is mapped to the **single authoritative primary clinical practice location** (`practice_locs[0]` after PO Box screening) to eliminate duplicate Cartesian rate inflation.

#### Rule 2: 4-Tier Verification Hierarchy
Every provider address is assigned an evidence-backed verification status:
1. **`VERIFIED_CURRENT` (Confidence 0.88 - 0.95 | 3,343 tuples, 58.9%):**
   - NPPES practice address updated within the last 24 months.
   - Physical street number and street name verified (not a PO Box).
   - Valid California postal code and geographic coordinates.
2. **`CORROBORATED` (Confidence 0.78 | 256 tuples, 4.5%):**
   - Historical NPPES practice location (older than 24 months) independently corroborated by exact street or facility match against the CDPH licensed hospital facility directory or PTD business roster.
3. **`NPPES_ONLY_UNVERIFIED` (Confidence 0.55 | 1,906 tuples, 33.6%):**
   - Valid California physical practice location in NPPES, but lacks recent update or external corroboration.
4. **`CONFLICTED` (Confidence 0.20 - 0.25 | 154 tuples, 2.7%):**
   - Discrepancy detected (e.g. administrative PO Box, national out-of-state reference lab, border district).
5. **`UNRESOLVED` (Confidence 0.00 | 13 tuples, 0.2%):**
   - Entity not found in registry or malformed record; preserved with null address for audit transparency.

---

### 2.4 Handling Conflicts & Discrepancies (Audit Log)

The pipeline detected and resolved **167 address conflicts**, documented in [`outputs/c5_address_conflicts.csv`](../outputs/c5_address_conflicts.csv):

| Conflict Category | Count | Underlying Cause | Systematic Resolution Rule |
|:---|:---:|:---|:---|
| **Administrative PO Box** | 42 | NPPES practice address listed as `PO BOX`, `P.O. BOX`, `DRAWER`, or `LOCKBOX`. | **Fallback Rule:** Inspect secondary practice locations. If physical street exists, elevate to verified physical address. Otherwise, flag as `CONFLICTED:PO_BOX_PRACTICE_ADDRESS` and preserve without fabricating fake street. |
| **National Reference Labs** | 112 | High-volume clinical diagnostic laboratories (e.g. LabCorp TIN `13-3151515`). | **Entity Rule:** Contracting TIN headquarters located out of state (e.g., Burlington, NC); physical servicing lab located in California (San Diego, CA). Preserved as valid in-network lab with explicit state disclosure. |
| **Border District Facilities** | 13 | Facilities located in adjacent border regions (e.g. Reno, NV / South Lake Tahoe, CA). | **Contracting Rule:** Contracted under California commercial PPO network to provide emergency/trauma care for Eastern Sierra California residents. Flagged with geographic explanation. |

---

### 2.5 Authoritative Address Verification Accounting

Because transaction volume is heavily concentrated among large regional hospital systems, reporting a single verification percentage is misleading. Our audit establishes four distinct, mathematically reconciled denominators:

| Evaluation Level | Verified / Corroborated Count | Total Denominator | Verification Share | Practical Significance |
|:---|:---:|:---:|:---:|:---|
| **Transaction Rate Rows** | **855,809** | **857,206** | **99.84%** | Contract volume weighted by hospital systems (Sutter, UC, Stanford). |
| **Provider Contracting Tuples** | **3,599** | **5,672** | **63.45%** | Unique (NPI, TIN, Address) contracting relationships across California. |
| **Unique Clinician NPIs** | **2,110** | **3,735** | **56.49%** | Distinct Type 1 and Type 2 practitioners in the PTD file. |
| **Benchmark Procedure Rates** | **1,455** | **2,418** | **60.17%** | Specific benchmark rate rows matched to the 134 hackathon procedures. |

---

## 3. Summary of Deliverables & Regulatory Compliance

- **Deliverable 1 (Rate Files):** Available in executive 4-tab Excel ([`curated_ppo_rates.xlsx`](../outputs/curated_ppo_rates.xlsx)), standard 6-column Excel ([`standard_curated_rates.xlsx`](../outputs/standard_curated_rates.xlsx)), and standard CSV ([`c6_curated_standard_rates.csv`](../outputs/c6_curated_standard_rates.csv)).
- **Deliverable 2 (Logic File):** This consolidated document.
- **Deliverable 3 (File Quality Metrics):** Documented across 11 dimensions in [`reports/c3_quality_methodology.md`](../reports/c3_quality_methodology.md) and [`submission/c3_metric_details.csv`](c3_metric_details.csv).
- **Deliverable 4 (Summary Metrics):** Reconciled in [`submission/SUMMARY.json`](SUMMARY.json).
- **Deliverable 7 (Brownie Points):** Interactive Executive & Analyst Dashboard ([`submission/interactive_dashboard.html`](interactive_dashboard.html) and `python run_ui.py`) + Cost-Effectiveness RPI Engine (C7).
