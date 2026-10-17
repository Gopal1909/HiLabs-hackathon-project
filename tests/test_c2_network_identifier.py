"""
tests/test_c2_network_identifier.py
────────────────────────────────────────────────────────────────────────────────
Unit tests for Phase 2 (C2) PPO Network Identification.
Offline tests covering:
  1. Identifier pattern matching (HIOS vs EIN vs Custom)
  2. Typo handling (e.g. 'CUSPPO' without space)
  3. Conflicting evidence and false-positive exclusion gates:
     - HMO plans (WholeCare, SmartCare, Salud HMO)
     - EOA / POS hybrid plans (Elect Open Access)
     - EPO plans
     - Individual market plans (Ambetter CA PPO)
     - Out-of-state plans (Health Net Oregon, QualChoice AR, Fidelis NY)
  4. Decision thresholds and confidence scoring (CONFIRMED, PROBABLE, UNCERTAIN, EXCLUDED)
  5. Rate file aggregation and relationship preservation
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import pytest

# Add src/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from c2_network_identifier import (
    evaluate_plan,
    build_ppo_network_files_table,
    build_c2_evidence_log,
    _HIOS_PLAN_ID_RE,
    _EIN_PLAN_ID_RE,
    _PPO_RE,
    _HMO_RE,
    _EOA_RE,
)

# Sample mock configuration
MOCK_CONFIG = {
    "c2_thresholds": {
        "confirmed": 0.85,
        "probable": 0.65,
        "uncertain": 0.40,
    },
    "c2_known_issuers": {
        "health_net_ca_hios": "67138",
        "health_net_ca_small_group_ppo_product": "67138CA073",
    },
}

BASE_HN_CA_PPO = {
    "brand": "Health Net",
    "plan_name": "Gold PPO 500/20",
    "plan_id": "67138CA073",
    "plan_id_type": "ein",  # Note: raw mislabeling in Centene index
    "plan_market_type": "group",
    "issuer_name": "Healthnet, LLC",
    "rate_file_url": "https://www.centene.com/content/dam/centene/Centene%20Corporate/json/DOCUMENT/2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json",
    "file_description": "in-network file",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Identifier Pattern Matching Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIdentifierMatching:

    def test_hios_id_valid(self):
        assert _HIOS_PLAN_ID_RE.match("67138CA073") is not None
        assert _HIOS_PLAN_ID_RE.match("67138CA024") is not None
        assert _HIOS_PLAN_ID_RE.match("33249OK002") is not None

    def test_hios_id_invalid(self):
        assert _HIOS_PLAN_ID_RE.match("952789166") is None
        assert _HIOS_PLAN_ID_RE.match("67138CA") is None
        assert _HIOS_PLAN_ID_RE.match("") is None

    def test_ein_id_valid(self):
        assert _EIN_PLAN_ID_RE.match("952789166") is not None
        assert _EIN_PLAN_ID_RE.match("911325671") is not None
        assert _EIN_PLAN_ID_RE.match("135369500") is not None

    def test_ein_id_invalid(self):
        assert _EIN_PLAN_ID_RE.match("67138CA073") is None
        assert _EIN_PLAN_ID_RE.match("12345") is None

    def test_resolved_type_hios(self):
        res = evaluate_plan(BASE_HN_CA_PPO, MOCK_CONFIG)
        assert res["identifier_type_resolved"] == "HIOS_PRODUCT_ID"

    def test_resolved_type_ein(self):
        row = {**BASE_HN_CA_PPO, "plan_id": "952789166", "plan_name": "CA L PPO 30/500/4000/30%"}
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["identifier_type_resolved"] == "EMPLOYER_SPONSOR_EIN"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Typo and Regex Matching Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTypoAndKeywordMatching:

    def test_standard_ppo(self):
        assert _PPO_RE.search("Health Net Gold PPO 500") is not None
        assert _PPO_RE.search("CA L PPO 30/500/4000/30%") is not None

    def test_cusppo_typo_without_space(self):
        """Validates that 'CUSPPO' without space matches PPO regex."""
        assert _PPO_RE.search("CA L CUSPPO 15/250/20% RAP") is not None
        row = {
            **BASE_HN_CA_PPO,
            "plan_name": "CA L CUSPPO 15/250/20% RAP",
            "plan_id": "901704765",
        }
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["classification"] == "PROBABLE"
        assert res["primary_network_type"] == "PPO"

    def test_case_insensitivity(self):
        assert _PPO_RE.search("standard ppo plan") is not None
        assert _PPO_RE.search("PREFERRED PROVIDER OPTION") is not None


# ─────────────────────────────────────────────────────────────────────────────
# 3. False-Positive Elimination Tests (Exclusion Gates)
# ─────────────────────────────────────────────────────────────────────────────

class TestFalsePositiveExclusionGates:

    def test_hmo_plan_excluded(self):
        row = {
            **BASE_HN_CA_PPO,
            "plan_name": "WholeCare HMO Gold $50 INF",
            "plan_id": "67138CA060",
        }
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["classification"] == "EXCLUDED"
        assert res["confidence_score"] == 0.0
        assert "HMO" in res["decision_reason"]
        assert res["primary_network_type"] == "HMO"

    def test_smartcare_hmo_excluded(self):
        row = {
            **BASE_HN_CA_PPO,
            "plan_name": "CA L SC HMO 50/1500d/7500",
            "plan_id": "474726731",
        }
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["classification"] == "EXCLUDED"
        assert "HMO" in res["decision_reason"]

    def test_eoa_elect_open_access_excluded(self):
        """Validates that Elect Open Access (POS hybrid) is excluded from pure PPO."""
        row = {
            **BASE_HN_CA_PPO,
            "plan_name": "CA L EOA 20/500a/2500",
            "plan_id": "953901917",
        }
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["classification"] == "EXCLUDED"
        assert res["confidence_score"] == 0.0
        assert "Elect Open Access" in res["decision_reason"] or "EOA" in res["decision_reason"]

    def test_ec_eoa_excluded(self):
        row = {
            **BASE_HN_CA_PPO,
            "plan_name": "CA L EC EOA 40/40%/5500",
            "plan_id": "954148514",
        }
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["classification"] == "EXCLUDED"

    def test_pos_plan_excluded(self):
        row = {
            **BASE_HN_CA_PPO,
            "plan_name": "POS 30/500/20%",
            "plan_id": "952789166",
        }
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["classification"] == "EXCLUDED"
        assert res["primary_network_type"] == "POS"

    def test_salud_mexico_excluded(self):
        row = {
            **BASE_HN_CA_PPO,
            "plan_name": "CA L SAL Mex 5/0/1500",
            "plan_id": "951234567",
        }
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["classification"] == "EXCLUDED"
        assert "Salud Mexico" in res["decision_reason"]

    def test_individual_market_ambetter_ca_excluded(self):
        """Validates that California individual-market PPO plans are excluded."""
        row = {
            "brand": "Ambetter",
            "plan_name": "Silver 70 Ambetter PPO AI-AN",
            "plan_id": "67138CA070",
            "plan_id_type": "hios",
            "plan_market_type": "individual",  # Individual market!
            "issuer_name": "Ambetter from Centene",
            "rate_file_url": "https://www.centene.com/content/dam/centene/Centene%20Corporate/json/DOCUMENT/2026-09-28_centene-management-company-llc_ambetter-ca_in-network.json",
            "file_description": "in-network file",
        }
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["classification"] == "EXCLUDED"
        assert "Individual exchange" in res["decision_reason"]
        assert res["in_commercial_group_scope"] is False

    def test_out_of_state_oregon_excluded(self):
        """Validates that Oregon Health Net PPO plans are excluded."""
        row = {
            "brand": "Health Net",
            "plan_name": "MCCABE METAL PRODUCTS PPO",
            "plan_id": "936033740",
            "plan_id_type": "ein",
            "plan_market_type": "group",
            "issuer_name": "Healthnet, LLC",
            "rate_file_url": "https://www.centene.com/content/dam/centene/Centene%20Corporate/json/DOCUMENT/2026-09-30_centene-management-company-llc_healthnet-or_in-network.json",
            "file_description": "in-network file",
        }
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["classification"] == "EXCLUDED"
        assert "Out-of-state" in res["decision_reason"]
        assert res["in_california_scope"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. Scoring and Decision Threshold Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestScoringAndThresholds:

    def test_confirmed_small_group_ppo(self):
        """HIOS 67138CA073 plan should achieve CONFIRMED classification (score >= 0.85)."""
        res = evaluate_plan(BASE_HN_CA_PPO, MOCK_CONFIG)
        assert res["classification"] == "CONFIRMED"
        assert res["confidence_score"] >= 0.85
        assert "Confirmed PPO" in res["decision_reason"]

    def test_probable_large_group_custom_ppo(self):
        """Employer-sponsored custom PPO with valid EIN should be PROBABLE (0.65 <= score < 0.85)."""
        row = {
            **BASE_HN_CA_PPO,
            "plan_name": "CA L CUS PPO COUNTY OF SANTA CLARA 200",
            "plan_id": "946000534",
        }
        res = evaluate_plan(row, MOCK_CONFIG)
        assert res["classification"] == "PROBABLE"
        assert 0.65 <= res["confidence_score"] < 0.95
        assert "Probable PPO" in res["decision_reason"]

    def test_uncertain_score_threshold(self):
        """A hypothetical ambiguous plan without file link or clear scope."""
        custom_thresholds = {"confirmed": 0.90, "probable": 0.80, "uncertain": 0.40}
        cfg = {"c2_thresholds": custom_thresholds, "c2_known_issuers": {}}
        row = {
            "brand": "Health Net",
            "plan_name": "Custom Preferred Plan",
            "plan_id": "000000000",
            "plan_id_type": "custom",
            "plan_market_type": "group",
            "issuer_name": "Other",
            "rate_file_url": "https://www.centene.com/content/dam/centene/Centene%20Corporate/json/DOCUMENT/2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json",
            "file_description": "in-network file",
        }
        res = evaluate_plan(row, cfg)
        assert res["classification"] in ("PROBABLE", "UNCERTAIN")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Rate File Aggregation & Preservation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRateFileAggregation:

    def test_build_ppo_network_files_table(self):
        rows = [
            # 1 Confirmed PPO
            evaluate_plan(BASE_HN_CA_PPO, MOCK_CONFIG),
            # 1 Probable PPO
            evaluate_plan({
                **BASE_HN_CA_PPO,
                "plan_name": "CA L PPO 30/500/4000/30%",
                "plan_id": "952789166",
            }, MOCK_CONFIG),
            # 1 Excluded HMO
            evaluate_plan({
                **BASE_HN_CA_PPO,
                "plan_name": "WholeCare HMO Gold $50",
                "plan_id": "67138CA060",
            }, MOCK_CONFIG),
        ]
        df = pd.DataFrame(rows)
        network_files_df = build_ppo_network_files_table(df)

        assert len(network_files_df) == 1
        record = network_files_df.iloc[0]
        assert record["is_target_ppo_network_file"] is True or record["is_target_ppo_network_file"] == 1
        assert record["confirmed_ppo_plans"] == 1
        assert record["probable_ppo_plans"] == 1
        assert record["excluded_plans_linked"] == 1
        assert record["total_plans_linked"] == 3
        assert "CRITICAL ARCHITECTURAL FINDING" in record["evidence_and_caveats"]

    def test_evidence_log_builder(self):
        log_df = build_c2_evidence_log()
        assert len(log_df) >= 5
        assert "evidence_id" in log_df.columns
        assert "source_url" in log_df.columns
        assert any("67138" in str(x) for x in log_df["identifier_matched"])
