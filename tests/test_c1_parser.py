"""
tests/test_c1_parser.py
────────────────────────────────────────────────────────────────────────────────
Unit tests for C1 index parsing components.
Tests are offline — no network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from utils import normalize_url, url_fingerprint  # noqa: E402
from c1_index_parser import (  # noqa: E402
    parse_index_entry,
    build_unique_rate_files,
    infer_network_type,
)

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# URL normalization tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeUrl:

    def test_lowercase_scheme_and_host(self):
        url = "HTTPS://WWW.EXAMPLE.COM/path/to/file.json"
        result = normalize_url(url)
        assert result.startswith("https://www.example.com/")

    def test_trailing_slash_stripped(self):
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_root_slash_preserved(self):
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_percent20_decoded_and_reencoded(self):
        url = "https://www.centene.com/content/dam/centene/Centene%20Corporate/file.json"
        result = normalize_url(url)
        # %20 should be decoded to space and re-encoded as %20 in path
        assert "Centene%20Corporate" in result or "Centene Corporate" not in result

    def test_tracking_params_stripped(self):
        url = "https://example.com/file.json?utm_source=test&utm_campaign=x&real=1"
        result = normalize_url(url, strip_params=["utm_source", "utm_campaign"])
        assert "utm_source" not in result
        assert "utm_campaign" not in result
        assert "real=1" in result

    def test_empty_string_returns_empty(self):
        assert normalize_url("") == ""

    def test_none_returns_empty(self):
        assert normalize_url(None) == ""  # type: ignore[arg-type]

    def test_whitespace_stripped(self):
        assert normalize_url("  https://example.com/file.json  ") == "https://example.com/file.json"


class TestUrlFingerprint:

    def test_same_url_same_fingerprint(self):
        u1 = "https://example.com/file.json"
        u2 = "https://example.com/file.json"
        assert url_fingerprint(u1) == url_fingerprint(u2)

    def test_different_url_different_fingerprint(self):
        u1 = "https://example.com/file1.json"
        u2 = "https://example.com/file2.json"
        assert url_fingerprint(u1) != url_fingerprint(u2)

    def test_trailing_slash_same_fingerprint(self):
        u1 = "https://example.com/path"
        u2 = "https://example.com/path/"
        assert url_fingerprint(u1) == url_fingerprint(u2)

    def test_fingerprint_length(self):
        fp = url_fingerprint("https://example.com/file.json")
        assert len(fp) == 16


# ─────────────────────────────────────────────────────────────────────────────
# Network type inference tests
# ─────────────────────────────────────────────────────────────────────────────

class TestInferNetworkType:

    def test_ppo_in_plan_name(self):
        net_type, evidence = infer_network_type("Health Net Silver PPO 5000")
        assert net_type == "PPO"
        assert evidence.upper() == "PPO"

    def test_hmo_in_plan_name(self):
        net_type, evidence = infer_network_type("Blue Cross HMO Plan")
        assert net_type == "HMO"

    def test_ppo_case_insensitive(self):
        net_type, _ = infer_network_type("preferred provider plan")
        assert net_type == "PPO"

    def test_unknown_when_no_match(self):
        net_type, evidence = infer_network_type("Elite Gold + Vision + Adult Dental")
        assert net_type == "UNKNOWN"
        assert evidence == ""

    def test_epo_detected(self):
        net_type, _ = infer_network_type("Ambetter EPO 3000")
        assert net_type == "EPO"

    def test_empty_string_unknown(self):
        net_type, _ = infer_network_type("")
        assert net_type == "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
# parse_index_entry tests (offline)
# ─────────────────────────────────────────────────────────────────────────────

MINIMAL_INDEX = {
    "reporting_entity_name": "Centene Management Company LLC",
    "reporting_entity_type": "Third Party Administrator",
    "last_updated_on": "2024-10-01",
    "version": "2.0.0",
    "reporting_structure": [
        {
            "reporting_plans": [
                {
                    "plan_name": "Health Net Gold PPO 500",
                    "plan_id_type": "hios",
                    "plan_id": "68765CA001",
                    "plan_market_type": "large_group",
                    "issuer_name": "Health Net",
                }
            ],
            "in_network_files": [
                {
                    "description": "In-Network Rates",
                    "location": "https://example.com/in_network.json.gz",
                }
            ],
            "allowed_amounts_files": [
                {
                    "description": "Out-of-Network Allowed Amounts",
                    "location": "https://example.com/allowed_amounts.json.gz",
                }
            ],
        }
    ],
}


class TestParseIndexEntry:

    def _parse(self, index_data=None):
        return parse_index_entry(
            brand="Health Net",
            source_index_url="https://www.centene.com/healthnet_index.json",
            index_data=index_data or MINIMAL_INDEX,
            retrieved_at="2024-10-17T00:00:00Z",
        )

    def test_returns_two_rows_per_plan(self):
        rows, skipped = self._parse()
        # 1 plan × 2 file types (in_network + allowed_amounts)
        assert len(rows) == 2
        assert skipped == []

    def test_brand_propagated(self):
        rows, _ = self._parse()
        assert all(r["brand"] == "Health Net" for r in rows)

    def test_plan_name_captured(self):
        rows, _ = self._parse()
        plan_names = {r["plan_name"] for r in rows}
        assert "Health Net Gold PPO 500" in plan_names

    def test_ppo_inferred_from_plan_name(self):
        rows, _ = self._parse()
        # Both rows (in_network + allowed_amounts) for this plan should be PPO
        assert any(r["network_type"] == "PPO" for r in rows)

    def test_url_normalised(self):
        rows, _ = self._parse()
        for r in rows:
            assert r["rate_file_url"] == r["rate_file_url"].strip()
            assert "  " not in r["rate_file_url"]

    def test_file_type_recorded(self):
        rows, _ = self._parse()
        types = {r["file_type"] for r in rows}
        assert "in_network" in types
        assert "allowed_amounts" in types

    def test_missing_location_logged_as_skipped(self):
        bad_index = {
            **MINIMAL_INDEX,
            "reporting_structure": [
                {
                    "reporting_plans": MINIMAL_INDEX["reporting_structure"][0]["reporting_plans"],
                    "in_network_files": [{"description": "test", "location": ""}],
                    "allowed_amounts_files": [],
                }
            ],
        }
        rows, skipped = self._parse(bad_index)
        assert len(skipped) >= 1
        assert all("missing 'location'" in s for s in skipped)

    def test_missing_reporting_structure(self):
        bad_index = {"reporting_entity_name": "X", "version": "2.0.0"}
        rows, skipped = self._parse(bad_index)
        assert rows == []
        assert len(skipped) == 1
        assert "reporting_structure" in skipped[0]

    def test_empty_plan_list(self):
        """A rate file with no plans should produce one row with empty plan fields."""
        no_plan_index = {
            **MINIMAL_INDEX,
            "reporting_structure": [
                {
                    "reporting_plans": [],
                    "in_network_files": [
                        {"description": "rates", "location": "https://example.com/rates.json"}
                    ],
                    "allowed_amounts_files": [],
                }
            ],
        }
        rows, skipped = self._parse(no_plan_index)
        assert len(rows) == 1
        assert rows[0]["plan_name"] == ""
        assert rows[0]["rate_file_url"] == "https://example.com/rates.json"

    def test_source_index_url_recorded(self):
        rows, _ = self._parse()
        assert all(
            r["source_index_url"] == "https://www.centene.com/healthnet_index.json"
            for r in rows
        )

    def test_retrieved_at_recorded(self):
        rows, _ = self._parse()
        assert all(r["retrieved_at"] == "2024-10-17T00:00:00Z" for r in rows)


# ─────────────────────────────────────────────────────────────────────────────
# build_unique_rate_files tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildUniqueRateFiles:

    def _make_df(self):
        rows, _ = parse_index_entry(
            brand="Health Net",
            source_index_url="https://example.com/index.json",
            index_data=MINIMAL_INDEX,
            retrieved_at="2024-10-17T00:00:00Z",
        )
        return pd.DataFrame(rows)

    def test_dedup_same_url(self):
        """Two plans pointing to the same in-network file → 1 unique row."""
        two_plan_index = {
            **MINIMAL_INDEX,
            "reporting_structure": [
                {
                    "reporting_plans": [
                        {
                            "plan_name": "Plan A PPO",
                            "plan_id": "001",
                            "plan_id_type": "hios",
                            "plan_market_type": "large_group",
                            "issuer_name": "Health Net",
                        },
                        {
                            "plan_name": "Plan B PPO",
                            "plan_id": "002",
                            "plan_id_type": "hios",
                            "plan_market_type": "large_group",
                            "issuer_name": "Health Net",
                        },
                    ],
                    "in_network_files": [
                        {"description": "Rates", "location": "https://example.com/rates.json"}
                    ],
                    "allowed_amounts_files": [],
                }
            ],
        }
        rows, _ = parse_index_entry(
            brand="Health Net",
            source_index_url="https://example.com/index.json",
            index_data=two_plan_index,
            retrieved_at="2024-10-17T00:00:00Z",
        )
        df = pd.DataFrame(rows)
        unique = build_unique_rate_files(df)
        # Both plans share same URL → 1 unique rate file
        assert len(unique) == 1
        assert unique.iloc[0]["plan_count"] == 2

    def test_empty_df_returns_empty(self):
        result = build_unique_rate_files(pd.DataFrame())
        assert result.empty

    def test_plan_count_accurate(self):
        df = self._make_df()
        unique = build_unique_rate_files(df)
        # Each URL has only 1 plan
        assert (unique["plan_count"] >= 1).all()

    def test_url_dedup_by_fingerprint(self):
        """URL with trailing slash vs without should deduplicate."""
        index_slash = {
            **MINIMAL_INDEX,
            "reporting_structure": [
                {
                    "reporting_plans": MINIMAL_INDEX["reporting_structure"][0]["reporting_plans"],
                    "in_network_files": [
                        {"description": "A", "location": "https://example.com/rates.json/"},
                        {"description": "B", "location": "https://example.com/rates.json"},
                    ],
                    "allowed_amounts_files": [],
                }
            ],
        }
        rows, _ = parse_index_entry(
            brand="Health Net",
            source_index_url="https://example.com/index.json",
            index_data=index_slash,
            retrieved_at="2024-10-17T00:00:00Z",
        )
        df = pd.DataFrame(rows)
        unique = build_unique_rate_files(df)
        # Trailing slash normalisation → 1 unique URL
        assert len(unique) == 1
