import time

import pytest
import requests
import responses

from legal_ai.sources.http import MIN_DELAY_SECONDS, polite_get


@responses.activate
def test_polite_get_sends_a_real_user_agent():
    responses.add(responses.GET, "https://example.com/probe", body="ok", status=200)
    response = polite_get("https://example.com/probe")
    assert response.status_code == 200
    sent = responses.calls[0].request.headers
    assert "legal-ai" in sent["User-Agent"].lower() or "legalai" in sent["User-Agent"].lower()


@responses.activate
def test_polite_get_rate_limits_same_host(monkeypatch):
    responses.add(responses.GET, "https://example.com/a", body="ok", status=200)
    responses.add(responses.GET, "https://example.com/b", body="ok", status=200)
    slept = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
    polite_get("https://example.com/a")
    polite_get("https://example.com/b")
    assert slept
    assert slept[0] <= MIN_DELAY_SECONDS


@responses.activate
def test_polite_get_retries_transient_network_errors_and_then_succeeds(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    responses.add(
        responses.GET,
        "https://example.com/flaky",
        body=requests.exceptions.ConnectionError("SSL handshake timed out"),
    )
    responses.add(
        responses.GET,
        "https://example.com/flaky",
        body=requests.exceptions.ConnectionError("SSL handshake timed out"),
    )
    responses.add(responses.GET, "https://example.com/flaky", body="ok", status=200)

    response = polite_get("https://example.com/flaky", max_retries=3)

    assert response.status_code == 200
    assert len(responses.calls) == 3


@responses.activate
def test_polite_get_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    responses.add(
        responses.GET,
        "https://example.com/always-down",
        body=requests.exceptions.ConnectionError("SSL handshake timed out"),
    )

    with pytest.raises(requests.exceptions.RequestException):
        polite_get("https://example.com/always-down", max_retries=1)

    assert len(responses.calls) == 2  # initial attempt + 1 retry
