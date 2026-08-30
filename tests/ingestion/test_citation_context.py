"""The words around a citation, which is where treatment lives.

Whether a judgment followed, distinguished or overruled the case it cites is
never in the citation itself -- "(2019) 8 SCC 729" is the same string in all
three. It is in the sentence around it. The graph records that A cites B and
nothing more, so answering "is this still good law" needs that sentence
carried alongside the edge.
"""

from legal_ai.ingestion.citations import extract_citation_contexts


def test_the_sentence_around_the_citation_is_returned():
    text = (
        "The High Court erred in its approach. "
        "We respectfully overrule (2019) 8 SCC 729 on this point. "
        "The appeal is allowed."
    )
    contexts = extract_citation_contexts(text)
    assert len(contexts) == 1
    citation, context = contexts[0]
    assert citation == "(2019) 8 SCC 729"
    assert "overrule" in context


def test_context_reaches_across_the_citation_both_ways():
    text = "x" * 400 + " Following (2019) 8 SCC 729 closely, " + "y" * 400
    _citation, context = extract_citation_contexts(text)[0]
    assert "Following" in context
    assert context.startswith("x") and context.endswith("y")


def test_each_citation_gets_its_own_context():
    text = (
        "We follow (2019) 8 SCC 729 in full. "
        "We distinguish [2015] 3 S.C.R. 100 on the facts."
    )
    contexts = extract_citation_contexts(text)
    assert len(contexts) == 2
    by_citation = dict(contexts)
    assert "follow" in by_citation["(2019) 8 SCC 729"]
    assert "distinguish" in by_citation["[2015] 3 S.C.R. 100"]


def test_the_same_case_cited_twice_yields_both_contexts():
    """A judgment may consider a case early and overrule it later. Keeping
    only the first mention would miss the treatment that matters."""
    text = (
        "Counsel relied on (2019) 8 SCC 729. " + "z" * 600 +
        " For these reasons (2019) 8 SCC 729 is overruled."
    )
    contexts = [c for c in extract_citation_contexts(text)
                if c[0] == "(2019) 8 SCC 729"]
    assert len(contexts) == 2
    assert any("overruled" in c for _, c in contexts)


def test_no_citations():
    assert extract_citation_contexts("A judgment citing nothing at all.") == []


def test_empty_text():
    assert extract_citation_contexts("") == []


def test_context_is_bounded():
    text = "q" * 5000 + " (2019) 8 SCC 729 " + "r" * 5000
    _citation, context = extract_citation_contexts(text)[0]
    assert len(context) < 1200
