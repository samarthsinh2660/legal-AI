# tests/probes/test_probe_supreme_court_bulk.py
import responses

from scripts.recon.probe_supreme_court_bulk import (
    BUCKET_URL,
    DATASET_SIZES_CSV_URL,
    SAMPLE_YEAR,
    check_pdf_has_text,
    run,
)

BUCKET_LISTING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult><Name>indian-supreme-court-judgments</Name>
<CommonPrefixes><Prefix>data/</Prefix></CommonPrefixes>
<CommonPrefixes><Prefix>metadata/</Prefix></CommonPrefixes>
</ListBucketResult>"""

PDF_LISTING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult>
<Contents><Key>data/pdf/year=2023/english/2023_1_INSC_1.pdf</Key><Size>102400</Size></Contents>
</ListBucketResult>"""

DATASET_SIZES_CSV = "year,file_count,total_size_gb\n2023,8131,5.35\n2024,7900,5.1\n"

# a minimal, single-page, real PDF with the word "JUDGMENT" as text
import pypdf  # noqa: E402


def _tiny_pdf_bytes(text: str) -> bytes:
    from io import BytesIO

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


@responses.activate
def test_run_reports_reachable_bucket_and_schema(monkeypatch, tmp_path):
    responses.add(responses.GET, BUCKET_URL, body=BUCKET_LISTING_XML, status=200)
    responses.add(responses.GET, DATASET_SIZES_CSV_URL, body=DATASET_SIZES_CSV, status=200)
    responses.add(
        responses.GET,
        f"{BUCKET_URL}?list-type=2&prefix=data/pdf/year={SAMPLE_YEAR}/english/&max-keys=1",
        body=PDF_LISTING_XML,
        status=200,
        match_querystring=False,
    )
    responses.add(
        responses.GET,
        f"{BUCKET_URL}data/pdf/year={SAMPLE_YEAR}/english/2023_1_INSC_1.pdf",
        body=_tiny_pdf_bytes("JUDGMENT"),
        status=200,
    )

    import pyarrow as pa
    import pyarrow.parquet as pq
    from io import BytesIO

    table = pa.table({"citation": ["2023 INSC 1"], "court": ["Supreme Court of India"]})
    buf = BytesIO()
    pq.write_table(table, buf)
    responses.add(
        responses.GET,
        f"{BUCKET_URL}metadata/parquet/year={SAMPLE_YEAR}/metadata.parquet",
        body=buf.getvalue(),
        status=200,
    )

    monkeypatch.chdir(tmp_path)
    report = run()

    assert report.source == "supreme_court_bulk"
    assert report.reachable is True
    assert report.access_method == "public_s3_https"
    assert "citation" in report.sample_fields
    assert "court" in report.sample_fields
    assert "parquet" in report.formats
    assert report.licence == "CC-BY-4.0"


def test_check_pdf_has_text_flags_empty_pdf():
    assert check_pdf_has_text(_tiny_pdf_bytes("")) is False
