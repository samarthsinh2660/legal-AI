# tests/test_recon_aggregate.py
from pathlib import Path

from scripts.recon.aggregate import load_reports, main, render_markdown
from scripts.recon.common import ProbeReport


def _sample_report(source: str, reachable: bool) -> ProbeReport:
    return ProbeReport(
        source=source,
        reachable=reachable,
        auth_required=False,
        access_method="public_s3_https",
        sample_fields=["citation"],
        approx_volume={"years": "1950-2026"},
        formats=["pdf", "parquet"],
        licence="CC-BY-4.0",
        attribution_required=True,
        notes=["all good"] if reachable else ["not reachable"],
        checked_at="2026-08-14T00:00:00+00:00",
    )


def test_load_reports_reads_all_json_files(tmp_path):
    _sample_report("supreme_court_bulk", True).save(tmp_path)
    _sample_report("india_code", False).save(tmp_path)

    reports = load_reports(tmp_path)

    assert {r.source for r in reports} == {"supreme_court_bulk", "india_code"}


def test_render_markdown_includes_summary_table_and_per_source_sections():
    reports = [_sample_report("supreme_court_bulk", True), _sample_report("india_code", False)]

    markdown = render_markdown(reports)

    assert "| Source | Reachable |" in markdown
    assert "supreme_court_bulk" in markdown
    assert "india_code" in markdown
    assert "CC-BY-4.0" in markdown


def test_main_writes_output_file(tmp_path):
    reports_dir = tmp_path / "reports"
    output_path = tmp_path / "DATA_RECON_FINDINGS.md"
    _sample_report("supreme_court_bulk", True).save(reports_dir)

    result_path = main(reports_dir=reports_dir, output_path=output_path)

    assert result_path == output_path
    assert output_path.exists()
    assert "supreme_court_bulk" in output_path.read_text()
