# scripts/recon/probe_gujarat_hc_bulk.py
"""Probe: Vanga High Court bulk corpus, scoped to Gujarat HC.

Court code 24_17 / bench "gujarathc" — confirmed via court-codes.json in
https://github.com/vanga/indian-high-court-judgments. See
docs/LEGAL_DATA_SOURCES.md §7 and
docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.3.
"""

from __future__ import annotations

import io
from xml.etree import ElementTree as ET

import pyarrow.parquet as pq

from legal_ai.sources.licensing import get_licence
from scripts.recon.common import ProbeReport, now_iso, polite_get, save_sample
from scripts.recon.probe_supreme_court_bulk import check_pdf_has_text

SOURCE = "gujarat_hc_bulk"
BUCKET_URL = "https://indian-high-court-judgments.s3.ap-south-1.amazonaws.com/"
STATS_MD_URL = (
    "https://raw.githubusercontent.com/vanga/"
    "indian-high-court-judgments/main/STATS.md"
)
COURT_CODE = "24_17"
BENCH = "gujarathc"
CANDIDATE_YEARS = [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2015, 2020, 2023, 2024, 2025, 2026]

_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def metadata_key_for_year(year: int) -> str:
    return f"metadata/parquet/year={year}/court={COURT_CODE}/bench={BENCH}/metadata.parquet"


def check_bucket_reachable() -> bool:
    return polite_get(BUCKET_URL).status_code == 200


def fetch_stats_md() -> str:
    response = polite_get(STATS_MD_URL)
    return response.text if response.status_code == 200 else ""


def find_years_present(years: list[int] = CANDIDATE_YEARS) -> list[int]:
    present = []
    for year in years:
        url = f"{BUCKET_URL}{metadata_key_for_year(year)}"
        response = polite_get(url)
        if response.status_code == 200:
            present.append(year)
    return present


def fetch_sample_metadata_fields(year: int) -> list[str]:
    url = f"{BUCKET_URL}{metadata_key_for_year(year)}"
    response = polite_get(url)
    if response.status_code != 200:
        return []
    save_sample(response.content, SOURCE, f"metadata_year_{year}.parquet")
    table = pq.read_table(io.BytesIO(response.content))
    return table.column_names


def find_sample_pdf_key(year: int) -> str | None:
    url = (
        f"{BUCKET_URL}?list-type=2&prefix="
        f"data/pdf/year={year}/court={COURT_CODE}/bench={BENCH}/&max-keys=1"
    )
    response = polite_get(url)
    if response.status_code != 200:
        return None
    root = ET.fromstring(response.text)
    key_el = root.find(f"{_S3_NS}Contents/{_S3_NS}Key")
    return key_el.text if key_el is not None else None


def run() -> ProbeReport:
    notes: list[str] = []
    reachable = check_bucket_reachable()

    stats_md = fetch_stats_md()
    if not stats_md:
        notes.append("STATS.md was not reachable")

    years_present = find_years_present()
    if not years_present:
        notes.append("no candidate year had Gujarat HC metadata — check court/bench code")

    sample_fields: list[str] = []
    if years_present:
        sample_year = years_present[-1]
        sample_fields = fetch_sample_metadata_fields(sample_year)

        pdf_key = find_sample_pdf_key(sample_year)
        if pdf_key:
            pdf_response = polite_get(f"{BUCKET_URL}{pdf_key}")
            if pdf_response.status_code == 200:
                save_sample(pdf_response.content, SOURCE, pdf_key.split("/")[-1])
                if not check_pdf_has_text(pdf_response.content):
                    notes.append("sample PDF has no extractable text — may need OCR")
        else:
            notes.append(f"could not find a sample PDF key for year={sample_year}")

    licence = get_licence(SOURCE)

    return ProbeReport(
        source=SOURCE,
        reachable=reachable,
        auth_required=False,
        access_method="public_s3_https",
        sample_fields=sample_fields,
        approx_volume={
            "years_present": years_present,
            "candidate_years_checked": CANDIDATE_YEARS,
            "court_code": COURT_CODE,
            "bench": BENCH,
        },
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
