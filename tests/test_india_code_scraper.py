import responses

from legal_ai.ingestion.india_code.scraper import LISTING_URL, list_act_urls

# Mirrors the real india code DSpace browse-listing page structure
# (confirmed against the live site during Task 12's live run): each Act row
# links to /handle/123456789/<id>?view_type=browse (not a bare
# /handle/.../<id> — those are unrelated state-legislation nav-menu links
# present on every page), and "next page" is an image link with no text
# (<a class="pull-right"><img src="/image/nextPage.gif"/></a>) that is
# simply absent once there is no next page.
PAGE_1_HTML = """
<html><body>
<a href="/handle/123456789/2454/">Andaman and Nicobar Islands</a>
<div class="panel-heading1 text-center">Showing items 1 to 2 of 3</div>
<a href="/handle/123456789/2263?view_type=browse">The Specific Relief Act, 1963</a>
<a href="/handle/123456789/9999?view_type=browse">The Limitation Act, 1963</a>
<a class="pull-right" href="/handle/123456789/1362/browse?type=shorttitle&amp;offset=2"><img src="/image/nextPage.gif"/></a>
</body></html>
"""

PAGE_2_HTML = """
<html><body>
<div class="panel-heading1 text-center">Showing items 3 to 3 of 3</div>
<a href="/handle/123456789/8888?view_type=browse">The Indian Contract Act, 1872</a>
</body></html>
"""


@responses.activate
def test_list_act_urls_paginates_until_all_acts_found():
    listing_base_url = LISTING_URL.split("?", 1)[0]
    responses.add(responses.GET, LISTING_URL, body=PAGE_1_HTML, status=200)
    responses.add(
        responses.GET,
        listing_base_url,
        body=PAGE_2_HTML,
        status=200,
        match=[responses.matchers.query_param_matcher({"type": "shorttitle", "offset": "2"})],
    )

    urls = list_act_urls()

    assert "https://www.indiacode.nic.in/handle/123456789/2263?view_type=browse" in urls
    assert "https://www.indiacode.nic.in/handle/123456789/9999?view_type=browse" in urls
    assert "https://www.indiacode.nic.in/handle/123456789/8888?view_type=browse" in urls
    assert len(urls) == 3
