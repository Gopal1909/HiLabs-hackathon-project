"""
src/utils.py
Shared utilities: logging, configuration loading, URL normalization, HTTP helpers.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests
import yaml

# ── Project root ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_project_root() -> Path:
    """Return the absolute path to the project root directory."""
    return PROJECT_ROOT


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load YAML configuration from config/settings.yaml (or a custom path).

    Returns a dict; all paths are resolved relative to the project root so
    that callers can use them directly with open() or Path().
    """
    if config_path is None:
        config_path = PROJECT_ROOT / "config" / "settings.yaml"

    with open(config_path, "r", encoding="utf-8") as fh:
        cfg: Dict[str, Any] = yaml.safe_load(fh)

    # Resolve relative output/data paths against project root
    dir_keys = ("outputs_dir", "raw_data_dir", "processed_data_dir", "logs_dir", "reports_dir")
    for key in dir_keys:
        if key in cfg:
            cfg[key] = str(PROJECT_ROOT / cfg[key])

    file_keys = (
        "plan_index_csv",
        "unique_rate_files_csv",
        "index_parsing_summary_json",
        "ppo_plan_candidates_csv",
        "ppo_network_files_csv",
        "c2_evidence_log_csv",
        "c2_summary_json",
        "c2_ppo_logic_md",
        "c3_file_quality_metrics_csv",
        "c3_metric_details_csv",
        "c3_summary_json",
        "c3_quality_methodology_md",
        "benchmark_weights_xlsx",
        "target_rate_file_path",
        "c4_extracted_rates_csv",
        "c4_ppo_rate_classification_csv",
        "c4_extraction_summary_json",
        "c4_extraction_methodology_md",
        "c5_provider_address_crosswalk_csv",
        "c5_address_evidence_csv",
        "c5_address_conflicts_csv",
        "c5_address_summary_json",
        "c5_address_methodology_md",
        "nppes_cache_file",
        "c6_curated_benchmark_rates_csv",
        "c6_curated_ppo_rates_csv",
        "c6_curated_ppo_rates_xlsx",
        "c6_curation_summary_json",
        "c6_pipeline_summary_md",
        "c7_provider_cost_effectiveness_csv",
        "c7_peer_group_summary_csv",
        "c7_summary_json",
        "c7_cost_effectiveness_methodology_md",
    )
    for key in file_keys:
        if key in cfg:
            cfg[key] = str(PROJECT_ROOT / cfg[key])

    return cfg


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """
    Configure the root logger.  Returns the module-level logger.
    If log_file is given the handler also writes to that file (append mode).
    """
    fmt = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO),
                        format=fmt, datefmt=datefmt, handlers=handlers)
    return logging.getLogger(__name__)


# ── URL normalization ─────────────────────────────────────────────────────────

