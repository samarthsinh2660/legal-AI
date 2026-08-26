"""The tool registry -- name to implementation, per PROJECT_STRUCTURE.md §6.

Agents name a tool; this decides what runs. Keeping the binding here rather
than inside an agent is the point of the boundary: an agent never knows
whether a judgment came from Postgres, the Bharat Courts archive or Indian
Kanoon, so a source can be swapped without touching agent code.

Invocation policy lives here too, because it is a property of the tool
rather than of any caller:

    FORCED_ARGS       arguments applied regardless of what a plan asked for
    DEFAULT_ARGS      defaults applied only when a plan did not specify them
"""

from __future__ import annotations

import inspect
from typing import Callable

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.tools import graph as graph_tools
from legal_ai.tools import judgments as judgment_tools
from legal_ai.tools import statutes as statute_tools

TOOLS: dict[str, Callable] = {
    "search_statutes": statute_tools.search_statutes,
    "get_statute": statute_tools.get_statute,
    "get_section": statute_tools.get_section,
    "search_judgments": judgment_tools.search_judgments,
    "get_judgment": judgment_tools.get_judgment,
    "find_citations": graph_tools.find_citations,
    "find_section_citations": graph_tools.find_section_citations,
    "find_judgment_sections": graph_tools.find_judgment_sections,
}

# Set in legal_ai.config.settings, which carries the reasoning.
SEARCH_LIMIT = DEFAULT_CONFIG.search_limit

# Judgments cost an outbound fetch each, unlike statutes which are already
# stored -- see Configuration.judgment_search_limit.
JUDGMENT_SEARCH_LIMIT = DEFAULT_CONFIG.judgment_search_limit

# Applied regardless of what a plan asked for. Interactive research must not
# block on the live archive scan: with no court given it scans the Supreme
# Court and all ~25 High Court partitions, measured at 228s for a query that
# found nothing. Fetching a judgment the corpus lacks is corpus growth and
# belongs on a background path, not in a loop a person is waiting on.
FORCED_ARGS: dict[str, dict] = {
    "search_judgments": {"live": False},
}

DEFAULT_ARGS: dict[str, dict] = {
    "search_statutes": {"limit": SEARCH_LIMIT},
    "search_judgments": {"limit": JUDGMENT_SEARCH_LIMIT},
}


def get_tool(name: str) -> Callable | None:
    """The implementation for `name`, or None if it is not registered.

    Returning None rather than raising is deliberate: an unregistered name
    reaching here means a model invented a tool, which is a step to drop,
    not an error to unwind the run with.
    """
    return TOOLS.get(name)


def resolve_args(name: str, args: dict) -> dict:
    """Arguments to actually call `name` with.

    Drops parameters the tool does not accept -- a model naming a plausible
    but wrong parameter would otherwise fail the whole step -- then applies
    defaults and finally the forced arguments, which override everything.
    """
    tool = TOOLS.get(name)
    if tool is None:
        return {}

    accepted = set(inspect.signature(tool).parameters)
    resolved = {key: value for key, value in args.items() if key in accepted}

    for key, value in DEFAULT_ARGS.get(name, {}).items():
        if key in accepted:
            resolved.setdefault(key, value)

    for key, value in FORCED_ARGS.get(name, {}).items():
        if key in accepted:
            resolved[key] = value

    return resolved
