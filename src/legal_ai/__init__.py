"""Pramana AI -- Indian legal intelligence.

Loading `.env` here, at package import, is deliberate. Configuration is
read straight from `os.environ` at the point of use (see llm/client.py
and knowledge/static/db.py), so anything that never loaded the file ran
with no GEMINI_API_KEY -- and the agents degrade *silently* in that case,
falling back to plain retrieval rather than raising. A benchmark run that
way looks like a working agent scoring badly. Loading once, for every
entry point, is what makes a missing key look missing.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def _load_env() -> None:
    # Real environment variables must win: CI, docker-compose and a
    # one-off `GEMINI_API_KEY=... python ...` all set them deliberately,
    # and a checked-out .env must not quietly override that.
    repo_env = Path(__file__).resolve().parents[2] / ".env"
    if repo_env.is_file():
        load_dotenv(repo_env, override=False)
        return
    # Installed rather than run from the checkout: fall back to a search
    # upward from the working directory.
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found, override=False)


_load_env()
