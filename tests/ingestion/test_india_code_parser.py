# tests/ingestion/test_india_code_parser.py
from legal_ai.ingestion.india_code.parser import parse_act

# Mirrors the real india code DSpace item page structure (confirmed against
# the live site during Task 12's live run — see
# docs/superpowers/plans/2026-08-15-ingestion-core-india-code-plan.md Task 12
# and CanonicalDocument provenance notes): the title lives in an element
# with id="short_title" (an <h1 class="ds-title"> never appears), and each
# section is a <div class="hideshowsection"> whose number/heading come from
# a static <a class="title"> link. The section body <p id="secpNNNN"> is
# always empty in the raw HTML — the real site fills it in client-side via
# an AJAX call to /show-data per section, which this scraper does not make.
ACT_HTML = """
<html><body>
<div class="display-item">
  <a href="/bitstream/123456789/2263/1/act.pdf">
    <p id="short_title">The Specific Relief Act, 1963</p>
  </a>
  <div class="hideshowsection" id="accordion1">
    <a class="title" href="/show-data?sectionId=5">
      <span class="label label-default">Section 5.</span>
      Recovery of specific immovable property
    </a>
    <p id="secp5"></p>
  </div>
  <div class="hideshowsection" id="accordion2">
    <a class="title" href="/show-data?sectionId=6">
      <span class="label label-default">Section 6.</span>
      Suit by person dispossessed of immovable property
    </a>
    <p id="secp6"></p>
  </div>
</div>
</body></html>
"""


def test_parse_act_extracts_title_and_full_document():
    act, sections = parse_act(ACT_HTML, "https://www.indiacode.nic.in/handle/123456789/2263")
    assert act.document_type == "act"
    assert act.title == "The Specific Relief Act, 1963"
    assert act.provenance.source.url == "https://www.indiacode.nic.in/handle/123456789/2263"


def test_parse_act_extracts_each_section():
    act, sections = parse_act(ACT_HTML, "https://www.indiacode.nic.in/handle/123456789/2263")
    assert len(sections) == 2
    titles = {s.title for s in sections}
    assert "Recovery of specific immovable property" in titles
    assert "Suit by person dispossessed of immovable property" in titles
    for section in sections:
        assert section.act_id == act.document_id
        assert section.document_type == "section"


def test_parse_act_section_body_is_empty_because_real_site_loads_it_via_ajax():
    act, sections = parse_act(ACT_HTML, "https://www.indiacode.nic.in/handle/123456789/2263")
    section_6 = next(s for s in sections if "dispossessed" in s.title)
    assert section_6.full_text == ""
