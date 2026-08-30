# tests/probes/test_probe_gujarat_hc_bulk.py
import responses

from scripts.recon.probe_gujarat_hc_bulk import (
    BUCKET_URL,
    BENCH,
    COURT_CODE,
    CANDIDATE_YEARS,
    STATS_MD_URL,
    metadata_key_for_year,
    run,
)


@responses.activate
def test_run_reports_years_present_for_gujarat(monkeypatch, tmp_path):
    responses.add(responses.GET, BUCKET_URL, body="<ListBucketResult/>", status=200)
    responses.add(responses.GET, STATS_MD_URL, body="Gujarat High Court | 24_17 | ...", status=200)

    import pyarrow as pa
    import pyarrow.parquet as pq
    from io import BytesIO

    table = pa.table({"citation": ["2023 GLR 1"], "court": ["High Court of Gujarat"]})
    buf = BytesIO()
    pq.write_table(table, buf)
    parquet_bytes = buf.getvalue()

    present_years = {2023, 2024}
    for year in CANDIDATE_YEARS:
        url = f"{BUCKET_URL}{metadata_key_for_year(year)}"
        if year in present_years:
            responses.add(responses.GET, url, body=parquet_bytes, status=200)
        else:
            responses.add(responses.GET, url, status=404)

    responses.add(
        responses.GET,
        f"{BUCKET_URL}?list-type=2&prefix=data/pdf/year=2023/court={COURT_CODE}/bench={BENCH}/&max-keys=1",
        body="<ListBucketResult/>",
        status=200,
        match_querystring=False,
    )

    monkeypatch.chdir(tmp_path)
    report = run()

    assert report.source == "gujarat_hc_bulk"
    assert report.approx_volume["years_present"] == [2023, 2024]
    assert "citation" in report.sample_fields
    assert report.licence == "CC-BY-4.0"
