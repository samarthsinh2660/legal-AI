"""Fetch real India Code Section body text via the site's AJAX endpoint.

India Code loads a Section's body text client-side: the Act page only
ships each Section's number/title, and the real text comes from a
separate call to /SectionPageContent. See
docs/superpowers/specs/2026-08-15-section-body-fetch-design.md for the
discovery process and design.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from legal_ai.sources.http import polite_get

SECTION_CONTENT_URL = "https://www.indiacode.nic.in/SectionPageContent"


def extract_section_ajax_ids(html: str) -> dict[str, tuple[str, str]]:
    """Map a section's number (e.g. '6') -> (actid, sectionId).

    Uses the anchor's `id` attribute ("{actid}#{sectionId}#{orgactid}"),
    not its href: real pages ship the href with a raw, un-escaped
    "&sectionId=", which any HTML parser decodes as the legacy entity
    "&sect" -> "§" before we see it, corrupting the query string.
    """
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, tuple[str, str]] = {}
    for section_el in soup.find_all("div", class_="hideshowsection"):
        title_link = section_el.find("a", class_="title")
        if title_link is None or not title_link.get("id"):
            continue
        label_el = title_link.find("span", class_="label")
        label_text = label_el.get_text(strip=True) if label_el else ""
        match = re.search(r"section\s+([\w.-]+)", label_text, re.IGNORECASE)
        number = match.group(1).rstrip(".") if match else ""
        if not number:
            continue
        parts = title_link["id"].split("#")
        if len(parts) >= 2 and parts[0] and parts[1]:
            result[number] = (parts[0], parts[1])
    return result


def fetch_section_text(actid: str, section_id: str) -> str:
    """Fetch and plain-text a Section's real body via SectionPageContent."""
    response = polite_get(
        SECTION_CONTENT_URL,
        params={"actid": actid, "sectionID": section_id},
    )
    payload = response.json()
    content_text = BeautifulSoup(payload.get("content", ""), "html.parser").get_text(" ", strip=True)
    footnote_text = BeautifulSoup(payload.get("footnote", ""), "html.parser").get_text(" ", strip=True)
    return f"{content_text}\n\n{footnote_text}".strip() if footnote_text else content_text
