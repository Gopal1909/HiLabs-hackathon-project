"""
tests/test_c3_file_grader.py
────────────────────────────────────────────────────────────────────────────────
Unit tests for Phase 3 (C3) PTD File Quality Grader.
Tests are self-contained and run offline on synthetic JSON MRF fixtures.
Covers:
  1. Federal NPI Luhn checksum algorithm (valid vs invalid, check digit)
  2. Employer Identification Number (EIN) format validation
  3. Structural validity and missing top-level keys
  4. Field completeness (missing billing code, missing rate value, missing rate type)
  5. Monetary rate validity: positive rates, $0 rate defect, negative rates
  6. Rate-type distribution: negotiated dollar vs percentage vs fee schedule
  7. Reference integrity: resolved references vs orphan provider reference IDs
  8. PPO applicability: PPO-linked provider groups vs HMO-linked vs generic
  9. Duplicate handling: exact duplicate record penalty
  10. Rate outlier detection: non-credible extreme rates
  11. Freshness and contract expiration dates
  12. Weighted 100-point composite scoring and preservation of individual defects
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
import pytest

# Add src/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from c3_file_grader import (
    is_valid_npi,
    is_valid_ein,
    PTDFileGrader,
    load_benchmark_procedure_codes,
)

# ── Synthetic Standard MRF Fixture ────────────────────────────────────────────

SYNTHETIC_CLEAN_MRF = {
    "reporting_entity_name": "Centene Management Company LLC",
    "reporting_entity_type": "Third Party Administrator",
    "version": "2.0.0",
    "last_updated_on": "2026-10-06",
    "provider_references": [
        {
            "provider_group_id": 1,
            "network_name": ["HealthNet PPO (California)"],
            "provider_groups": [
                {
                    "npi": [1770688129, 1063646446],
                    "tin": {
                        "type": "ein",
                        "value": "68-0273974",
                        "business_name": "Sutter Health PPO Network",
                    },
                }
            ],
        },
        {
            "provider_group_id": 2,
            "network_name": ["DIRECT NETWORK: AMBETTER HMO"],
            "provider_groups": [
                {
                    "npi": [1285009035],
                    "tin": {
                        "type": "ein",
                        "value": "95-1234567",
                        "business_name": "DIRECT NETWORK: AMBETTER HMO",
                    },
                }
            ],
        },
    ],
    "in_network": [
        {
            "negotiation_arrangement": "ffs",
            "name": "OFFICE VISIT EST PATIENT 30-39 MIN",
            "billing_code_type": "CPT",
            "billing_code_type_version": "2022",
            "billing_code": "99214",
            "description": "Office or other outpatient visit",
            "negotiated_rates": [
                {
                    "negotiated_prices": [
                        {
                            "negotiated_type": "negotiated",
                            "negotiated_rate": 145.50,
                            "expiration_date": "9999-12-31",
                            "service_code": ["11"],
                            "billing_class": "professional",
                            "setting": "outpatient",
                        }
                    ],
                    "provider_references": [1],
                },
                {
                    "negotiated_prices": [
                        {
                            "negotiated_type": "negotiated",
                            "negotiated_rate": 120.00,
                            "expiration_date": "9999-12-31",
                            "service_code": ["11"],
                            "billing_class": "professional",
                            "setting": "outpatient",
                        }
                    ],
                    "provider_references": [2],
                },
            ],
        },
        {
            "negotiation_arrangement": "ffs",
            "name": "IMMUNE GLOBULIN SUBCUTANEOUS",
            "billing_code_type": "HCPCS",
            "billing_code_type_version": "2022",
            "billing_code": "J1559",
            "description": "Injection immune globulin",
            "negotiated_rates": [
                {
                    "negotiated_prices": [
                        {
                            "negotiated_type": "negotiated",
                            "negotiated_rate": 25.80,
                            "expiration_date": "9999-12-31",
                            "service_code": ["11"],
                            "billing_class": "professional",
                            "setting": "outpatient",
                        }
                    ],
                    "provider_references": [1],
                }
            ],
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Identifier Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIdentifierValidation:

    def test_valid_luhn_npis(self):
        # Known valid 10-digit NPIs from live Centene data
        assert is_valid_npi("1770688129") is True
        assert is_valid_npi(1770688129) is True
        assert is_valid_npi("1063646446") is True
        assert is_valid_npi("1285009035") is True

    def test_invalid_luhn_npis(self):
        # Corrupted check digit
        assert is_valid_npi("1770688120") is False
        assert is_valid_npi("1234567890") is False
        # Wrong length
        assert is_valid_npi("177068812") is False
        assert is_valid_npi("17706881299") is False
        # Non-numeric
        assert is_valid_npi("177068812A") is False
        assert is_valid_npi(None) is False

    def test_valid_eins(self):
        assert is_valid_ein("68-0273974") is True
        assert is_valid_ein("680273974") is True
        assert is_valid_ein("95-1234567") is True

    def test_invalid_eins(self):
        assert is_valid_ein("68-02739") is False
        assert is_valid_ein("1234567890") is False
        assert is_valid_ein("68-ABC3974") is False
        assert is_valid_ein(None) is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Structural Validity & Completeness Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStructuralValidityAndCompleteness:

    def test_clean_mrf_structural_validity(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(SYNTHETIC_CLEAN_MRF, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            grader.benchmark_codes = {"99214", "J1559"}
            file_metrics, details = grader.grade_file(temp_path)

            assert file_metrics["m01_structural_validity"] == 100.0
            assert file_metrics["m02_field_completeness"] == 100.0
            assert file_metrics["total_billing_code_entries"] == 2
            assert file_metrics["total_rate_records"] == 3
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_missing_top_level_keys(self):
        corrupted = {
            "reporting_entity_name": "Centene",
            # missing version, last_updated_on, reporting_entity_type
            "provider_references": [],
            "in_network": [],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(corrupted, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            file_metrics, details = grader.grade_file(temp_path)
            # 3 out of 6 keys present = 50.0%
            assert file_metrics["m01_structural_validity"] == 50.0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_missing_critical_rate_fields(self):
        mrf_incomplete = {
            **SYNTHETIC_CLEAN_MRF,
            "in_network": [
                {
                    "billing_code": "",  # missing billing code
                    "billing_code_type": "CPT",
                    "negotiated_rates": [
                        {
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "",  # missing rate type
                                    "negotiated_rate": None,  # missing rate value
                                }
                            ],
                            "provider_references": [1],
                        }
                    ],
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(mrf_incomplete, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            file_metrics, _ = grader.grade_file(temp_path)
            assert file_metrics["m02_field_completeness"] == 0.0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Rate Validity: $0 Rates, Negative Rates, and Rate Types
# ─────────────────────────────────────────────────────────────────────────────

class TestRateValidityAndRateTypes:

    def test_zero_rate_defect_penalized(self):
        mrf_zero_rates = {
            **SYNTHETIC_CLEAN_MRF,
            "in_network": [
                {
                    "billing_code": "99214",
                    "billing_code_type": "CPT",
                    "negotiated_rates": [
                        {
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 0.00,  # $0 defect!
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient",
                                }
                            ],
                            "provider_references": [1],
                        },
                        {
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 150.00,  # Valid positive
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient",
                                }
                            ],
                            "provider_references": [1],
                        },
                    ],
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(mrf_zero_rates, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            file_metrics, _ = grader.grade_file(temp_path)
            assert file_metrics["monetary_rates_zero_count"] == 1
            assert file_metrics["monetary_rates_positive_count"] == 1
            # 1 out of 2 positive = 50.0%
            assert file_metrics["m06_monetary_rate_validity"] == 50.0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_negative_rates_penalized(self):
        mrf_neg = {
            **SYNTHETIC_CLEAN_MRF,
            "in_network": [
                {
                    "billing_code": "99214",
                    "billing_code_type": "CPT",
                    "negotiated_rates": [
                        {
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": -45.00,  # Negative rate error
                                    "expiration_date": "9999-12-31",
                                }
                            ],
                            "provider_references": [1],
                        }
                    ],
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(mrf_neg, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            file_metrics, _ = grader.grade_file(temp_path)
            assert file_metrics["monetary_rates_negative_count"] == 1
            assert file_metrics["m06_monetary_rate_validity"] == 0.0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_percentage_rates_separated_from_monetary(self):
        mrf_pct = {
            **SYNTHETIC_CLEAN_MRF,
            "in_network": [
                {
                    "billing_code": "99214",
                    "billing_code_type": "CPT",
                    "negotiated_rates": [
                        {
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "percentage",
                                    "negotiated_rate": 65.0,  # 65% of billed charges
                                    "expiration_date": "9999-12-31",
                                }
                            ],
                            "provider_references": [1],
                        }
                    ],
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(mrf_pct, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            file_metrics, _ = grader.grade_file(temp_path)
            # Percentage rates should not pollute monetary rate counters
            assert file_metrics["total_prices_evaluated"] == 1
            assert file_metrics["monetary_rates_positive_count"] == 0
            assert file_metrics["m09_rate_type_usability"] == 0.0  # 0% dollar rates
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Reference Integrity & PPO Applicability Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestReferenceIntegrityAndPPOApplicability:

    def test_orphan_provider_reference_detected(self):
        mrf_orphan = {
            **SYNTHETIC_CLEAN_MRF,
            "in_network": [
                {
                    "billing_code": "99214",
                    "billing_code_type": "CPT",
                    "negotiated_rates": [
                        {
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 100.0,
                                }
                            ],
                            "provider_references": [9999],  # Does not exist in provider_references!
                        }
                    ],
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(mrf_orphan, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            file_metrics, details = grader.grade_file(temp_path)
            assert file_metrics["orphan_provider_references_count"] == 1
            assert file_metrics["m04_reference_integrity"] == 0.0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_ppo_vs_hmo_applicability_distinction(self):
        """Rates linked to provider_group 1 (PPO) vs provider_group 2 (HMO)."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(SYNTHETIC_CLEAN_MRF, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            file_metrics, _ = grader.grade_file(temp_path)
            # 2 rates linked to group 1 (PPO), 1 rate linked to group 2 (HMO)
            assert file_metrics["rates_linked_to_ppo_count"] == 2
            assert file_metrics["rates_linked_to_hmo_count"] == 1
            # PPO percentage: 2 / 3 = 66.67%
            assert file_metrics["m11_ppo_applicability"] == 66.67
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Duplicate Records & Outlier Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDuplicatesAndOutliers:

    def test_exact_duplicate_detection(self):
        mrf_dups = {
            **SYNTHETIC_CLEAN_MRF,
            "in_network": [
                {
                    "billing_code": "99214",
                    "billing_code_type": "CPT",
                    "negotiated_rates": [
                        {
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 150.0,
                                    "billing_class": "professional",
                                    "setting": "outpatient",
                                }
                            ],
                            "provider_references": [1],
                        },
                        {
                            # Exact identical duplicate
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 150.0,
                                    "billing_class": "professional",
                                    "setting": "outpatient",
                                }
                            ],
                            "provider_references": [1],
                        },
                    ],
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(mrf_dups, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            file_metrics, _ = grader.grade_file(temp_path)
            assert file_metrics["exact_duplicate_rate_records"] == 1
            # 1 duplicate out of 2 prices = 50% duplicate -> 50% score
            assert file_metrics["m08_deduplication_quality"] == 50.0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_extreme_outlier_detection(self):
        mrf_outlier = {
            **SYNTHETIC_CLEAN_MRF,
            "in_network": [
                {
                    "billing_code": "99214",
                    "billing_code_type": "CPT",
                    "negotiated_rates": [
                        {
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 500000.0,  # $500,000 for office visit!
                                    "billing_class": "professional",
                                    "setting": "outpatient",
                                }
                            ],
                            "provider_references": [1],
                        }
                    ],
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(mrf_outlier, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            file_metrics, _ = grader.grade_file(temp_path)
            assert file_metrics["m07_rate_outlier_quality"] == 0.0  # 100% outliers
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Composite 100-Point Scoring & Preservation of Defects
# ─────────────────────────────────────────────────────────────────────────────

class TestCompositeScoring:

    def test_overall_score_weighted_sum(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(SYNTHETIC_CLEAN_MRF, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            grader.benchmark_codes = {"99214", "J1559"}
            file_metrics, details = grader.grade_file(temp_path)

            calculated_sum = sum(d["weighted_score"] for d in details)
            assert round(calculated_sum, 2) == file_metrics["overall_quality_score"]
            assert file_metrics["overall_quality_score"] > 80.0
            assert file_metrics["quality_grade"] in ("A", "B")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_streaming_cap_sample_limit(self):
        """Validates bounded streaming with max_rate_items parameter."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(SYNTHETIC_CLEAN_MRF, f)
            temp_path = f.name

        try:
            grader = PTDFileGrader({"c3_scoring_weights": {}})
            file_metrics, _ = grader.grade_file(temp_path, max_rate_items=1)
            # Only 1 billing code entry should be processed
            assert file_metrics["total_billing_code_entries"] == 1
            assert file_metrics["analysis_coverage"] == "SAMPLE"
            assert file_metrics["max_items_capped"] == 1
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
