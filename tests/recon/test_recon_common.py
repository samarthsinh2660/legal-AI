# tests/recon/test_recon_common.py
import json
import time
from pathlib import Path

import responses

from scripts.recon.common import (
    DEFAULT_TIMEOUT,
    MIN_DELAY_SECONDS,
    ProbeReport,
    polite_get,
    save_sample,
)


def test_probe_report_saves_and_round_trips(tmp_path):
    report = ProbeReport(
        source="test_source",
        reachable=True,
        auth_required=False,
        access_method="public_s3_https",
        sample_fields=["citation", "court"],
        approx_volume={"years": "1950-2026"},
        formats=["pdf", "parquet"],
        licence="CC-BY-4.0",
        attribution_required=True,
        notes=["looks fine"],
        checked_at="2026-08-14T00:00:00+00:00",
    )

    path = report.save(tmp_path)

    assert path == tmp_path / "test_source.json"
    restored = json.loads(path.read_text())
    assert restored["source"] == "test_source"
    assert restored["sample_fields"] == ["citation", "court"]


@responses.activate
def test_polite_get_sends_user_agent_and_respects_timeout():
    responses.add(
        responses.GET,
        "https://example.com/probe",
        body="ok",
        status=200,
    )

    response = polite_get("https://example.com/probe")

    assert response.status_code == 200
    sent_headers = responses.calls[0].request.headers
    assert "PramanaAI-Recon" in sent_headers["User-Agent"]


@responses.activate
def test_polite_get_waits_between_calls_to_same_host(monkeypatch):
    responses.add(responses.GET, "https://example.com/a", body="ok", status=200)
    responses.add(responses.GET, "https://example.com/b", body="ok", status=200)

    slept_for = []
    monkeypatch.setattr(time, "sleep", lambda seconds: slept_for.append(seconds))

    polite_get("https://example.com/a")
    polite_get("https://example.com/b")

    assert slept_for, "expected a delay before the second call to the same host"
    assert slept_for[0] <= MIN_DELAY_SECONDS


def test_save_sample_writes_bytes_under_source_directory(tmp_path):
    path = save_sample(b"hello", "test_source", "sample.pdf", base_dir=tmp_path)

    assert path == tmp_path / "test_source" / "sample.pdf"
    assert path.read_bytes() == b"hello"
