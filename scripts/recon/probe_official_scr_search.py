"""Probe: the official Supreme Court Reports search portal.

See docs/LEGAL_DATA_SOURCES.md §4 and
docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.3.
"""

from __future__ import annotations

import re

from legal_ai.sources.licensing import get_licence
from scripts.recon.common import ProbeReport, now_iso, polite_get

SOURCE = "official_scr_search"
SEARCH_URL = "https://scr.sci.gov.in/scrsearch/"

_SPA_SHELL_PATTERN = re.compile(r'id=["\'](app|root)["\']')
_POPULATED_ROW_PATTERN = re.compile(r"<tr[^>]*>.*?</tr>", re.IGNORECASE | re.DOTALL)

# Securimage (CAPTCHA lib) + csrf-magic.js — presence blocks scripted search.
_CAPTCHA_PATTERN = re.compile(r"securimage|csrf-magic", re.IGNORECASE)


def detect_rendering_mode(html: str) -> str:
    rows = _POPULATED_ROW_PATTERN.findall(html)
    has_real_rows = any(re.search(r"<td", row, re.IGNORECASE) for row in rows)
    if has_real_rows:
        return "server_rendered"
    if _CAPTCHA_PATTERN.search(html):
        return "captcha_protected"
    if _SPA_SHELL_PATTERN.search(html):
        return "js_spa"
    return "unknown"


def run() -> ProbeReport:
    notes: list[str] = []

    response = polite_get(SEARCH_URL)
    reachable = response.status_code == 200

    mode = "unknown"
    if reachable:
        mode = detect_rendering_mode(response.text)
        if mode == "captcha_protected":
            notes.append(
                "the page serves a Securimage CAPTCHA plus a csrf-magic.js "
                "token — any real search submission requires solving a "
                "CAPTCHA and carrying a session-bound CSRF token; this is "
                "not a rendering-mode problem, it's a bot-protection wall. "
                "Do not attempt to bypass it — use Bharat Courts' captcha "
                "solver (see bharat_courts probe) or manual verification "
                "instead of scripting around this portal directly"
            )
        elif mode == "js_spa":
            notes.append(
                "the page is a JavaScript SPA shell with no server-rendered "
                "results — this source is not scriptable with plain HTTP "
                "GETs; treat it as manual-verification-only for Phase 1"
            )
        elif mode == "unknown":
            notes.append(
                "could not determine rendering mode from the initial "
                "response — needs manual inspection before building a tool"
            )
    else:
        notes.append(f"search portal returned HTTP {response.status_code}")

    licence = get_licence(SOURCE)

    return ProbeReport(
        source=SOURCE,
        reachable=reachable,
        auth_required=False,
        access_method=mode,
        sample_fields=[],
        approx_volume={},
        formats=["html"],
        licence=licence.licence,
        attribution_required=licence.attribution_required,
        notes=notes,
        checked_at=now_iso(),
    )


if __name__ == "__main__":
    report = run()
    print(report.model_dump_json(indent=2))
    report.save()
