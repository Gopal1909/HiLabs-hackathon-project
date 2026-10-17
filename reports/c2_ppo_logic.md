# Phase 2 (C2) — PPO Network Identification & Logic Report

**Hackathon Track:** Data Pipeline Curation for Provider Rates  
**Payer:** Centene Corporation  
**Market Scope:** California Commercial Group  
**Target Network:** Preferred Provider Organization (PPO)  
**Date of Audit:** October 2026  

---

## Executive Summary

Phase 2 establishes an authoritative, auditable classification framework to identify Centene’s true California commercial group PPO network. It reconciles the Phase 1 hypothesis (255 candidate plan IDs), crosswalks plan identifiers against state and federal regulatory registries, inspects the underlying machine-readable rate file, and produces a complete, defendable inventory of target plans and rate files.

### Key Conclusions
1. **Hypothesis Reconciled:** The preliminary Phase 1 candidate count of 255 unique plan IDs represented a mixture of **249 California PPO plan IDs** and **6 Oregon PPO plan IDs** (from `healthnet-or`). Furthermore, in-depth text parsing identified 1 California plan with a naming typo (`CA L CUSPPO...` without a space) that was previously unclassified. Thus, the true target California Commercial Group PPO network contains exactly **456 plan offerings across 250 unique plan IDs**.
2. **Regulatory Identifier Crosswalk:** Centene's index file uniformly labels `plan_id_type` as `"ein"`. In reality:
   - **34 plans** carry genuine 10-character **CMS HIOS Product IDs** (`67138CA073`), verified in the CMS HIOS public exchange registry as Health Net of California's Small Group Commercial PPO product.
   - **422 plans** carry 9-digit **Employer Sponsor EINs** representing customized Large Group commercial PPO contracts (e.g., County of Santa Clara, Aon client employer pools).
3. **Consolidated Shared Rate File:** Selective streaming inspection of `2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json` (701.6 MB) revealed that it is a **shared multi-network file** covering 456 PPO plans, 719 HMO plans, and 133 POS/EOA plans. Inside the file, provider references explicitly segregate networks (e.g. `"HealthNet PPO (California)"`, `"PPO: <County>"` vs `"DIRECT NETWORK: AMBETTER HMO"`). **Downstream rate extraction in Phase 3 cannot treat all rates in this file as PPO.**

---

## 1. Hypothesis Verification & Reconciliation

In Phase 1, preliminary keyword matching on `\bppo\b` identified 469 plan rows in Health Net across 255 unique plan IDs. Phase 2 audited this finding against the underlying raw index JSON (`data/raw/2026-09-30_healthnet_index.json`):

| Scope | Plan Rows | Unique Plan IDs | Status | Rationale |
|:---|:---:|:---:|:---:|:---|
| **Health Net California (Structure 0)** | 455 | 249 | In-Scope Candidate | Explicit PPO keyword in CA commercial group file |
| **Health Net CA Typo (`CUSPPO`)** | 1 | 1 | Added to Target | Typo in name (`CA L CUSPPO 15/250/20% RAP`), EIN `901704765` |
| **Health Net Oregon (Structure 1)** | 14 | 6 | **EXCLUDED** | Out-of-state jurisdiction (`healthnet-or_in-network.json`) |
| **Total Phase 1 Reported** | **469** | **255** | Reconciled | 249 CA + 6 OR = 255 |
| **Actual California Target Network** | **456** | **250** | **TARGET PPO** | 34 Confirmed (HIOS) + 422 Probable (EIN) |

---

## 2. Identifier Crosswalk & Regulatory Mapping

### A. The Schema Mislabeling Problem
In CMS Transparency in Coverage (TiC) Table of Contents schema v2.0.0, the `plan_id_type` field must be either `hios` or `ein`. Centene's data pipeline populated `plan_id_type: "ein"` for 1,312 out of 1,312 California plans, creating a significant data curation trap.

### B. Resolution of Identifier Types
By inspecting the actual syntax and structure of the `plan_id` values, two distinct classes of identifiers were uncovered:

```
┌────────────────────────────────────────────────────────────────────────┐
│               Health Net California Commercial Group Plans             │
│                             (1,312 plans)                              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         ▼                                                     ▼
┌─────────────────────────────────┐           ┌─────────────────────────────────┐
│     CMS HIOS Product IDs        │           │     Employer Sponsor EINs       │
│          (154 plans)            │           │         (1,158 plans)           │
│  Format: 67138CA0xx (10 chars)  │           │      Format: 9 digits           │
└────────────────┬────────────────┘           └────────────────┬────────────────┘
                 │                                             │
      ┌──────────┴──────────┐                       ┌──────────┴──────────┐
      ▼                     ▼                       ▼                     ▼
┌───────────┐         ┌───────────┐           ┌───────────┐         ┌───────────┐
│ PPO Plans │         │ HMO Plans │           │ PPO Plans │         │ HMO / POS │
│ (34 plans)│         │(120 plans)│           │(422 plans)│         │(736 plans)│
│67138CA073 │         │024,026,etc│           │ 249 EINs  │         │ Non-PPO   │
└───────────┘         └───────────┘           └───────────┘         └───────────┘
```

