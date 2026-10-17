# HiLabs Hackathon — Data Pipeline Curation for Provider Rates

**Payer:** Centene | **Market:** California Commercial Group | **Focus:** PPO Network

## Problem Statement
Build a pipeline that:
1. **C1 – Network Mapping**: Finds Centene's PPO network in its price-transparency index files
2. **C2 – PTD Grading**: Grades quality of rate files ($0 rates, duplicates, stale contracts, missing codes)
3. **C3 – Address Mapping**: Maps provider NPI/TIN to correct practising addresses

---

## Project Structure

```
intelligent-meitner/
├── src/
│   ├── c1_index_parser.py       # Phase 1: parse all Centene brand indexes
│   ├── c2_network_identifier.py # Phase 2: identify PPO network (future)
│   └── utils.py                 # Shared utilities
├── data/
│   ├── raw/                     # Raw downloads (gitignored)
│   └── processed/               # Intermediate processed data
├── outputs/
│   ├── plan_index.csv           # All plans × rate-file mappings
│   ├── unique_rate_files.csv    # Deduplicated rate files
│   └── index_parsing_summary.json
├── reports/                     # Quality reports (future)
├── tests/
│   └── test_c1_parser.py        # Unit tests for C1
├── config/
│   └── settings.yaml            # Configurable parameters
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Phase 1 — Parse Centene Index Files
```bash
python src/c1_index_parser.py
```

### 3. Run tests
```bash
python -m pytest tests/ -v
```

---

## Data Sources

| Brand | Source Index URL | Notes |
|-------|-----------------|-------|
| Ambetter | `centene.com/.../2026-09-28_ambetter_index.json` | Individual market |
| Health Net | `centene.com/.../2026-09-30_healthnet_index.json` | CA commercial group |
| Fidelis | `centene.com/.../2026-09-28_fidelis_index.json` | NY market |
| QualChoice | `centene.com/.../2026-09-28_qualchoice_index.json` | AR market |

All index files follow CMS Transparency in Coverage JSON schema v2.0.0.

---

## Index File Schema (CMS TiC v2.0.0)

```json
{
  "reporting_entity_name": "...",
  "reporting_entity_type": "...",
  "last_updated_on": "YYYY-MM-DD",
  "version": "2.0.0",
  "reporting_structure": [
    {
      "reporting_plans": [
        {
          "plan_name": "...",
          "plan_id_type": "hios",
          "plan_id": "...",
          "plan_market_type": "individual|small_group|large_group",
          "issuer_name": "..."
        }
      ],
      "in_network_files": [{"description": "...", "location": "https://..."}],
      "allowed_amounts_files": [{"description": "...", "location": "https://..."}]
    }
  ]
}
```

---

## Phase 1 Outputs

| File | Description |
|------|-------------|
| `outputs/plan_index.csv` | Every plan record with its linked rate-file URLs |
| `outputs/unique_rate_files.csv` | Deduplicated rate files with plan count |
| `outputs/index_parsing_summary.json` | Counts, errors, timing, source provenance |

---

## Constraints and Design Decisions

1. **No PPO assumption from name alone**: Network type is extracted from `plan_name`, `plan_market_type`, and description fields, then labeled `inferred|explicit|unknown`.
2. **URL normalization**: Strip trailing slashes, decode `%20`, lowercase scheme+host, preserve path case. SHA-256 hash used for canonical deduplication.
3. **Memory efficiency**: Large index files are streamed using `ijson` or `requests` streaming; not loaded entirely into RAM.
4. **Rerunnability**: Idempotent — existing outputs are overwritten; raw downloads are cached by date.
5. **No fabrication**: Parsing failures are logged with reason; incomplete downloads are labeled `status=partial`.

---

## Next Steps

- **C2**: Identify the PPO network by scoring plan_name keywords + plan_market_type + in_network_files description
- **C3**: Extract negotiated rates for CA PPO plans + map NPI/TIN to NPPES addresses
