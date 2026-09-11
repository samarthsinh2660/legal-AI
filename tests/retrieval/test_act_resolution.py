"""Resolving an Act as a judgment names it to the Act we hold.

Every statute link in the graph, and the section a reader's question is
matched to, goes through this one function. A wrong match writes a
CITES_SECTION edge to an Act the judgment never mentioned, and it renders
exactly like a right one -- so the cases below are the wrong matches it was
found making on real judgments, each pinned so it cannot come back.
"""

import pytest

from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import find_act_by_name


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.close()


# --- abbreviations the extractor already recognised and nothing resolved --


@pytest.mark.parametrize("written, expected", [
    ("IPC", "act:ipc-1860"),
    ("CrPC", "act:crpc-1973"),
    ("CPC", "act:2191"),
    ("Evidence Act", "act:iea-1872"),
    ("Indian Evidence Act", "act:iea-1872"),
    ("NI Act", "act:2189"),
    ("N.I. Act", "act:2189"),
    ("NDPS Act", "act:1791"),
    ("SARFAESI Act", "act:2006"),
    ("POCSO Act", "act:2079"),
    ("A&C Act", "act:1978"),
    ("IBC", "act:2154"),
])
def test_a_common_abbreviation_resolves(conn, written, expected):
    assert find_act_by_name(conn, written) == expected


# --- wrong matches the substring rule was making -------------------------


@pytest.mark.parametrize("written, wrongly_became", [
    # Income Tax Act 1961 is not held; its words appear, out of order, in
    # the Black Money Act's title.
    ("Income Tax Act", "act:2147"),
    # "state" matched inside "Estate".
    ("State Act", "act:19547"),
    # Only the Amendment and Validation Act is held, not the 1894 Act.
    ("Land Acquisition Act", "act:19244"),
    # Only the Banking and Insurance Companies special Act is held.
    ("Industrial Disputes Act", "act:1919"),
    ("Finance Act", "act:1863"),
])
def test_an_act_we_do_not_hold_is_not_forced_onto_one_we_do(conn, written, wrongly_became):
    # Unresolved is the correct outcome: the Act is not on our shelf. A match
    # to a different Act would be a citation the judgment never made.
    assert find_act_by_name(conn, written) != wrongly_became


def test_a_name_two_held_acts_share_is_refused(conn):
    # "Succession Act" is the Indian Succession Act 1925 in one judgment and
    # the Hindu Succession Act 1956 in the next. Choosing the shorter title
    # was a coin toss presented as a fact.
    assert find_act_by_name(conn, "Succession Act") is None


def test_a_full_short_title_still_resolves(conn):
    assert find_act_by_name(conn, "Hindu Succession Act") == "act:1713"
    assert find_act_by_name(conn, "Specific Relief Act") == "act:1583"
    assert find_act_by_name(conn, "Indian Penal Code") == "act:ipc-1860"


# --- the year the extractor captured and nothing used --------------------


def test_the_written_year_settles_which_act(conn):
    assert find_act_by_name(conn, "Indian Succession Act", "1925") == "act:2385"
    assert find_act_by_name(conn, "Hindu Succession Act", "1956") == "act:1713"


def test_a_year_contradicting_the_act_we_hold_is_refused(conn):
    # The Companies Act 1956 is not held; the 2013 Act is. A judgment that
    # wrote "1956" did not mean the 2013 Act, whatever the name shares.
    assert find_act_by_name(conn, "Companies Act", "1956") is None
    # The same for an abbreviation: a 1898 Code is not the 1973 one.
    assert find_act_by_name(conn, "Code of Criminal Procedure", "1898") is None


def test_one_act_stored_twice_resolves_to_the_copy_with_sections(conn):
    # act:1583 and act:2263 share the title "The Specific Relief Act, 1963";
    # the first holds 48 sections, the second one. A link to the stub is a
    # link to a section that is not there.
    assert find_act_by_name(conn, "Specific Relief Act", "1963") == "act:1583"


def test_an_empty_name_resolves_to_nothing(conn):
    assert find_act_by_name(conn, "") is None
    assert find_act_by_name(conn, "the Act") is None


def test_every_alias_points_at_an_act_we_hold(conn):
    # An alias is a hand-written id. One pointing at the wrong Act is a
    # wrong link on every judgment that uses the abbreviation -- two were
    # guessed wrong while this table was written, one at the Andhra Pradesh
    # Reorganisation Act for "Aadhaar Act".
    from legal_ai.knowledge.static.store import _ALIASES

    held = {row[0] for row in conn.execute(
        "SELECT document_id FROM documents WHERE document_type = 'act'"
    ).fetchall()}
    assert set(_ALIASES.values()) - held == set()


def test_an_act_named_inside_another_title_is_not_that_act(conn):
    # "The Goa, Daman and Diu (Extension of the Code of Civil Procedure and
    # the Arbitration Act) Regulation" contains "Arbitration Act". It is not
    # the Arbitration Act, and matching the phrase anywhere took 351
    # references there.
    assert find_act_by_name(conn, "Arbitration Act") != "act:1575"


def test_a_name_two_acts_answer_to_needs_its_year(conn):
    # The Representation of the People Act is two Acts, 1950 and 1951.
    assert find_act_by_name(conn, "Representation of People Act") is None
    assert find_act_by_name(conn, "Representation of People Act", "1951") == "act:2096"


@pytest.mark.parametrize("written, expected", [
    ("Aadhaar Act", "act:2160"),
    ("Motor Vehicle Act", "act:1798"),
    ("I&B Code", "act:2154"),
    ("Arbitration & Conciliation Act", "act:1978"),
])
def test_a_short_name_for_a_long_title_resolves(conn, written, expected):
    assert find_act_by_name(conn, written) == expected


def test_the_arbitration_act_needs_its_year(conn):
    # 1996 is the Arbitration and Conciliation Act; 1940 is a repealed Act
    # we do not hold. Without a year it could be either.
    assert find_act_by_name(conn, "Arbitration Act", "1996") == "act:1978"
    assert find_act_by_name(conn, "Arbitration Act", "1940") is None
    assert find_act_by_name(conn, "Arbitration Act") is None


@pytest.mark.parametrize("described", [
    "State Act", "Central Act", "Principal Act", "Amendment Act", "said Act",
])
def test_a_description_is_not_a_name(conn, described):
    # "The Andhra State Act, 1953" ends in "State Act", and 22 references to
    # "the State Act" -- meaning whichever State's law was in issue -- were
    # about to be linked to it.
    assert find_act_by_name(conn, described) is None