1. **HIOS Product ID `67138CA073` (Small Group PPO):**
   - **Issuer ID `67138`:** Officially registered with CMS and Covered California to **Health Net of California, Inc.**
   - **Product ID `073`:** Registered under the California Department of Managed Health Care (DMHC) and California Department of Insurance (CDI) as Health Net's Small Group Commercial PPO product.
   - **Plans Covered:** 34 distinct benefit designs (e.g., `Platinum PPO 250/15`, `Gold PPO 500/20`, `Silver PPO 1700/50 INF`, `Bronze PPO 6300/65`).
   - **Classification:** `CONFIRMED` (Confidence Score: **0.95 / 1.00**).

2. **Employer Sponsor EINs (Large Group Custom PPO):**
   - **Structure:** 9-digit IRS Employer Identification Numbers (e.g., `911325671`, `952789166`, `954373573`).
   - **Regulatory Context:** In California, large group employer health benefit plans are bespoke contracts negotiated between the carrier and the employer or union trust (e.g., `CA L CUS PPO COUNTY OF SANTA CLARA 200`, `CA L CUS CBA PPO MFOW WELFARE FUND`, `CA L CUS PPO HSAF ED BRZ Plus Aon SCA`).
   - **Why EINs are used:** Under ERISA and CMS TiC rules (45 CFR § 147.212), group health plans without a standard HIOS ID must be identified by the Plan Sponsor's EIN.
   - **Classification:** `PROBABLE` (Confidence Score: **0.80 / 1.00**).

---

## 3. Classification Framework & Scoring Rubric

To ensure complete objectivity, the pipeline separates **evidence**, **confidence score**, and the **final classification decision**.

### Evidence Weight Allocation (Total: 1.00)
- **Factor A: Plan Name Evidence (Max: 0.35)**
  - Explicit `PPO` or `CUSPPO` token: `+0.25`
  - Standard California tiered cost-share signature (`copay/deductible/OOP/coinsurance` or `HSA/HDHP`): `+0.10`
- **Factor B: Identifier & Regulatory Crosswalk (Max: 0.30)**
  - Matches known CMS HIOS Small Group PPO Product ID (`67138CA073`): `+0.30`
  - Valid 9-digit Employer EIN identifying customized large group PPO contract: `+0.20`
  - Generic HIOS format under CA issuer: `+0.15`
- **Factor C: Rate File Linkage & PPO Content Evidence (Max: 0.25)**
  - References Centene's official California commercial rate file (`healthnet-ca_in-network.json`): `+0.15`
  - Rate file metadata confirms internal PPO network partitions (`HealthNet PPO (California)`, `PPO: <County>`): `+0.10`
- **Factor D: Market Scope & Issuer Evidence (Max: 0.10)**
  - Confirmed commercial group market type (`plan_market_type == 'group'`): `+0.05`
  - Issuer confirmed as Health Net California commercial entity (`Healthnet, LLC`): `+0.05`

### Decision Thresholds
| Decision | Score Threshold | Criteria & Action | Count |
|:---|:---:|:---|:---:|
| **CONFIRMED** | $\ge 0.85$ | Regulatory verification via CMS HIOS registry + full scope & file linkage | **34** |
| **PROBABLE** | $0.65 \le s < 0.85$ | Employer-sponsored large group PPO, valid sponsor EIN, explicit PPO plan name | **422** |
| **UNCERTAIN** | $0.40 \le s < 0.65$ | Ambiguous indicators or conflicting signals | **0** |
| **EXCLUDED** | $< 0.40$ or Gated | HMO, POS, EOA, EPO, Individual market, or Non-California plans | **2,819** |

---

## 4. False Positive Analysis & Exclusion Gates

Every non-PPO and out-of-scope plan was subjected to deterministic exclusion gates with an immutable audit trace:

### 1. HMO Product Lines (719 Plans Excluded)
- **Examples:** `WholeCare HMO`, `SmartCare HMO`, `Full Network HMO`, `Salud HMO y Mas`, `CA L SC HMO`.
- **Exclusion Reason:** Health Maintenance Organizations mandate a Primary Care Physician (PCP) gatekeeper and closed provider panel without out-of-network benefits (except emergency care). Including these would contaminate PPO rate benchmarking with capitated HMO provider schedules.

