# Five-Minute Video Presentation Script
## HiLabs Hackathon: Data Pipeline Curation for Provider Rates
### Centene California Commercial Group PPO Network Rate Curation & Price Competitiveness Analysis

**Target Duration:** 5 minutes (300 seconds)  
**Presenter:** Data Engineering & Health Economics Lead  
**Slide / Screen Recording Cue:** Display live repository, Excel workbook, and terminal commands.

---

### [0:00 - 0:45] Section 1: The Business Problem & Why PTD Is a Curation Problem

**[Visual: Title Slide / Terminal showing `outputs/curated_ppo_rates.xlsx` and raw 701 MB JSON]**

**Speaker:**
> "Hello everyone. Under the federal Transparency in Coverage mandate, health plans publish monthly machine-readable files detailing their negotiated rates with in-network providers. Payer contracting executives and pricing strategists use this data to benchmark rates against competitors and negotiate fair hospital and physician contracts.
>
> But getting there is a **data curation problem, not a display problem**. In raw payer files:
> 1. **Network names are ambiguous:** Payers publish index files covering hundreds of plans across brands and markets. Plan names rarely indicate whether they belong to a PPO, HMO, or individual exchange network.
> 2. **File quality cannot be assumed:** Raw files contain $\$0$ rates, negative rates, duplicate contracts, and missing procedure codes.
> 3. **Rates lack addresses and specialties:** Rates are tied only to a billing Tax ID and an NPI. One TIN can operate hundreds of clinic sites, and about 80% of addresses in the CMS NPPES registry represent administrative billing offices or PO Boxes rather than physical practicing clinics.
>
> Our mission was to solve these three core problems for **Centene's California Commercial Group PPO Network**, grade file quality, extract rates with zero memory bloat, verify practicing locations, and deliver an executive-grade rate deliverable."

---

### [0:45 - 1:45] Section 2: End-to-End Architecture & Core Engineering Decisions

**[Visual: Mermaid Pipeline Architecture Diagram & `reports/c6_pipeline_summary.md`]**

**Speaker:**
> "Here is our 7-stage streaming architecture, built strictly in Python with zero external database dependencies:
>
> - **In Phase 1 and 2 (Network Identification):** We parsed 11 Centene index files and 3,275 plan rows. Rather than relying on naive text matching, we cross-referenced official CMS HIOS registries. We identified **456 target California Commercial PPO plans**—34 Confirmed under Health Net's official HIOS Product `67138CA073`, and 422 Probable plans under California employer commercial EINs—pointing to the target 701.6 MB file `healthnet-ca_in-network.json`. Over 2,800 HMO, POS, and exchange plans were cleanly excluded.
>
> - **In Phase 3 (File Quality Grading):** We built an `ijson` streaming grader that evaluated over 1.5 million prices in 13.6 seconds across 11 dimensions. The file achieved a composite score of **82.17 / 100 (Grade B)**, confirming structural integrity, zero orphan references, and zero $\$0$ rates.
>
> - **In Phase 4 (Rate Extraction):** Standard `json.load` crashes on a 700 MB file. We built a two-pass streaming parser that expanded multi-practitioner groups into **1,511,720 provider-rate records** in 23.7 seconds with peak RAM under 350 MB. Crucially, we enforced a **non-collapsing rate context rule**: preserving Modifier 26 professional fees versus global fees, and office versus hospital outpatient place of service, ensuring contracting teams never see distorted averages."

---

### [1:45 - 2:45] Section 3: Solving the Address & Multi-Location Problem (C5)

**[Visual: Screen showing `outputs/c5_address_conflicts.csv` and `outputs/c5_provider_address_crosswalk.csv`]**

