# scripts/recon/probe_supreme_court_bulk.py
"""Probe: Vanga Supreme Court bulk corpus (indian-supreme-court-judgments).

See docs/LEGAL_DATA_SOURCES.md §5 and
docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.3.
"""

from __future__ import annotations

import io
import json
from xml.etree import ElementTree as ET

import pyarrow.parquet as pq
import pypdf

from legal_ai.sources.licensing import get_licence
from scripts.recon.common import ProbeReport, now_iso, polite_get, save_sample

SOURCE = "supreme_court_bulk"
BUCKET_URL = "https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/"
DATASET_SIZES_CSV_URL = (
    "https://raw.githubusercontent.com/vanga/"
    "indian-supreme-court-judgments/main/dataset_sizes.csv"
)
SAMPLE_YEAR = 2023

_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def check_bucket_reachable() -> tuple[bool, str]:
    response = polite_get(BUCKET_URL)
    return response.status_code == 200, response.text


def fetch_dataset_sizes() -> str:
    response = polite_get(DATASET_SIZES_CSV_URL)
    return response.text if response.status_code == 200 else ""


def fetch_sample_metadata_fields(year: int = SAMPLE_YEAR) -> list[str]:
    url = f"{BUCKET_URL}metadata/parquet/year={year}/metadata.parquet"
    response = polite_get(url)
    if response.status_code != 200:
        return []
    save_sample(response.content, SOURCE, f"metadata_year_{year}.parquet")
    table = pq.read_table(io.BytesIO(response.content))
    return table.column_names


def find_sample_pdf_key(year: int = SAMPLE_YEAR) -> str | None:
    url = f"{BUCKET_URL}?list-type=2&prefix=data/pdf/year={year}/english/&max-keys=1"
    response = polite_get(url)
    if response.status_code != 200:
        return None
    root = ET.fromstring(response.text)
    key_el = root.find(f"{_S3_NS}Contents/{_S3_NS}Key")
    return key_el.text if key_el is not None else None


def check_pdf_has_text(pdf_bytes: bytes) -> bool:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    text = "".join(page.extract_text() or "" for page in reader.pages)
    return len(text.strip()) > 0


def run() -> ProbeReport:
    notes: list[str] = []
    reachable, _ = check_bucket_reachable()

    sizes_csv = fetch_dataset_sizes()
    approx_volume: dict = {}
    if sizes_csv:
        lines = [line for line in sizes_csv.strip().splitlines() if line]
        approx_volume = {"dataset_sizes_csv_rows": len(lines) - 1}
    else:
        notes.append("dataset_sizes.csv was not reachable; volume unknown")

    sample_fields = fetch_sample_metadata_fields()
    if not sample_fields:
        notes.append(f"could not read a sample metadata.parquet for year={SAMPLE_YEAR}")

    pdf_key = find_sample_pdf_key()
    pdf_has_text = False
    if pdf_key:
        pdf_response = polite_get(f"{BUCKET_URL}{pdf_key}")
        if pdf_response.status_code == 200:
            save_sample(pdf_response.content, SOURCE, pdf_key.split("/")[-1])
            pdf_has_text = check_pdf_has_text(pdf_response.content)
            if not pdf_has_text:
                notes.append("sample PDF has no extractable text — may need OCR")
    else:
        notes.append(f"could not find a sample PDF key for year={SAMPLE_YEAR}")

    licence = get_licence(SOURCE)

    return ProbeReport(
        source=SOURCE,
        reachable=reachable,
        auth_required=False,
        access_method="public_s3_https",
        sample_fields=sample_fields,
        approx_volume=approx_volume,
        formats=["pdf", "json", "parquet"],
        licence=licence.licence,
        attribution_required=licence.attribution_required,
        notes=notes,
        checked_at=now_iso(),
    )


if __name__ == "__main__":
    report = run()
    print(report.model_dump_json(indent=2))
    report.save()
