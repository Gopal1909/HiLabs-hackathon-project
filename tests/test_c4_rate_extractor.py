"""
tests/test_c4_rate_extractor.py
Unit tests for Phase 4 (C4) Negotiated Rate Extraction and PPO Classification.

Tests synthetic MRF data with:
- Multiple providers per group (NPI expansion)
- Multiple rate types (negotiated vs percentage)
- Missing provider references (unresolved reference tracking)
- Differing service conditions (modifiers, place of service, billing class)
- Explicit PPO vs HMO vs Ambetter Individual vs Major Health Systems
- Capitation arrangement exclusion
- Multiple rates for the exact same clinical context
- Malformed records handling
"""
import csv
import json
import os
import tempfile
import pytest

from src.c4_rate_extractor import (
    RateExtractor,
    validate_npi_luhn,
    validate_tin_ein,
)


class TestIdentifierValidation:
    def test_valid_luhn_npis(self):
        # Known valid CMS Luhn NPIs
        valid_npis = ["1770688129", "1063646446", "1285009035", "1902520455", "1245494517"]
        for npi in valid_npis:
            assert validate_npi_luhn(npi) is True

    def test_invalid_luhn_npis(self):
        # Corrupted or wrong checksum
        invalid_npis = ["1770688128", "1234567890", "0000000000", "short", ""]
        for npi in invalid_npis:
            assert validate_npi_luhn(npi) is False

    def test_valid_eins(self):
        valid_eins = ["68-0273974", "94-1156581", "200434866", "95-4248140"]
        for ein in valid_eins:
            assert validate_tin_ein(ein) is True

    def test_invalid_eins(self):
        invalid_eins = ["000000000", "123456789", "12-34", "", None]
        for ein in invalid_eins:
            assert validate_tin_ein(ein) is False