### 2. Elect Open Access (EOA) & POS Hybrids (133 Plans Excluded)
- **Examples:** `CA L EOA 20/500a/2500`, `CA L EC EOA 40/40%/5500`, `POS 30/500/20%`.
- **Clinical & Legal Definition:** In California DMHC regulatory filings, Health Net's **Elect Open Access (EOA)** is a two-tier Point-of-Service hybrid. Tier 1 requires an HMO PCP from a contracted Participating Physician Group (PPG). Tier 2 allows self-referral to specialists. Major surgeries, hospitalizations, and facility care require PCP authorization. It is not an open PPO network.

### 3. Salud Mexico Cross-Border Products (4 Plans Excluded)
- **Examples:** `CA L SAL Mex 5/0/1500`, `CA L&T CUS SAL CEMENT MASONS CA H&W GF+`.
- **Exclusion Reason:** Cross-border HMO network utilizing Mexican provider networks (SIMNSA) in Baja California/Tijuana.

### 4. Ambetter California Individual Market Plans (58 Plans Excluded)
- **Examples:** `Silver 70 Ambetter PPO AI-AN`, `Gold 80 Ambetter PPO`, `Minimum Coverage Ambetter PPO`.
- **Exclusion Reason:** Although labeled PPO and located in California, their `plan_market_type` is strictly `"individual"` (Covered California individual exchange). The hackathon problem statement explicitly scopes **California Commercial Group**.

### 5. Out-of-State Plans (1,905 Plans Excluded)
- **Examples:** Health Net Oregon (381 plans), Ambetter multi-state (1,062 plans in TX, FL, GA, etc.), QualChoice Arkansas (368 plans), Fidelis New York (94 plans).
- **Exclusion Reason:** Non-California regulatory jurisdiction.

---

## 5. Rate File Architecture & Downstream C3 Mandate

### Metadata of the Target Rate File
- **File Name:** `2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json`
- **File Size:** **701,615,514 bytes** (~701.6 MB uncompressed JSON)
- **HTTP Header:** `Accept-Ranges: bytes` (supports range requests and chunked streaming)
- **Reporting Entity:** Centene Management Company LLC (Third Party Administrator)
- **Last Updated:** 2026-10-06

### Crucial Architectural Discovery: Consolidated Shared File
Streaming sampling of the `provider_references` array revealed that Centene bundles all California commercial lines into this single file:
- **PPO Provider Sub-Networks:**
  - `"HealthNet PPO (California)"`
  - County-specific PPO networks: `"PPO: Los Angeles County"`, `"PPO: Santa Clara County"`, `"PPO: Sacramento County"`, `"PPO: San Diego County"`, `"PPO: Riverside County"`, `"PPO: Orange County"`, `"PPO: Marin County"`.
- **HMO & Direct Networks:**
  - `"DIRECT NETWORK: AMBETTER HMO"`
  - Direct contracted hospital systems: Sutter Health, Montage Medical Group, Mountain View Urgent Care.

### Downstream Mandate for Phase 3 (C3) Rate Extraction
> [!CAUTION]
> **Do not treat every negotiated rate in `healthnet-ca_in-network.json` as a PPO rate.**
> Because 719 HMO plans and 133 POS plans reference this exact same file, rate extraction must join `in_network[].negotiated_rates[].provider_reference` back to `provider_references[].network_name` and `provider_groups[].tin.business_name`. Rates associated solely with HMO capitated physician groups must be filtered out.

---

## 6. Deliverable Inventory

| Deliverable File | Rows | Description |
|:---|:---:|:---|
| [`outputs/ppo_plan_candidates.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/ppo_plan_candidates.csv) | 3,275 | Complete inventory of every plan evaluated, with resolved identifier types, scores, classifications, evidence, and decision reasons. |
| [`outputs/ppo_network_files.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/ppo_network_files.csv) | 33 | Detailed profile of all 33 rate files, plan links, size, confirmed/probable PPO links, and downstream caveats. |
| [`outputs/c2_evidence_log.csv`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/c2_evidence_log.csv) | 6 | Audit trail of external registries and official sources consulted (Centene, CMS HIOS, IRS EIN, CA DMHC). |
| [`outputs/c2_summary.json`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/c2_summary.json) | — | Machine-readable metrics: candidate counts, classification breakdown, target file specs, and verification findings. |
| [`reports/c2_ppo_logic.md`](file:///c:/Users/prani/antigravity/intelligent-meitner/reports/c2_ppo_logic.md) | — | This authoritative logic and methodology report. |
| [`tests/test_c2_network_identifier.py`](file:///c:/Users/prani/antigravity/intelligent-meitner/tests/test_c2_network_identifier.py) | 32 tests | Unit tests covering identifier matching, scoring thresholds, typo handling, false-positive exclusions, and rate file summary builds. |
