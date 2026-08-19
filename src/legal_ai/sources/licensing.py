# src/legal_ai/sources/licensing.py
"""Known licence/attribution facts per data source.

Single source of truth for licensing claims — probes and, later, ingestion
adapters read from here rather than re-stating terms inline. See
docs/LEGAL_DATA_SOURCES.md §2 (source-of-truth hierarchy) and the
per-source sections it links.
"""

from __future__ import annotations

from pydantic import BaseModel


class LicenceInfo(BaseModel):
    source: str
    licence: str
    attribution_required: bool
    redistribution_allowed: bool
    notes: str


KNOWN_LICENCES: dict[str, LicenceInfo] = {
    "supreme_court_bulk": LicenceInfo(
        source="supreme_court_bulk",
        licence="CC-BY-4.0",
        attribution_required=True,
        redistribution_allowed=True,
        notes=(
            "Vanga indian-supreme-court-judgments corpus, storage sponsored "
            "by AWS Open Data. Bulk engineering source; the official SC "
            "portal remains the authority for the final document."
        ),
    ),
    "gujarat_hc_bulk": LicenceInfo(
        source="gujarat_hc_bulk",
        licence="CC-BY-4.0",
        attribution_required=True,
        redistribution_allowed=True,
        notes=(
            "Vanga indian-high-court-judgments corpus, scraped primarily "
            "from the eCourts judgments portal. Scoped here to "
            "court=24_17/bench=gujarathc."
        ),
    ),
    "india_code": LicenceInfo(
        source="india_code",
        licence="Government of India — primary legislative source",
        attribution_required=False,
        redistribution_allowed=True,
        notes=(
            "No stated redistribution restriction. Treat as the preferred "
            "primary source for statute text, not a licensed dataset."
        ),
    ),
    "official_scr_search": LicenceInfo(
        source="official_scr_search",
        licence="Government of India — official court portal",
        attribution_required=False,
        redistribution_allowed=True,
        notes="The source to verify a final judgment document against.",
    ),
    "bharat_courts": LicenceInfo(
        source="bharat_courts",
        licence="Programmatic access layer over official sources",
        attribution_required=False,
        redistribution_allowed=True,
        notes=(
            "Not a new legal authority — see docs/LEGAL_DATA_SOURCES.md §8. "
            "The underlying official court/eCourts source remains "
            "authoritative."
        ),
    ),
    "bharat_courts_archive": LicenceInfo(
        source="bharat_courts_archive",
        licence="CC-BY-4.0 (Vanga public AWS Open Data archives)",
        attribution_required=True,
        redistribution_allowed=True,
        notes=(
            "bharat-courts' ArchiveClient over the same Vanga "
            "indian-supreme-court-judgments / indian-high-court-judgments "
            "public archives as supreme_court_bulk / gujarat_hc_bulk, but "
            "queried per-lookup instead of bulk-downloaded — covers any "
            "state High Court, not just Gujarat."
        ),
    ),
    "indian_kanoon": LicenceInfo(
        source="indian_kanoon",
        licence="Public case-law aggregator — not an official government source",
        attribution_required=True,
        redistribution_allowed=True,
        notes=(
            "Fallback only, used when a judgment isn't in the Bharat "
            "Courts archive (e.g. the 2026 coverage gap). Must be labeled "
            "as a secondary aggregator in provenance, not treated as "
            "primary — matches how judgment:sc-2026-ca-6936-2023 was "
            "already labeled."
        ),
    ),
}


def get_licence(source: str) -> LicenceInfo:
    if source not in KNOWN_LICENCES:
        raise KeyError(f"No licence info registered for source '{source}'")
    return KNOWN_LICENCES[source]
