# src/legal_ai/ingestion/india_code/scraper.py
"""India Code Central Acts listing + per-act page fetch.

Confirmed real: 845 Acts, no JSON API, "Showing items X to Y of N" on
LISTING_URL — see docs/DATA_RECON_FINDINGS.md.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from legal_ai.sources.http import polite_get

BASE_URL = "https://www.indiacode.nic.in"
LISTING_URL = f"{BASE_URL}/handle/123456789/1362/browse?type=shorttitle"

_COUNT_PATTERN = re.compile(r"showing items\s+([\d,]+)\s+to\s+([\d,]+)\s+of\s+([\d,]+)", re.IGNORECASE)


def _parse_act_links(html: str) -> list[str]:
    # Real listing-page rows link to each Act as
    # /handle/123456789/<id>?view_type=browse — not a bare /handle/.../<id>
    # (those are unrelated state-legislation nav-menu links present on every
    # page), and the pagination links themselves are also under .../browse
    # so they must be excluded by requiring the view_type=browse query.
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/handle/123456789/") and "view_type=browse" in href:
            links.append(urljoin(BASE_URL, href))
    return links


def _next_page_url(html: str) -> str | None:
    # Real "next page" control is an image link (<a class="pull-right">
    # wrapping <img src="/image/nextPage.gif">) with no link text — it is
    # simply absent from the page when there is no next page.
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True).lower() == "next":
            return urljoin(BASE_URL, a["href"])
        img = a.find("img")
        if img is not None and "nextpage" in img.get("src", "").lower():
            return urljoin(BASE_URL, a["href"])
    return None


def list_act_urls() -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    page_url: str | None = LISTING_URL

    while page_url is not None:
        response = polite_get(page_url)
        for url in _parse_act_links(response.text):
            if url not in seen:
                seen.add(url)
                urls.append(url)
        page_url = _next_page_url(response.text)

    return urls


def fetch_act_html(url: str) -> str:
    return polite_get(url).text
