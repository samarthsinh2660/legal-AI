"""Polite, identified HTTP for every production source adapter.

Same rate-limiting discipline as scripts/recon/common.py's polite_get,
promoted here for production ingestion code — see
docs/PROJECT_STRUCTURE.md §6 (probes and tools are separate code).
"""

from __future__ import annotations

import time
from typing import Any, Optional
from urllib.parse import urlparse

import requests

USER_AGENT = "PramanaAI-Ingestion/0.1 (legal-ai; Indian Legal Intelligence data layer)"
DEFAULT_TIMEOUT = 12
MIN_DELAY_SECONDS = 1.0
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0

_last_request_at: dict[str, float] = {}


def polite_get(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
    max_retries: int = MAX_RETRIES,
    **kwargs: Any,
) -> requests.Response:
    """A rate-limited GET that retries transient network failures.

    A single SSL handshake timeout or dropped connection over an 800+
    request run should not crash the whole run — see the real failure
    that motivated this: docs/superpowers/plans/2026-08-15-ingestion-core-india-code-plan.md
    Task 12's live run hit exactly this on request ~87.
    """
    host = urlparse(url).netloc
    merged_headers = {"User-Agent": USER_AGENT}
    if headers:
        merged_headers.update(headers)

    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        now = time.monotonic()
        last = _last_request_at.get(host)
        if last is not None:
            elapsed = now - last
            if elapsed < MIN_DELAY_SECONDS:
                time.sleep(MIN_DELAY_SECONDS - elapsed)

        try:
            response = requests.get(url, timeout=timeout, headers=merged_headers, **kwargs)
            _last_request_at[urlparse(url).netloc] = time.monotonic()
            return response
        except requests.exceptions.RequestException as exc:
            last_error = exc
            _last_request_at[urlparse(url).netloc] = time.monotonic()
            if attempt < max_retries:
                time.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))

    assert last_error is not None
    raise last_error
