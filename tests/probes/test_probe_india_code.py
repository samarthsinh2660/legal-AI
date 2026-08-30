# tests/probes/test_probe_india_code.py
import responses

from scripts.recon.probe_india_code import (
    BROWSE_URL,
    LISTING_URL,
    SAMPLE_SEARCH_URL,
    estimate_act_count,
    run,
)

# The landing page is a navigation menu — no count lives here.
BROWSE_HTML = """
<html><body>
Browse Central Acts List of Acts Short Title Act Number Act Year
</body></html>
"""

# The real DSpace browse-by-title listing uses this exact phrasing,
# confirmed against https://www.indiacode.nic.in/handle/123456789/1362/browse?type=shorttitle
LISTING_HTML = """
<html><body>
<div class="pagination-info">Showing items 1 to 20 of 845</div>
<a href="/handle/123456789/2263">The Specific Relief Act, 1963</a>
</body></html>
"""

SEARCH_HTML = """
<html><body>
<div class="artifact-title">Specific Relief Act, 1963</div>
</body></html>
"""


def test_estimate_act_count_parses_real_dspace_showing_items_text():
    assert estimate_act_count(LISTING_HTML) == 845


def test_estimate_act_count_handles_comma_thousands_separator():
    html = "<div>Showing items 1 to 20 of 1,450</div>"
    assert estimate_act_count(html) == 1450


@responses.activate
def test_run_reports_html_scrape_and_no_api(monkeypatch, tmp_path):
    responses.add(responses.GET, BROWSE_URL, body=BROWSE_HTML, status=200)
    responses.add(responses.GET, LISTING_URL, body=LISTING_HTML, status=200)
    responses.add(responses.GET, SAMPLE_SEARCH_URL, body=SEARCH_HTML, status=200)

    monkeypatch.chdir(tmp_path)
    report = run()

    assert report.source == "india_code"
    assert report.reachable is True
    assert report.access_method == "html_scrape"
    assert report.formats == ["html"]
    assert report.approx_volume.get("central_acts_count") == 845
    assert any("no json api" in note.lower() or "no api" in note.lower() for note in report.notes)
