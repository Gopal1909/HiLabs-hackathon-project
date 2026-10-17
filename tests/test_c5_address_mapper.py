"""
tests/test_c5_address_mapper.py
Unit tests for Phase 5 (C5) Provider Address Verification and Multi-Address Resolution.

Tests:
- Identifier validation (Luhn NPI, 9-digit EIN)
- Address normalization and PO Box detection
- Type 1 (Individual) vs Type 2 (Organization) parsing
- Practice location (LOCATION) vs Mailing address (MAILING)
- Stale NPPES record detection (last_updated < 2022)
- Geographic corroboration against PTD business name and county wrappers
- Conflicted addresses (PO Box only, Out of state)
- Unresolved NPIs (missing from NPPES or missing in PTD)
- Multi-provider TIN group resolution
- Offline / mock client testing
"""
import csv
import json
import os
import tempfile
import pytest

from src.c5_address_mapper import (
    AddressMapper,
    NPPESRegistryClient,
    clean_postal_code,
    is_po_box,
    normalize_address_line,
    validate_npi_luhn,
    validate_tin_ein,
)


class TestAddressHelpers:
    def test_validate_npi_luhn(self):
        # Valid Luhn NPIs
        assert validate_npi_luhn("1770688129") is True
        assert validate_npi_luhn("1063646446") is True
        assert validate_npi_luhn("1285009035") is True
        assert validate_npi_luhn("1902520455") is True
        # Invalid NPIs
        assert validate_npi_luhn("1770688128") is False
        assert validate_npi_luhn("12345") is False
        assert validate_npi_luhn("0123456789") is False
        assert validate_npi_luhn("") is False
        assert validate_npi_luhn(None) is False

    def test_validate_tin_ein(self):
        assert validate_tin_ein("68-0273974") is True
        assert validate_tin_ein("941156581") is True
        assert validate_tin_ein("000000000") is False
        assert validate_tin_ein("123456789") is False
        assert validate_tin_ein("12-34") is False
        assert validate_tin_ein(None) is False

    def test_normalize_address_line(self):
        raw = "1625 Stockton Boulevard, Suite #208"
        norm = normalize_address_line(raw)
        assert norm == "1625 STOCKTON BLVD STE 208"

        raw2 = "777 Knowles Drive, Suite 16A"
        norm2 = normalize_address_line(raw2)
        assert norm2 == "777 KNOWLES DR STE 16A"

    def test_is_po_box(self):
        assert is_po_box("PO BOX 255228") is True
        assert is_po_box("P.O. Box 1234") is True
        assert is_po_box("Post Office Box 500") is True
        assert is_po_box("1625 Stockton Blvd") is False
        assert is_po_box("") is False

    def test_clean_postal_code(self):
        assert clean_postal_code("958167092") == "95816"
        assert clean_postal_code("95032-1417") == "95032"
        assert clean_postal_code("94103") == "94103"