def normalize_url(raw_url: str, strip_params: Optional[List[str]] = None) -> str:
    """
    Canonical URL normalization rules:
      1. Strip leading/trailing whitespace.
      2. Parse with urllib.parse.urlparse.
      3. Lowercase scheme and netloc (host is case-insensitive per RFC 3986).
      4. Decode then re-encode the path to remove spurious %20 variants.
      5. Remove trailing slash from path (unless path == '/').
      6. Drop specified query-string parameters (tracking params etc.).
      7. Drop the fragment.
    Returns the normalised URL string.
    """
    raw_url = (raw_url or "").strip()
    if not raw_url:
        return ""

    parsed = urllib.parse.urlparse(raw_url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Decode then re-encode path: handles %20 variants consistently
    path = urllib.parse.unquote(parsed.path)
    path = urllib.parse.quote(path, safe="/:@!$&'()*+,;=")
    path = path.rstrip("/") if path != "/" else path

    # Remove unwanted query params
    if parsed.query:
        qs_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if strip_params:
            qs_pairs = [(k, v) for k, v in qs_pairs
                        if k.lower() not in {p.lower() for p in strip_params}]
        query = urllib.parse.urlencode(qs_pairs)
    else:
        query = ""

    normalised = urllib.parse.urlunparse((scheme, netloc, path, "", query, ""))
    return normalised


def url_fingerprint(url: str) -> str:
    """SHA-256 hex digest of the normalised URL (first 16 chars for readability)."""
    canonical = normalize_url(url)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

class HttpClient:
    """
    Simple HTTP client wrapping requests with configurable retry/backoff,
    user-agent, and streaming support.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.timeout = int(cfg.get("http_timeout_seconds", 60))
        self.chunk_size = int(cfg.get("http_chunk_size", 65536))
        self.max_retries = int(cfg.get("max_retries", 3))
        self.backoff = float(cfg.get("retry_backoff_factor", 2))
        self.headers = {
            "User-Agent": cfg.get("user_agent", "CentenePTDParser/1.0"),
            "Accept": "application/json, */*",
            "Accept-Encoding": "gzip, deflate",
        }
        self._logger = logging.getLogger(self.__class__.__name__)

    def get_json(self, url: str) -> Tuple[Optional[Any], Optional[str]]:
        """
        Fetch *url* and parse response body as JSON.
        Returns (parsed_object, None) on success, (None, error_message) on failure.
        Uses streaming + incremental read to avoid loading enormous files whole.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.get(
                    url,
                    headers=self.headers,
                    timeout=self.timeout,
                    stream=True,
                )
                resp.raise_for_status()

                chunks: List[bytes] = []
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    chunks.append(chunk)
                raw = b"".join(chunks)
                resp.close()

                return json.loads(raw.decode("utf-8-sig")), None

            except requests.exceptions.HTTPError as exc:
                msg = f"HTTP {exc.response.status_code} for {url}"
                self._logger.warning("Attempt %d/%d: %s", attempt, self.max_retries, msg)
                if exc.response.status_code in (400, 403, 404, 410):
                    return None, msg   # non-retriable
            except requests.exceptions.RequestException as exc:
                msg = f"{type(exc).__name__}: {exc}"
                self._logger.warning("Attempt %d/%d: %s for %s", attempt, self.max_retries, msg, url)

            if attempt < self.max_retries:
                sleep_time = self.backoff ** attempt
                self._logger.debug("Sleeping %.1fs before retry", sleep_time)
                time.sleep(sleep_time)

        return None, f"All {self.max_retries} attempts failed for {url}"

    def head(self, url: str) -> Tuple[Optional[int], Optional[str]]:
        """Quick HEAD request. Returns (status_code, error_message)."""
        try:
            resp = requests.head(
                url, headers=self.headers, timeout=self.timeout, allow_redirects=True
            )
            return resp.status_code, None
        except requests.exceptions.RequestException as exc:
            return None, str(exc)


# ── Ensure directories exist ──────────────────────────────────────────────────

def ensure_directories(cfg: Dict[str, Any]) -> None:
    """Create all configured output/data directories if they don't exist."""
    for key in ("outputs_dir", "raw_data_dir", "processed_data_dir", "logs_dir", "reports_dir"):
        if key in cfg:
            os.makedirs(cfg[key], exist_ok=True)


# ── CMS Identifier Validation (Canonical Luhn Checksum & EIN Formats) ────────

def is_valid_npi(npi_val: Any) -> bool:
    """
    Validate a 10-digit National Provider Identifier (NPI) using the CMS
    standard Luhn check digit algorithm (ISO/IEC 7812 with '80840' prefix).
    Per CMS rules, valid NPIs must begin with '1' (individual) or '2' (organization).
    """
    if npi_val is None:
        return False
    s = str(npi_val).strip()
    if not (len(s) == 10 and s.isdigit()):
        return False
    if s[0] not in ('1', '2'):
        return False

    full = "80840" + s
    digits = [int(c) for c in full]

    total = 0
    double = True
    for d in reversed(digits[:-1]):
        if double:
            val = d * 2
            total += (val - 9) if val > 9 else val
        else:
            total += d
        double = not double

    check_digit = (10 - (total % 10)) % 10
    return check_digit == digits[-1]


def is_valid_ein(ein_val: Any) -> bool:
    """
    Validate 9-digit Employer Identification Number (TIN/EIN).
    Rejects dummy / trivial numbers (000000000, 111111111, 999999999, 123456789).
    """
    if ein_val is None:
        return False
    clean = re.sub(r'[-\s]', '', str(ein_val).strip())
    if len(clean) != 9 or not clean.isdigit():
        return False
    if clean in {"000000000", "111111111", "999999999", "123456789"}:
        return False
    return True
