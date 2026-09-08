"""What the worker is not allowed to be.

Two properties hold this shape together, and both are the kind that decay
silently: one careless import turns the worker into a service, and one
careless fetch turns the browser into its client. Neither would fail a
functional test -- the app would keep working, and the deployment story
would quietly stop being true.

    browser  ──►  API  ──►  Postgres  ◄──  worker

The browser talks to the API and to nothing else. The worker talks to
Postgres and to the model API, and answers nobody. That is what lets a
worker live on another machine behind a NAT, and what stops a reader
holding a token from reaching the thing that spends model budget.
"""

from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]

# A server, in any of the forms this codebase could grow one.
SERVER_IMPORTS = ("fastapi", "uvicorn", "starlette", "flask", "aiohttp.web")


def _worker_sources() -> list[pathlib.Path]:
    return sorted((REPO / "src" / "worker").glob("*.py"))


def test_there_is_a_worker_to_check():
    """A glob that matches nothing would pass everything below."""
    assert len(_worker_sources()) >= 4


def test_the_worker_serves_no_http():
    """No inbound port is the whole of "it can run anywhere"."""
    offenders = [
        (path.name, line)
        for path in _worker_sources()
        for line in path.read_text().splitlines()
        if line.startswith(("import ", "from ")) or line.strip().startswith(("import ", "from "))
        if any(name in line for name in SERVER_IMPORTS)
    ]
    assert offenders == []


def test_the_worker_image_exposes_no_port():
    lines = (REPO / "Dockerfile").read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("FROM") and line.endswith("AS worker"))
    directives = [line.split()[0] for line in lines[start:] if line and not line.startswith("#")]
    assert "EXPOSE" not in directives


def test_the_browser_names_exactly_one_host():
    """Every request the frontend makes goes to one base URL.

    A second host in the client would mean a browser talking to something
    that is not the API -- which is how a job runner ends up needing a
    public port and a token of its own.
    """
    sources = list((REPO / "frontend" / "src").rglob("*.ts"))
    sources += list((REPO / "frontend" / "src").rglob("*.tsx"))
    assert sources, "no frontend sources found"

    hardcoded = [
        (str(path.relative_to(REPO)), line.strip())
        for path in sources
        if path.name != "constant.ts"
        for line in path.read_text().splitlines()
        if ("http://" in line or "https://" in line)
        and not line.lstrip().startswith(("*", "//"))
        # Namespaces and schema URLs are not requests.
        and "xmlns" not in line and "schema" not in line
    ]
    assert hardcoded == []
