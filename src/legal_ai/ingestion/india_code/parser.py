# src/legal_ai/ingestion/india_code/parser.py
"""Parse an India Code Act page into a CanonicalDocument Act + Sections."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.schemas.evidence import Provenance, SourceRef

_ACT_ID_PATTERN = re.compile(r"/handle/123456789/(\d+)")


def _act_document_id(source_url: str) -> str:
    match = _ACT_ID_PATTERN.search(source_url)
    handle = match.group(1) if match else source_url
    return f"act:{handle}"


def _provenance(source_url: str, document_id: str) -> Provenance:
    return Provenance(
        source=SourceRef(
            name="India Code",
            url=source_url,
            document_id=document_id,
            source_type="primary",
        ),
        retrieved_at=datetime.now(timezone.utc),
        licence="Government of India — primary legislative source",
        attribution_required=False,
    )


_SECTION_LABEL_PATTERN = re.compile(r"section\s+([\w.-]+)", re.IGNORECASE)
_SECTION_BODY_ID_PATTERN = re.compile(r"^secp\d+$")


def parse_act(html: str, source_url: str) -> tuple[CanonicalDocument, list[CanonicalDocument]]:
    soup = BeautifulSoup(html, "html.parser")
    act_id = _act_document_id(source_url)

    # Real India Code pages have no <h1 class="ds-title"> — the title is the
    # first <... id="short_title"> element in the display-item header. (The
    # Hindi title reuses the same id further down, so `find` — which returns
    # the first match — is what we want here.)
    title_el = soup.find(id="short_title")
    title = title_el.get_text(strip=True) if title_el else "Untitled Act"

    full_text = soup.get_text(" ", strip=True)
    act = CanonicalDocument(
        document_id=act_id,
        document_type="act",
        title=title,
        full_text=full_text,
        content_hash=content_hash(full_text),
        provenance=_provenance(source_url, act_id),
        ingested_at=datetime.now(timezone.utc),
    )

    # Real India Code pages have no <div class="act-section"> — each section
    # is a <div class="hideshowsection"> whose number/heading are in a
    # static <a class="title"> link, but whose body <p id="secpNNNN"> is
    # populated client-side via AJAX (a GET to /show-data per section) and
    # is therefore empty in the HTML this scraper fetches.
    sections: list[CanonicalDocument] = []
    for section_el in soup.find_all("div", class_="hideshowsection"):
        title_link = section_el.find("a", class_="title")
        if title_link is None:
            continue
        label_el = title_link.find("span", class_="label")
        label_text = label_el.get_text(strip=True) if label_el else ""
        match = _SECTION_LABEL_PATTERN.search(label_text)
        number = match.group(1).rstrip(".") if match else ""
        full_link_text = title_link.get_text(" ", strip=True)
        heading_text = full_link_text.replace(label_text, "", 1).strip() if label_text else full_link_text
        section_title = heading_text or (f"Section {number}" if number else "Untitled section")
        body_el = section_el.find("p", id=_SECTION_BODY_ID_PATTERN)
        body = body_el.get_text(strip=True) if body_el else ""
        section_id = f"{act_id}:sec-{number}"
        sections.append(
            CanonicalDocument(
                document_id=section_id,
                document_type="section",
                title=section_title,
                act_id=act_id,
                full_text=body,
                content_hash=content_hash(body),
                provenance=_provenance(source_url, section_id),
                ingested_at=datetime.now(timezone.utc),
            )
        )

    return act, sections