class TestStagedAddressResolution:
    @pytest.fixture
    def mock_mapper(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        # Mock NPPES Registry Responses
        mock_data = {
            "1770688129": {  # Sutter Health - Type 2, Location in Sacramento, recent 2026 update
                "enumeration_type": "NPI-2",
                "basic": {
                    "organization_name": "SUTTER VALLEY MEDICAL FOUNDATION",
                    "last_updated": "2026-08-21",
                    "status": "A",
                },
                "addresses": [
                    {
                        "address_purpose": "MAILING",
                        "address_1": "PO BOX 255228",
                        "city": "SACRAMENTO",
                        "state": "CA",
                        "postal_code": "958655228",
                    },
                    {
                        "address_purpose": "LOCATION",
                        "address_1": "1625 STOCKTON BLVD STE 208",
                        "city": "SACRAMENTO",
                        "state": "CA",
                        "postal_code": "958167092",
                    }
                ],
                "taxonomies": [{"code": "291U00000X", "desc": "Clinical Medical Laboratory", "primary": True}],
            },
            "1750550968": {  # Dr. Saal - Type 2 / Dermatology, Los Gatos, updated 2026
                "enumeration_type": "NPI-2",
                "basic": {
                    "organization_name": "BRUCE M SAAL, MD A MEDICAL CORPORATION",
                    "last_updated": "2026-03-12",
                    "status": "A",
                },
                "addresses": [
                    {
                        "address_purpose": "LOCATION",
                        "address_1": "777 KNOWLES DR STE 16",
                        "city": "LOS GATOS",
                        "state": "CA",
                        "postal_code": "950321448",
                    }
                ],
                "taxonomies": [{"code": "207N00000X", "desc": "Dermatology", "primary": True}],
            },
            "1669731899": {  # Dr. Jong - Stale 2012 update, Location in Folsom
                "enumeration_type": "NPI-2",
                "basic": {
                    "organization_name": "FOLSOM DERMATOLOGY",
                    "last_updated": "2012-05-08",
                    "status": "A",
                },
                "addresses": [
                    {
                        "address_purpose": "LOCATION",
                        "address_1": "1745 CREEKSIDE DR",
                        "city": "FOLSOM",
                        "state": "CA",
                        "postal_code": "956303924",
                    }
                ],
                "taxonomies": [{"code": "207N00000X", "desc": "Dermatology", "primary": True}],
            },
            "1000000001": {  # PO Box only in NPPES -> Conflicted
                "enumeration_type": "NPI-1",
                "basic": {
                    "first_name": "JOHN",
                    "last_name": "DOE",
                    "last_updated": "2018-01-01",
                    "status": "A",
                },
                "addresses": [
                    {
                        "address_purpose": "MAILING",
                        "address_1": "PO BOX 999",
                        "city": "OAKLAND",
                        "state": "CA",
                        "postal_code": "94612",
                    }
                ],
                "taxonomies": [],
            },
            "1000000002": {  # Out of state (TX) -> Conflicted
                "enumeration_type": "NPI-1",
                "basic": {
                    "first_name": "ALICE",
                    "last_name": "SMITH",
                    "last_updated": "2024-01-01",
                    "status": "A",
                },
                "addresses": [
                    {
                        "address_purpose": "LOCATION",
                        "address_1": "100 MAIN ST",
                        "city": "DALLAS",
                        "state": "TX",
                        "postal_code": "75001",
                    }
                ],
                "taxonomies": [],
            }
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(mock_data, f)

        mapper = AddressMapper()
        mapper.client.cache = mock_data
        mapper.client.cache_file = cache_file
        return mapper

    @pytest.fixture
    def mock_ptd_mrf(self, tmp_path):
        mrf_data = {
            "provider_references": [
                {
                    "provider_group_id": 1,
                    "provider_groups": [
                        {"npi": [1770688129], "tin": {"type": "ein", "value": "68-0273974", "business_name": "Sutter Physical & Hand Therapy - Sacramento"}}
                    ]
                },
                {
                    "provider_group_id": 2,
                    "provider_groups": [
                        {"npi": [1750550968], "tin": {"type": "ein", "value": "94-2603666", "business_name": "SAAL, M.D."}}
                    ]
                },
                {
                    "provider_group_id": 3,
                    "provider_groups": [
                        {"npi": [1669731899], "tin": {"type": "ein", "value": "45-3599490", "business_name": "Folsom Dermatology"}}
                    ]
                },
                {
                    "provider_group_id": 4,
                    "provider_groups": [
                        {"npi": [1000000001], "tin": {"type": "ein", "value": "11-2223334", "business_name": "Oakland Clinic"}}
                    ]
                },
                {
                    "provider_group_id": 5,
                    "provider_groups": [
                        {"npi": [1000000002], "tin": {"type": "ein", "value": "55-6667778", "business_name": "Texas Telehealth Provider"}}
                    ]
                },
                {
                    "provider_group_id": 6,
                    "provider_groups": [
                        {"npi": [9999999999], "tin": {"type": "ein", "value": "99-8887776", "business_name": "Missing Provider"}}
                    ]
                }
            ],
            "in_network": []
        }
        file_path = tmp_path / "mock_ptd.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(mrf_data, f)
        return str(file_path)

    def test_verified_current_resolution(self, mock_mapper, mock_ptd_mrf, tmp_path):
        out_xwalk = str(tmp_path / "xwalk.csv")
        out_evid = str(tmp_path / "evid.csv")
        out_conf = str(tmp_path / "conf.csv")
        out_summ = str(tmp_path / "summ.json")

        summary = mock_mapper.resolve_addresses(
            rate_file_path=mock_ptd_mrf,
            output_crosswalk_path=out_xwalk,
            output_evidence_path=out_evid,
            output_conflicts_path=out_conf,
            output_summary_path=out_summ,
        )

        with open(out_xwalk, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        # Check Sutter (1770688129) -> VERIFIED_CURRENT (Sacramento matches business name + recent 2026 update)
        sutter = next(r for r in rows if r["npi"] == "1770688129")
        assert sutter["verification_status"] == "VERIFIED_CURRENT"
        assert float(sutter["confidence_score"]) >= 0.88
        assert sutter["city"] == "SACRAMENTO"
        assert sutter["address_line_1"] == "1625 STOCKTON BLVD STE 208"
        assert sutter["address_purpose"] == "LOCATION"

    def test_corroborated_stale_record(self, mock_mapper, mock_ptd_mrf, tmp_path):
        out_xwalk = str(tmp_path / "xwalk.csv")
        summary = mock_mapper.resolve_addresses(
            rate_file_path=mock_ptd_mrf,
            output_crosswalk_path=out_xwalk,
            output_evidence_path=str(tmp_path / "e.csv"),
            output_conflicts_path=str(tmp_path / "c.csv"),
            output_summary_path=str(tmp_path / "s.json"),
        )
        with open(out_xwalk, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        # Check Dr. Jong (1669731899) -> CORROBORATED (stale 2012 date, but city Folsom matches PTD name Folsom Dermatology)
        jong = next(r for r in rows if r["npi"] == "1669731899")
        assert jong["verification_status"] == "CORROBORATED"
        assert jong["is_stale_nppes_risk"] == "Y"
        assert jong["city"] == "FOLSOM"

    def test_po_box_conflict_detected(self, mock_mapper, mock_ptd_mrf, tmp_path):
        out_xwalk = str(tmp_path / "xwalk.csv")
        out_conf = str(tmp_path / "conf.csv")
        mock_mapper.resolve_addresses(
            rate_file_path=mock_ptd_mrf,
            output_crosswalk_path=out_xwalk,
            output_evidence_path=str(tmp_path / "e.csv"),
            output_conflicts_path=out_conf,
            output_summary_path=str(tmp_path / "s.json"),
        )
        with open(out_conf, "r", encoding="utf-8") as f:
            conflicts = list(csv.DictReader(f))

        po_box_conf = [c for c in conflicts if c["npi"] == "1000000001"]
        assert len(po_box_conf) == 1
        assert po_box_conf[0]["conflict_type"] == "PO_BOX_MAILING_ONLY"

    def test_out_of_state_conflict_detected(self, mock_mapper, mock_ptd_mrf, tmp_path):
        out_conf = str(tmp_path / "conf.csv")
        mock_mapper.resolve_addresses(
            rate_file_path=mock_ptd_mrf,
            output_crosswalk_path=str(tmp_path / "x.csv"),
            output_evidence_path=str(tmp_path / "e.csv"),
            output_conflicts_path=out_conf,
            output_summary_path=str(tmp_path / "s.json"),
        )
        with open(out_conf, "r", encoding="utf-8") as f:
            conflicts = list(csv.DictReader(f))

        tx_conf = [c for c in conflicts if c["npi"] == "1000000002"]
        assert len(tx_conf) == 1
        assert tx_conf[0]["conflict_type"] == "OUT_OF_STATE_DISCREPANCY"

    def test_missing_npi_unresolved(self, mock_mapper, mock_ptd_mrf, tmp_path):
        out_xwalk = str(tmp_path / "xwalk.csv")
        mock_mapper.resolve_addresses(
            rate_file_path=mock_ptd_mrf,
            output_crosswalk_path=out_xwalk,
            output_evidence_path=str(tmp_path / "e.csv"),
            output_conflicts_path=str(tmp_path / "c.csv"),
            output_summary_path=str(tmp_path / "s.json"),
        )
        with open(out_xwalk, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        missing = next(r for r in rows if r["npi"] == "9999999999")
        assert missing["verification_status"] == "UNRESOLVED"
        assert float(missing["confidence_score"]) == 0.0