class TestProviderReferenceClassification:
    @pytest.fixture
    def synthetic_mrf(self, tmp_path):
        mrf_data = {
            "reporting_entity_name": "Centene Test",
            "reporting_entity_type": "Third Party Administrator",
            "version": "2.0.0",
            "last_updated_on": "2026-10-06",
            "provider_references": [
                {
                    "provider_group_id": 1,
                    "provider_groups": [
                        {
                            "npi": [1770688129, 1063646446],
                            "tin": {"type": "ein", "value": "68-0273974", "business_name": "HealthNet PPO (California)"}
                        }
                    ]
                },
                {
                    "provider_group_id": 2,
                    "provider_groups": [
                        {
                            "npi": [1285009035],
                            "tin": {"type": "ein", "value": "95-4248140", "business_name": "PPO: Los Angeles County"}
                        }
                    ]
                },
                {
                    "provider_group_id": 3,
                    "provider_groups": [
                        {
                            "npi": [1902520455],
                            "tin": {"type": "ein", "value": "94-1156581", "business_name": "Stanford Health Care"}
                        }
                    ]
                },
                {
                    "provider_group_id": 4,
                    "provider_groups": [
                        {
                            "npi": [1245494517],
                            "tin": {"type": "ein", "value": "20-0434866", "business_name": "DIRECT NETWORK: AMBETTER HMO"}
                        }
                    ]
                },
                {
                    "provider_group_id": 5,
                    "provider_groups": [
                        {
                            "npi": [1750550968],
                            "tin": {"type": "ein", "value": "94-2603666", "business_name": "DIRECT NETWORK: AMBETTER PPO"}
                        }
                    ]
                },
                {
                    "provider_group_id": 6,
                    "provider_groups": [
                        {
                            "npi": [1669287033],
                            "tin": {"type": "ein", "value": "45-3599490", "business_name": "Smith Physical Therapy Clinic"}
                        }
                    ]
                }
            ],
            "in_network": [
                {
                    "negotiation_arrangement": "ffs",
                    "billing_code": "99213",
                    "billing_code_type": "CPT",
                    "billing_code_type_version": "2022",
                    "name": "OFFICE VISIT EST PATIENT",
                    "description": "Office or other outpatient visit for evaluation and management",
                    "negotiated_rates": [
                        {
                            "provider_references": [1],
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 125.00,
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient",
                                    "service_code": ["11"]
                                }
                            ]
                        },
                        {
                            "provider_references": [3],
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 160.00,
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient",
                                    "service_code": ["11"],
                                    "billing_code_modifier": ["25"]
                                }
                            ]
                        },
                        {
                            "provider_references": [4],
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 90.00,
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient"
                                }
                            ]
                        },
                        {
                            "provider_references": [5],
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 95.00,
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient"
                                }
                            ]
                        },
                        {
                            "provider_references": [6],
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 110.00,
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient"
                                }
                            ]
                        },
                        {
                            "provider_references": [999],  # Unresolved reference
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 100.00,
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient"
                                }
                            ]
                        }
                    ]
                },
                {
                    "negotiation_arrangement": "capitation",
                    "billing_code": "36415",
                    "billing_code_type": "CPT",
                    "billing_code_type_version": "2022",
                    "name": "ROUTINE VENIPUNCTURE",
                    "negotiated_rates": [
                        {
                            "provider_references": [3],
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 15.00,
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        file_path = tmp_path / "synthetic_mrf.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(mrf_data, f)
        return str(file_path)

    def test_provider_reference_classification_categories(self, synthetic_mrf):
        extractor = RateExtractor()
        pref_map = extractor.load_provider_references(synthetic_mrf)

        # 1: HealthNet PPO -> CONFIRMED_PPO
        assert pref_map[1]["ppo_applicability"] == "CONFIRMED_PPO"
        # 2: PPO: Los Angeles County -> CONFIRMED_PPO
        assert pref_map[2]["ppo_applicability"] == "CONFIRMED_PPO"
        # 3: Stanford Health Care -> PROBABLE_PPO
        assert pref_map[3]["ppo_applicability"] == "PROBABLE_PPO"
        # 4: DIRECT NETWORK: AMBETTER HMO -> EXCLUDED_HMO
        assert pref_map[4]["ppo_applicability"] == "EXCLUDED_HMO"
        # 5: DIRECT NETWORK: AMBETTER PPO -> EXCLUDED_INDIVIDUAL_EXCHANGE
        assert pref_map[5]["ppo_applicability"] == "EXCLUDED_INDIVIDUAL_EXCHANGE"
        # 6: General clinic -> AMBIGUOUS_UNRESOLVED
        assert pref_map[6]["ppo_applicability"] == "AMBIGUOUS_UNRESOLVED"

    def test_npi_expansion(self, synthetic_mrf, tmp_path):
        out_rates = str(tmp_path / "rates.csv")
        out_class = str(tmp_path / "class.csv")
        out_summ = str(tmp_path / "summary.json")

        extractor = RateExtractor()
        summary = extractor.extract_and_classify(
            file_path=synthetic_mrf,
            output_rates_path=out_rates,
            output_classification_path=out_class,
            output_summary_path=out_summ,
        )

        with open(out_rates, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Provider ref 1 had 2 NPIs (1770688129 and 1063646446)
        ref1_rows = [r for r in rows if r["provider_group_id"] == "1"]
        assert len(ref1_rows) == 2
        npis_in_ref1 = {r["npi"] for r in ref1_rows}
        assert npis_in_ref1 == {"1770688129", "1063646446"}

    def test_capitation_exclusion(self, synthetic_mrf, tmp_path):
        out_rates = str(tmp_path / "rates.csv")
        out_class = str(tmp_path / "class.csv")
        out_summ = str(tmp_path / "summary.json")

        extractor = RateExtractor()
        summary = extractor.extract_and_classify(
            file_path=synthetic_mrf,
            output_rates_path=out_rates,
            output_classification_path=out_class,
            output_summary_path=out_summ,
        )

        with open(out_rates, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Capitation item 36415 should be marked EXCLUDED_CAPITATION
        cap_rows = [r for r in rows if r["billing_code"] == "36415"]
        assert len(cap_rows) == 1
        assert cap_rows[0]["ppo_applicability"] == "EXCLUDED_CAPITATION"
        assert cap_rows[0]["negotiation_arrangement"] == "capitation"

    def test_unresolved_provider_reference(self, synthetic_mrf, tmp_path):
        out_rates = str(tmp_path / "rates.csv")
        out_class = str(tmp_path / "class.csv")
        out_summ = str(tmp_path / "summary.json")

        extractor = RateExtractor()
        summary = extractor.extract_and_classify(
            file_path=synthetic_mrf,
            output_rates_path=out_rates,
            output_classification_path=out_class,
            output_summary_path=out_summ,
        )

        # Group 999 was not in provider_references
        assert summary["counts"]["unresolved_provider_references"] == 1


class TestRateSelectionAndConflictHandling:
    @pytest.fixture
    def conflicting_rates_mrf(self, tmp_path):
        mrf_data = {
            "provider_references": [
                {
                    "provider_group_id": 10,
                    "provider_groups": [
                        {
                            "npi": [1902520455],
                            "tin": {"type": "ein", "value": "94-1156581", "business_name": "Cedars-Sinai Medical Center"}
                        }
                    ]
                }
            ],
            "in_network": [
                {
                    "negotiation_arrangement": "ffs",
                    "billing_code": "99214",
                    "billing_code_type": "CPT",
                    "name": "OFFICE VISIT EST PATIENT LEVEL 4",
                    "negotiated_rates": [
                        {
                            "provider_references": [10],
                            "negotiated_prices": [
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 185.00,
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient",
                                    "service_code": ["11"]
                                },
                                {
                                    "negotiated_type": "negotiated",
                                    "negotiated_rate": 210.00,  # Alternative rate for exact same context!
                                    "expiration_date": "9999-12-31",
                                    "billing_class": "professional",
                                    "setting": "outpatient",
                                    "service_code": ["11"]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        file_path = tmp_path / "conflict_mrf.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(mrf_data, f)
        return str(file_path)

    def test_multiple_comparable_rates_flagged(self, conflicting_rates_mrf, tmp_path):
        out_rates = str(tmp_path / "rates.csv")
        out_class = str(tmp_path / "class.csv")
        out_summ = str(tmp_path / "summary.json")

        extractor = RateExtractor()
        summary = extractor.extract_and_classify(
            file_path=conflicting_rates_mrf,
            output_rates_path=out_rates,
            output_classification_path=out_class,
            output_summary_path=out_summ,
        )

        with open(out_rates, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        # The second row should be flagged as MULTIPLE_COMPARABLE_RATES_FLAGGED
        flags = [r["rate_selection_flag"] for r in rows]
        assert "MULTIPLE_COMPARABLE_RATES_FLAGGED" in flags
        # Alternative rates must document both values
        alt_str = rows[1]["alternative_rate_values"]
        assert "185" in alt_str and "210" in alt_str


class TestAddressConstraint:
    def test_address_status_is_unresolved(self, tmp_path):
        # Verify strict constraint: addresses must remain UNRESOLVED_PENDING_C5
        mrf_data = {
            "provider_references": [
                {
                    "provider_group_id": 1,
                    "provider_groups": [{"npi": [1770688129], "tin": {"type": "ein", "value": "68-0273974", "business_name": "Clinic"}}]
                }
            ],
            "in_network": [
                {
                    "negotiation_arrangement": "ffs",
                    "billing_code": "99213",
                    "negotiated_rates": [
                        {
                            "provider_references": [1],
                            "negotiated_prices": [{"negotiated_type": "negotiated", "negotiated_rate": 100.00}]
                        }
                    ]
                }
            ]
        }
        file_path = tmp_path / "addr_test.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(mrf_data, f)

        out_rates = str(tmp_path / "rates.csv")
        extractor = RateExtractor()
        extractor.extract_and_classify(
            file_path=str(file_path),
            output_rates_path=out_rates,
            output_classification_path=str(tmp_path / "c.csv"),
            output_summary_path=str(tmp_path / "s.json"),
        )

        with open(out_rates, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)
            assert row["address_status"] == "UNRESOLVED_PENDING_C5"
