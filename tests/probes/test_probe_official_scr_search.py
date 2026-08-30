import responses

from scripts.recon.probe_official_scr_search import (
    SEARCH_URL,
    detect_rendering_mode,
    run,
)

SPA_HTML = '<html><body><div id="app"></div><script src="/app.js"></script></body></html>'
SERVER_RENDERED_HTML = """
<html><body>
<table id="results"><tr><td>ABC v. State</td><td>2025 INSC 100</td></tr></table>
</body></html>
"""
# Confirmed against the real page: it ships Securimage (a PHP CAPTCHA lib)
# and csrf-magic.js — this is what the live scr.sci.gov.in/scrsearch/ page
# actually serves, not a plain SPA shell.
CAPTCHA_HTML = """
<html><body>
<script src="/scrsearch/csrf-magic.js"></script>
<img src="/scrsearch/vendor/securimage/securimage_play.php?id=abc" />
</body></html>
"""


def test_detect_rendering_mode_flags_empty_spa_shell():
    assert detect_rendering_mode(SPA_HTML) == "js_spa"


def test_detect_rendering_mode_flags_populated_table():
    assert detect_rendering_mode(SERVER_RENDERED_HTML) == "server_rendered"


def test_detect_rendering_mode_flags_captcha_protection():
    assert detect_rendering_mode(CAPTCHA_HTML) == "captcha_protected"


def test_detect_rendering_mode_falls_back_to_unknown():
    assert detect_rendering_mode("<html><body>hi</body></html>") == "unknown"


@responses.activate
def test_run_reports_captcha_protection_with_actionable_note(monkeypatch, tmp_path):
    responses.add(responses.GET, SEARCH_URL, body=CAPTCHA_HTML, status=200)

    monkeypatch.chdir(tmp_path)
    report = run()

    assert report.source == "official_scr_search"
    assert report.reachable is True
    assert report.access_method == "captcha_protected"
    assert any("captcha" in note.lower() for note in report.notes)
    assert any("do not attempt to bypass" in note.lower() for note in report.notes)
