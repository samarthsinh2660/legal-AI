"""Ingest India Code's 14 "Spent Acts" — a separate listing category from
the main Central Acts list this project originally scraped (see
docs/superpowers/specs/2026-08-15-section-body-fetch-design.md and the
2026-08-17 web-search cross-check: 846 Acts + 14 Spent Acts = 860 total
central acts currently in force, and our corpus had exactly 846 — this
script closes that gap).

Spent Acts have no /handle/ DSpace page and no AJAX section structure
like regular Central Acts — India Code only exposes a title + a direct
PDF link for each. So the whole Act (title + every Section) is extracted
from the PDF via Gemini in one pass, the same verbatim-extraction
discipline as complete_missing_sections_from_pdf.py: copy, don't
paraphrase or invent, null if genuinely not found.

Run: .venv/bin/python -m scripts.section_collection.ingest_spent_acts
"""

from __future__ import annotations

import io
import json
import os
import re
import time
from datetime import datetime, timezone

import pypdf
from google import genai

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.chunk_store import chunk_and_store
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef
from legal_ai.sources.http import polite_get

SPENT_ACT_LISTING_URL = "https://www.indiacode.nic.in/spent-act/spent-act.jsp"
MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-3-flash-preview"]


def list_spent_acts() -> list[tuple[str, str]]:
    """Returns [(title, pdf_url), ...] for all 14 real rows on the page."""
    from bs4 import BeautifulSoup

    html = polite_get(SPENT_ACT_LISTING_URL).text
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="repealedactid")
    rows = table.find("tbody").find_all("tr")
    results = []
    for row in rows:
        cells = row.find_all("td")
        title = cells[1].get_text(strip=True)
        link = cells[3].find("a")
        if link and link.get("href"):
            results.append((title, "https://www.indiacode.nic.in" + link["href"]))
    return results


def extract_pdf_text(pdf_url: str) -> str:
    response = polite_get(pdf_url)
    reader = pypdf.PdfReader(io.BytesIO(response.content))
    return "\n".join(page.extract_text() for page in reader.pages)


def ask_gemini_for_all_sections(client: genai.Client, act_title: str, pdf_text: str) -> list[dict]:
    prompt = f"""You are extracting structure from an official Indian legal Act PDF — {act_title}.

Read this Act's real body text (skip the "ARRANGEMENT OF SECTIONS" table
of contents at the start — use it only to know which numbers exist, not
as the source of body text) and return every real Section it contains.

For each Section, copy its number, its heading/title, and its verbatim
body text exactly as written — do not summarize, paraphrase, correct, or
invent anything. Exclude the number and heading from the body text itself
(they go in separate fields).

Return ONLY valid JSON, no markdown fences, no commentary:
[{{"number": "1", "title": "Short title...", "body": "verbatim body text"}}, ...]

PDF TEXT:
{pdf_text}
"""
    last_error: Exception | None = None
    for model in MODELS:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(model=model, contents=prompt)
                text = resp.text.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\n|\n```$", "", text)
                return json.loads(text)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
                    time.sleep(65)
                elif attempt == 0:
                    time.sleep(5)
    raise last_error if last_error is not None else RuntimeError("no models configured")


def _act_id_from_pdf_url(pdf_url: str) -> str:
    # e.g. ".../SpentActFileOpenServlet?sfilename=A2021-25.pdf" -> "act:spent-2021-25"
    match = re.search(r"sfilename=A(\d+)-(\d+)\.pdf", pdf_url)
    if match:
        return f"act:spent-{match.group(1)}-{match.group(2)}"
    return f"act:spent-{content_hash(pdf_url)[:12]}"


def _provenance(pdf_url: str, document_id: str) -> Provenance:
    return Provenance(
        source=SourceRef(
            name="India Code (Spent Acts, PDF, AI-assisted extraction)",
            url=pdf_url,
            document_id=document_id,
            source_type="primary",
        ),
        retrieved_at=datetime.now(timezone.utc),
        licence="Government of India — primary legislative source",
        attribution_required=False,
    )


def run() -> None:
    api_key = os.environ["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
    conn = get_connection()
    driver = get_driver()

    acts = list_spent_acts()
    print(f"Found {len(acts)} Spent Acts", flush=True)

    total_acts_stored = 0
    total_sections_stored = 0
    for title, pdf_url in acts:
        act_id = _act_id_from_pdf_url(pdf_url)
        pdf_text = extract_pdf_text(pdf_url)

        try:
            sections_raw = ask_gemini_for_all_sections(client, title, pdf_text)
        except Exception as exc:  # noqa: BLE001
            print(f"{act_id} ({title}): FAILED — {exc!r}", flush=True)
            continue

        act_doc = CanonicalDocument(
            document_id=act_id,
            document_type="act",
            title=title,
            full_text=pdf_text,
            content_hash=content_hash(pdf_text),
            provenance=_provenance(pdf_url, act_id),
            ingested_at=datetime.now(timezone.utc),
        )
        vector = embed(act_doc.full_text)
        upsert_document(conn, act_doc, embedding=vector)
        total_acts_stored += 1

        filled = 0
        for entry in sections_raw:
            number = str(entry.get("number") or "").strip()
            body = entry.get("body")
            if not number or not isinstance(body, str) or len(body.strip()) < 5:
                continue
            section_id = f"{act_id}:sec-{number}"
            section_doc = CanonicalDocument(
                document_id=section_id,
                document_type="section",
                title=str(entry.get("title") or f"Section {number}"),
                act_id=act_id,
                full_text=body.strip(),
                content_hash=content_hash(body.strip()),
                provenance=_provenance(pdf_url, section_id),
                ingested_at=datetime.now(timezone.utc),
            )
            section_vector = embed(section_doc.full_text)
            upsert_document(conn, section_doc, embedding=section_vector)
            chunk_and_store(conn, section_doc.document_id, section_doc.full_text, section_doc.document_type)
            write_act_section(driver, act_doc, section_doc)
            filled += 1

        total_sections_stored += filled
        print(f"{act_id} ({title}): {filled} sections stored", flush=True)

    print(f"\nDONE. Acts stored: {total_acts_stored}  Sections stored: {total_sections_stored}", flush=True)
    conn.close()


if __name__ == "__main__":
    run()