**Speaker:**
> "Phase 5 directly addresses the hackathon's core challenge: knowing **who and where**.
>
> We extracted all 5,672 provider contracting tuples. We built a high-throughput, concurrent client querying the CMS NPPES Registry API v2.1 for all 3,735 unique NPIs, creating a persistent disk cache that executes in **0.05 seconds** on repeat runs.
>
> To eliminate stale or administrative addresses, we implemented a 4-stage verification hierarchy:
> 1. We strictly decoupled `LOCATION` from `MAILING` addresses, flagging PO Boxes as `CONFLICTED`.
> 2. We flagged 2,206 provider records in NPPES that had not been updated since before 2022.
> 3. We corroborated clinical sites against California Department of Public Health hospital licensing and major health system rosters—including Sutter Health, UC Health, Cedars-Sinai, Stanford, and Dignity Health.
> 4. We documented 167 real-world edge cases, including national specialized testing labs like LabCorp, and border hospital facilities in Incline Village, Nevada.
>
> **The Result:** At the curated PPO rate-row level, **99.84%** of rates link to independently verified or corroborated clinical practice locations!"

---

### [2:45 - 3:45] Section 4: Phase 6 Deliverables & Phase 7 Cost-Effectiveness

**[Visual: Open `outputs/curated_ppo_rates.xlsx` and show the 4 tabs live, then show `outputs/c7_peer_group_summary.csv`]**

**Speaker:**
> "In Phase 6, we generated an executive-grade, 4-tab Excel deliverable—[`curated_ppo_rates.xlsx`](file:///c:/Users/prani/antigravity/intelligent-meitner/outputs/curated_ppo_rates.xlsx):
> - **Tab 1: Executive Summary Dashboard** with KPI cards and network scope accounting.
> - **Tab 2: All 2,418 Benchmark Procedure Rates** at the NPI, TIN, Address, Code, Specialty, and Weight level.
> - **Tab 3: A 5,000-Row Stratified PPO Cross-Section** enabling immediate spreadsheet filtering across all specialties without lag.
> - **Tab 4: An exhaustive Data Dictionary** defining all 36 fields.
>
> In Phase 7, we implemented **Rate Cost-Effectiveness Analysis** (`src/c7_cost_effectiveness.py`). We established 97 defensible clinical peer groups based on procedure code, modifier, billing class, and setting:
> - **96.73% of benchmark rates** met our minimum threshold of $\ge 5$ comparable providers.
> - We computed the **Relative Price Index (RPI)**, midpoint percentile rank, potential price variance, and a **Benchmark-Weighted Portfolio Index** using the hackathon's official procedure weights.
> - **The Findings:** 61.5% of rates are median-aligned. However, academic medical centers like UCSF command weighted RPIs of **284%**—nearly 3x market median—reflecting significant institutional bargaining leverage."

---

### [3:45 - 4:30] Section 5: Auditability, Limitations, and Production Quality

**[Visual: Show `reports/final_audit.md` and run `pytest` in terminal showing 109 passing tests]**

**Speaker:**
> "We believe in radical transparency:
> - In `reports/final_audit.md`, every single check was verified. We confirmed that all 857,206 curated PPO rows reconcile with the 1.51M extracted rows, and that zero ambiguous contracts were converted into confirmed PPO rates.
> - We clearly distinguish between rate-row verification (99.84%) and provider-tuple verification (63.45%), explaining why hospital system breadth drives rate-line coverage.
> - We note that Centene's 100% score for freshness reflects TiC evergreen formatting (`9999-12-31`), but does not guarantee recent contract renegotiation.
>
> Our test suite contains **109 passing automated unit and integration tests**, running in under 17 seconds."

---

### [4:30 - 5:00] Section 6: Conclusion

**[Visual: Show terminal with clean Git status, repository structure, and final summary slide]**

**Speaker:**
> "In summary, our pipeline delivers:
> 1. Complete, defensible PPO network isolation;
> 2. An 11-dimension objective file quality scorecard;
> 3. Verified practicing addresses with zero fabricated locations; and
> 4. An actionable, executive-ready Excel rate deliverable with comparative price competitiveness modeling.
>
> Thank you, and we welcome your questions!"
