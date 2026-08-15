# scripts/recon/common.py
"""Shared infrastructure for the Phase 1 data-source probe scripts.

See docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.2.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from pydantic import BaseModel

USER_AGENT = (
    "PramanaAI-Recon/0.1 (Indian Legal Intelligence data recon; "
    "low-volume, non-commercial research probe)"
)
DEFAULT_TIMEOUT = 12
MIN_DELAY_SECONDS = 1.0

REPORTS_DIR = Path("data/recon/reports")
SAMPLES_DIR = Path("data/recon/samples")

_last_request_at: dict[str, float] = {}


class ProbeReport(BaseModel):
    source: str
    reachable: bool
    auth_required: bool
    access_method: str
    sample_fields: list[str] = []
    approx_volume: dict[str, Any] = {}
    formats: list[str] = []
    licence: str
    attribution_required: bool
    notes: list[str] = []
    checked_at: str

    def save(self, directory: Path = REPORTS_DIR) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.source}.json"
        path.write_text(self.model_dump_json(indent=2))
        return path


def polite_get(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
    **kwargs: Any,
) -> requests.Response:
    """A `requests.get` that identifies itself and rate-limits per host."""
    host = urlparse(url).netloc
    now = time.monotonic()
    last = _last_request_at.get(host)
    if last is not None:
        elapsed = now - last
        if elapsed < MIN_DELAY_SECONDS:
            time.sleep(MIN_DELAY_SECONDS - elapsed)

    merged_headers = {"User-Agent": USER_AGENT}
    if headers:
        merged_headers.update(headers)

    response = requests.get(url, timeout=timeout, headers=merged_headers, **kwargs)
    _last_request_at[urlparse(url).netloc] = time.monotonic()
    return response


def save_sample(
    content: bytes,
    source: str,
    filename: str,
    base_dir: Path = SAMPLES_DIR,
) -> Path:
    directory = base_dir / source
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(content)
    return path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
