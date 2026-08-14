# scripts/recon/probe_india_code.py
"""Probe: India Code Central Acts browse/search.

See docs/LEGAL_DATA_SOURCES.md §3 and
docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.3.
"""

from __future__ import annotations

import re

from legal_ai.sources.licensing import get_licence
from scripts.recon.common import ProbeReport, now_iso, polite_get

SOURCE = "india_code"
BROWSE_URL = "https://www.indiacode.nic.in/handle/123456789/1362"
# BROWSE_URL is a nav menu with no item count. The count lives on this
# DSpace browse-by-title listing page instead.
LISTING_URL = "https://www.indiacode.nic.in/handle/123456789/1362/browse?type=shorttitle"
SAMPLE_SEARCH_URL = (
    "https://www.indiacode.nic.in/handle/123456789/1362/"
    "simple-search?query=specific+relief+act"
)

# DSpace listing format: "Showing items 1 to 20 of 845".
_COUNT_PATTERN = re.compile(r"showing items\s+[\d,]+\s+to\s+[\d,]+\s+of\s+([\d,]+)", re.IGNORECASE)
_TAG_PATTERN = re.compile(r"<[^>]+>")


def estimate_act_count(html: str) -> int | None:
    match = _COUNT_PATTERN.search(html)
    return int(match.group(1).replace(",", "")) if match else None


def run() -> ProbeReport:
    notes: list[str] = []

    browse_response = polite_get(BROWSE_URL)
    reachable = browse_response.status_code == 200

    act_count = None
    if reachable:
        listing_response = polite_get(LISTING_URL)
        if listing_response.status_code == 200:
            act_count = estimate_act_count(listing_response.text)
            if act_count is None:
                notes.append(
                    "listing page was reachable but its 'Showing items ... of N' "
                    "text did not match the expected DSpace format — inspect "
                    f"{LISTING_URL} by hand"
                )
        else:
            notes.append(f"listing page returned HTTP {listing_response.status_code}")
    else:
        notes.append(f"browse page returned HTTP {browse_response.status_code}")

    search_response = polite_get(SAMPLE_SEARCH_URL)
    # Result rows wrap each matched word in its own highlight tag, splitting
    # "specific relief" apart in the raw HTML — strip tags before matching.
    search_text = _TAG_PATTERN.sub(" ", search_response.text).lower()
    search_text = " ".join(search_text.split())
    if search_response.status_code != 200 or "specific relief" not in search_text:
        notes.append("sample search for 'Specific Relief Act' did not return the expected result")

    notes.append(
        "India Code exposes no JSON API — every field must come from HTML "
        "scraping of the browse/search/detail pages."
    )

    licence = get_licence(SOURCE)

    return ProbeReport(
        source=SOURCE,
        reachable=reachable,
        auth_required=False,
        access_method="html_scrape",
        sample_fields=["act_title", "act_url"],
        approx_volume={"central_acts_count": act_count},
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
