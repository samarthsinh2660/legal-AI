# Phase 1 Data-Layer Recon — Implementation Plan

**Status:** Complete. All 11 tasks executed, 22/22 tests passing, all five
probes run against live sources. Results: `docs/DATA_RECON_FINDINGS.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine, with evidence, whether India Code, the Supreme Court, and
Gujarat High Court are reachable, in a usable structure, with reliable
provenance and licensing — before writing any ingestion pipeline.

**Architecture:** A minimal `src/legal_ai/` scaffold hosts two shared pieces
(a `Evidence`/`Provenance` schema and a per-source licence registry) that the
real ingestion code will reuse later. Five standalone probe scripts under
`scripts/recon/` each hit one source, write a structured `ProbeReport` JSON
file, and never download more than one or two sample objects. An aggregator
renders all reports into `docs/DATA_RECON_FINDINGS.md`.

**Tech Stack:** Python 3.11+, `pydantic` (schemas/reports), `requests` (HTTP),
`pyarrow` (reading sampled Parquet), `pypdf` (checking a sampled PDF has real
text), `pytest` + `responses` (HTTP-mocked tests).

## Global Constraints

- Python `>=3.11` (matches `langgraph.json` in `docs/PROJECT_STRUCTURE.md`).
- No bulk downloads — every probe samples at most one or two objects per
  source (per `docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md`
  §2 scope and §5 error handling).
- All outbound HTTP goes through `polite_get()` — a real `User-Agent` and a
  minimum 1-second delay per host, per the spec's politeness requirement
  (Vanga's READMEs explicitly ask against high-concurrency scraping).
- `data/` is gitignored; nothing under it is ever committed.
- **Do not run `git add` / `git commit` at any step below.** The user commits
  manually. Every task ends with tests passing and files saved — stop there.
- Every probe script prints its `ProbeReport` as JSON to stdout AND writes it
  to `data/recon/reports/<source>.json`.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/legal_ai/__init__.py`
- Create: `src/legal_ai/schemas/__init__.py`
- Create: `src/legal_ai/sources/__init__.py`
- Create: `scripts/__init__.py`
- Create: `scripts/recon/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: an installable `legal_ai` package (editable install via
  `pip install -e ".[dev]"`), and `scripts/recon` importable as
  `scripts.recon.*` from the repo root.

- [x] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "legal-ai"
version = "0.0.1"
description = "Pramana AI — Indian Legal Intelligence data layer and recon tooling"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.7",
    "requests>=2.32",
    "pyarrow>=17.0",
    "pypdf>=4.3",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "responses>=0.25",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [x] **Step 2: Write `.env.example`**

```bash
# No credentials are required for the recon phase — every probed source
# (India Code, the Vanga S3 buckets, the SC/HC official portals) is public.
# This file exists so later phases (LangSmith, model providers, DB URLs)
# have a place to land without a schema change.
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=legal-ai
```

- [x] **Step 3: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
venv/
*.egg-info/
.pytest_cache/
data/
.env
```

- [x] **Step 4: Create empty package/init files**

```bash
mkdir -p src/legal_ai/schemas src/legal_ai/sources scripts/recon tests
touch src/legal_ai/__init__.py
touch src/legal_ai/schemas/__init__.py
touch src/legal_ai/sources/__init__.py
touch scripts/__init__.py
touch scripts/recon/__init__.py
touch tests/__init__.py
```

- [x] **Step 5: Install the package editable, with dev extras**

Run: `pip install -e ".[dev]"`
Expected: installs cleanly; `python -c "import legal_ai"` succeeds with no
output (no error).

---

### Task 2: `Evidence` / `Provenance` schema

**Files:**
- Create: `src/legal_ai/schemas/evidence.py`
- Test: `tests/test_evidence.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces: `SourceRef`, `Location`, `Provenance`, `Evidence` — pydantic
  `BaseModel` classes. Later tasks import
  `from legal_ai.schemas.evidence import SourceRef, Provenance, Evidence, Location`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_evidence.py
from datetime import datetime, timezone

from legal_ai.schemas.evidence import Evidence, Location, Provenance, SourceRef


def test_evidence_round_trips_through_json():
    source = SourceRef(
        name="Supreme Court of India",
        url="https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/",
        document_id="2023_1_INSC_1",
        source_type="primary",
    )
    provenance = Provenance(
        source=source,
        retrieved_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        licence="CC-BY-4.0",
        attribution_required=True,
    )
    evidence = Evidence(
        content="...a person in possession cannot be ousted...",
        provenance=provenance,
        location=Location(page=12, paragraph=42),
    )

    restored = Evidence.model_validate_json(evidence.model_dump_json())

    assert restored.provenance.source.name == "Supreme Court of India"
    assert restored.provenance.source.source_type == "primary"
    assert restored.location.paragraph == 42
    assert restored.provenance.attribution_required is True


def test_source_type_rejects_unknown_value():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SourceRef(
            name="x",
            url="https://example.com",
            source_type="not_a_real_type",
        )
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_evidence.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.schemas.evidence'`

- [x] **Step 3: Write the implementation**

```python
# src/legal_ai/schemas/evidence.py
"""Provenance-carrying evidence, per docs/LEGAL_DATA_SOURCES.md §28."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

SourceType = Literal["primary", "programmatic", "research"]


class SourceRef(BaseModel):
    name: str
    url: str
    document_id: Optional[str] = None
    source_type: SourceType


class Location(BaseModel):
    page: Optional[int] = None
    paragraph: Optional[int] = None


class Provenance(BaseModel):
    source: SourceRef
    retrieved_at: datetime
    licence: str
    attribution_required: bool


class Evidence(BaseModel):
    content: str
    provenance: Provenance
    location: Optional[Location] = None
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_evidence.py -v`
Expected: 2 passed

---

### Task 3: Per-source licence registry

**Files:**
- Create: `src/legal_ai/sources/licensing.py`
- Test: `tests/test_licensing.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `LicenceInfo` (pydantic model), `get_licence(source: str) -> LicenceInfo`,
  and the five registered keys: `"supreme_court_bulk"`, `"gujarat_hc_bulk"`,
  `"india_code"`, `"official_scr_search"`, `"bharat_courts"`. Every probe
  script in Tasks 5–9 calls `get_licence(SOURCE)` to fill its report's
  `licence` / `attribution_required` fields — this is the single place that
  licence claim lives.

- [x] **Step 1: Write the failing test**

```python
# tests/test_licensing.py
import pytest

from legal_ai.sources.licensing import KNOWN_LICENCES, get_licence


def test_get_licence_returns_known_source():
    info = get_licence("supreme_court_bulk")
    assert info.licence == "CC-BY-4.0"
    assert info.attribution_required is True


def test_get_licence_raises_on_unknown_source():
    with pytest.raises(KeyError):
        get_licence("not_a_real_source")


def test_all_five_phase1_sources_are_registered():
    expected = {
        "supreme_court_bulk",
        "gujarat_hc_bulk",
        "india_code",
        "official_scr_search",
        "bharat_courts",
    }
    assert expected.issubset(KNOWN_LICENCES.keys())
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_licensing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.sources.licensing'`

- [x] **Step 3: Write the implementation**

```python
# src/legal_ai/sources/licensing.py
"""Known licence/attribution facts per data source.

Single source of truth for licensing claims — probes and, later, ingestion
adapters read from here rather than re-stating terms inline. See
docs/LEGAL_DATA_SOURCES.md §2 (source-of-truth hierarchy) and the
per-source sections it links.
"""

from __future__ import annotations

from pydantic import BaseModel


class LicenceInfo(BaseModel):
    source: str
    licence: str
    attribution_required: bool
    redistribution_allowed: bool
    notes: str


KNOWN_LICENCES: dict[str, LicenceInfo] = {
    "supreme_court_bulk": LicenceInfo(
        source="supreme_court_bulk",
        licence="CC-BY-4.0",
        attribution_required=True,
        redistribution_allowed=True,
        notes=(
            "Vanga indian-supreme-court-judgments corpus, storage sponsored "
            "by AWS Open Data. Bulk engineering source; the official SC "
            "portal remains the authority for the final document."
        ),
    ),
    "gujarat_hc_bulk": LicenceInfo(
        source="gujarat_hc_bulk",
        licence="CC-BY-4.0",
        attribution_required=True,
        redistribution_allowed=True,
        notes=(
            "Vanga indian-high-court-judgments corpus, scraped primarily "
            "from the eCourts judgments portal. Scoped here to "
            "court=24_17/bench=gujarathc."
        ),
    ),
    "india_code": LicenceInfo(
        source="india_code",
        licence="Government of India — primary legislative source",
        attribution_required=False,
        redistribution_allowed=True,
        notes=(
            "No stated redistribution restriction. Treat as the preferred "
            "primary source for statute text, not a licensed dataset."
        ),
    ),
    "official_scr_search": LicenceInfo(
        source="official_scr_search",
        licence="Government of India — official court portal",
        attribution_required=False,
        redistribution_allowed=True,
        notes="The source to verify a final judgment document against.",
    ),
    "bharat_courts": LicenceInfo(
        source="bharat_courts",
        licence="Programmatic access layer over official sources",
        attribution_required=False,
        redistribution_allowed=True,
        notes=(
            "Not a new legal authority — see docs/LEGAL_DATA_SOURCES.md §8. "
            "The underlying official court/eCourts source remains "
            "authoritative."
        ),
    ),
}


def get_licence(source: str) -> LicenceInfo:
    if source not in KNOWN_LICENCES:
        raise KeyError(f"No licence info registered for source '{source}'")
    return KNOWN_LICENCES[source]
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_licensing.py -v`
Expected: 3 passed

---

### Task 4: Shared probe infrastructure (`common.py`)

**Files:**
- Create: `scripts/recon/common.py`
- Test: `tests/test_recon_common.py`

**Interfaces:**
- Consumes: nothing from earlier tasks directly (licence values are passed
  in by callers, not looked up here).
- Produces: `ProbeReport` (pydantic model with `.save(directory) -> Path`),
  `polite_get(url, timeout=DEFAULT_TIMEOUT, headers=None, **kwargs) ->
  requests.Response`, `save_sample(content: bytes, source: str, filename:
  str, base_dir: Path = SAMPLES_DIR) -> Path`, `now_iso() -> str`,
  `REPORTS_DIR: Path`, `SAMPLES_DIR: Path`, `USER_AGENT: str`,
  `DEFAULT_TIMEOUT: int`, `MIN_DELAY_SECONDS: float`. Every probe script in
  Tasks 5–9 imports all of these.

- [x] **Step 1: Write the failing tests**

```python
# tests/test_recon_common.py
import json
import time
from pathlib import Path

import responses

from scripts.recon.common import (
    DEFAULT_TIMEOUT,
    MIN_DELAY_SECONDS,
    ProbeReport,
    polite_get,
    save_sample,
)


def test_probe_report_saves_and_round_trips(tmp_path):
    report = ProbeReport(
        source="test_source",
        reachable=True,
        auth_required=False,
        access_method="public_s3_https",
        sample_fields=["citation", "court"],
        approx_volume={"years": "1950-2026"},
        formats=["pdf", "parquet"],
        licence="CC-BY-4.0",
        attribution_required=True,
        notes=["looks fine"],
        checked_at="2026-08-14T00:00:00+00:00",
    )

    path = report.save(tmp_path)

    assert path == tmp_path / "test_source.json"
    restored = json.loads(path.read_text())
    assert restored["source"] == "test_source"
    assert restored["sample_fields"] == ["citation", "court"]


@responses.activate
def test_polite_get_sends_user_agent_and_respects_timeout():
    responses.add(
        responses.GET,
        "https://example.com/probe",
        body="ok",
        status=200,
    )

    response = polite_get("https://example.com/probe")

    assert response.status_code == 200
    sent_headers = responses.calls[0].request.headers
    assert "PramanaAI-Recon" in sent_headers["User-Agent"]


@responses.activate
def test_polite_get_waits_between_calls_to_same_host(monkeypatch):
    responses.add(responses.GET, "https://example.com/a", body="ok", status=200)
    responses.add(responses.GET, "https://example.com/b", body="ok", status=200)

    slept_for = []
    monkeypatch.setattr(time, "sleep", lambda seconds: slept_for.append(seconds))

    polite_get("https://example.com/a")
    polite_get("https://example.com/b")

    assert slept_for, "expected a delay before the second call to the same host"
    assert slept_for[0] <= MIN_DELAY_SECONDS


def test_save_sample_writes_bytes_under_source_directory(tmp_path):
    path = save_sample(b"hello", "test_source", "sample.pdf", base_dir=tmp_path)

    assert path == tmp_path / "test_source" / "sample.pdf"
    assert path.read_bytes() == b"hello"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_recon_common.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.recon.common'`
(and `responses` must already be installed from Task 1's dev extras)

- [x] **Step 3: Write the implementation**

```python
# scripts/recon/common.py
"""Shared infrastructure for the Phase 1 data-source probe scripts.

See docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.2.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from pydantic import BaseModel

USER_AGENT = (
    "PramanaAI-Recon/0.1 (Indian Legal Intelligence data recon; "
    "low-volume, non-commercial research probe)"
)
DEFAULT_TIMEOUT = 12
MIN_DELAY_SECONDS = 1.0

REPORTS_DIR = Path("data/recon/reports")
SAMPLES_DIR = Path("data/recon/samples")

_last_request_at: dict[str, float] = {}


class ProbeReport(BaseModel):
    source: str
    reachable: bool
    auth_required: bool
    access_method: str
    sample_fields: list[str] = []
    approx_volume: dict[str, Any] = {}
    formats: list[str] = []
    licence: str
    attribution_required: bool
    notes: list[str] = []
    checked_at: str

    def save(self, directory: Path = REPORTS_DIR) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.source}.json"
        path.write_text(self.model_dump_json(indent=2))
        return path


def polite_get(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
    **kwargs: Any,
) -> requests.Response:
    """A `requests.get` that identifies itself and rate-limits per host."""
    host = urlparse(url).netloc
    now = time.monotonic()
    last = _last_request_at.get(host)
    if last is not None:
        elapsed = now - last
        if elapsed < MIN_DELAY_SECONDS:
            time.sleep(MIN_DELAY_SECONDS - elapsed)

    merged_headers = {"User-Agent": USER_AGENT}
    if headers:
        merged_headers.update(headers)

    response = requests.get(url, timeout=timeout, headers=merged_headers, **kwargs)
    _last_request_at[urlparse(url).netloc] = time.monotonic()
    return response


def save_sample(
    content: bytes,
    source: str,
    filename: str,
    base_dir: Path = SAMPLES_DIR,
) -> Path:
    directory = base_dir / source
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(content)
    return path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_recon_common.py -v`
Expected: 4 passed

---

### Task 5: Probe — Supreme Court bulk corpus (Vanga)

**Files:**
- Create: `scripts/recon/probe_supreme_court_bulk.py`
- Test: `tests/test_probe_supreme_court_bulk.py`

**Interfaces:**
- Consumes: `ProbeReport`, `polite_get`, `save_sample`, `now_iso`, `REPORTS_DIR`
  from `scripts.recon.common` (Task 4); `get_licence` from
  `legal_ai.sources.licensing` (Task 3).
- Produces: `run() -> ProbeReport` with `source="supreme_court_bulk"`. Also
  runnable as `python -m scripts.recon.probe_supreme_court_bulk`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_probe_supreme_court_bulk.py
import responses

from scripts.recon.probe_supreme_court_bulk import (
    BUCKET_URL,
    DATASET_SIZES_CSV_URL,
    SAMPLE_YEAR,
    check_pdf_has_text,
    run,
)

BUCKET_LISTING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult><Name>indian-supreme-court-judgments</Name>
<CommonPrefixes><Prefix>data/</Prefix></CommonPrefixes>
<CommonPrefixes><Prefix>metadata/</Prefix></CommonPrefixes>
</ListBucketResult>"""

PDF_LISTING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult>
<Contents><Key>data/pdf/year=2023/english/2023_1_INSC_1.pdf</Key><Size>102400</Size></Contents>
</ListBucketResult>"""

DATASET_SIZES_CSV = "year,file_count,total_size_gb\n2023,8131,5.35\n2024,7900,5.1\n"

# a minimal, single-page, real PDF with the word "JUDGMENT" as text
import pypdf  # noqa: E402


def _tiny_pdf_bytes(text: str) -> bytes:
    from io import BytesIO

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


@responses.activate
def test_run_reports_reachable_bucket_and_schema(monkeypatch, tmp_path):
    responses.add(responses.GET, BUCKET_URL, body=BUCKET_LISTING_XML, status=200)
    responses.add(responses.GET, DATASET_SIZES_CSV_URL, body=DATASET_SIZES_CSV, status=200)
    responses.add(
        responses.GET,
        f"{BUCKET_URL}?list-type=2&prefix=data/pdf/year={SAMPLE_YEAR}/english/&max-keys=1",
        body=PDF_LISTING_XML,
        status=200,
        match_querystring=False,
    )
    responses.add(
        responses.GET,
        f"{BUCKET_URL}data/pdf/year={SAMPLE_YEAR}/english/2023_1_INSC_1.pdf",
        body=_tiny_pdf_bytes("JUDGMENT"),
        status=200,
    )

    import pyarrow as pa
    import pyarrow.parquet as pq
    from io import BytesIO

    table = pa.table({"citation": ["2023 INSC 1"], "court": ["Supreme Court of India"]})
    buf = BytesIO()
    pq.write_table(table, buf)
    responses.add(
        responses.GET,
        f"{BUCKET_URL}metadata/parquet/year={SAMPLE_YEAR}/metadata.parquet",
        body=buf.getvalue(),
        status=200,
    )

    monkeypatch.chdir(tmp_path)
    report = run()

    assert report.source == "supreme_court_bulk"
    assert report.reachable is True
    assert report.access_method == "public_s3_https"
    assert "citation" in report.sample_fields
    assert "court" in report.sample_fields
    assert "parquet" in report.formats
    assert report.licence == "CC-BY-4.0"


def test_check_pdf_has_text_flags_empty_pdf():
    assert check_pdf_has_text(_tiny_pdf_bytes("")) is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_probe_supreme_court_bulk.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.recon.probe_supreme_court_bulk'`

- [x] **Step 3: Write the implementation**

```python
# scripts/recon/probe_supreme_court_bulk.py
"""Probe: Vanga Supreme Court bulk corpus (indian-supreme-court-judgments).

See docs/LEGAL_DATA_SOURCES.md §5 and
docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.3.
"""

from __future__ import annotations

import io
import json
from xml.etree import ElementTree as ET

import pyarrow.parquet as pq
import pypdf

from legal_ai.sources.licensing import get_licence
from scripts.recon.common import ProbeReport, now_iso, polite_get, save_sample

SOURCE = "supreme_court_bulk"
BUCKET_URL = "https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/"
DATASET_SIZES_CSV_URL = (
    "https://raw.githubusercontent.com/vanga/"
    "indian-supreme-court-judgments/main/dataset_sizes.csv"
)
SAMPLE_YEAR = 2023

_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def check_bucket_reachable() -> tuple[bool, str]:
    response = polite_get(BUCKET_URL)
    return response.status_code == 200, response.text


def fetch_dataset_sizes() -> str:
    response = polite_get(DATASET_SIZES_CSV_URL)
    return response.text if response.status_code == 200 else ""


def fetch_sample_metadata_fields(year: int = SAMPLE_YEAR) -> list[str]:
    url = f"{BUCKET_URL}metadata/parquet/year={year}/metadata.parquet"
    response = polite_get(url)
    if response.status_code != 200:
        return []
    save_sample(response.content, SOURCE, f"metadata_year_{year}.parquet")
    table = pq.read_table(io.BytesIO(response.content))
    return table.column_names


def find_sample_pdf_key(year: int = SAMPLE_YEAR) -> str | None:
    url = f"{BUCKET_URL}?list-type=2&prefix=data/pdf/year={year}/english/&max-keys=1"
    response = polite_get(url)
    if response.status_code != 200:
        return None
    root = ET.fromstring(response.text)
    key_el = root.find(f"{_S3_NS}Contents/{_S3_NS}Key")
    return key_el.text if key_el is not None else None


def check_pdf_has_text(pdf_bytes: bytes) -> bool:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    text = "".join(page.extract_text() or "" for page in reader.pages)
    return len(text.strip()) > 0


def run() -> ProbeReport:
    notes: list[str] = []
    reachable, _ = check_bucket_reachable()

    sizes_csv = fetch_dataset_sizes()
    approx_volume: dict = {}
    if sizes_csv:
        lines = [line for line in sizes_csv.strip().splitlines() if line]
        approx_volume = {"dataset_sizes_csv_rows": len(lines) - 1}
    else:
        notes.append("dataset_sizes.csv was not reachable; volume unknown")

    sample_fields = fetch_sample_metadata_fields()
    if not sample_fields:
        notes.append(f"could not read a sample metadata.parquet for year={SAMPLE_YEAR}")

    pdf_key = find_sample_pdf_key()
    pdf_has_text = False
    if pdf_key:
        pdf_response = polite_get(f"{BUCKET_URL}{pdf_key}")
        if pdf_response.status_code == 200:
            save_sample(pdf_response.content, SOURCE, pdf_key.split("/")[-1])
            pdf_has_text = check_pdf_has_text(pdf_response.content)
            if not pdf_has_text:
                notes.append("sample PDF has no extractable text — may need OCR")
    else:
        notes.append(f"could not find a sample PDF key for year={SAMPLE_YEAR}")

    licence = get_licence(SOURCE)

    return ProbeReport(
        source=SOURCE,
        reachable=reachable,
        auth_required=False,
        access_method="public_s3_https",
        sample_fields=sample_fields,
        approx_volume=approx_volume,
        formats=["pdf", "json", "parquet"],
        licence=licence.licence,
        attribution_required=licence.attribution_required,
        notes=notes,
        checked_at=now_iso(),
    )


if __name__ == "__main__":
    report = run()
    print(report.model_dump_json(indent=2))
    report.save()
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_probe_supreme_court_bulk.py -v`
Expected: 2 passed

---

### Task 6: Probe — Gujarat High Court bulk corpus (Vanga)

**Files:**
- Create: `scripts/recon/probe_gujarat_hc_bulk.py`
- Test: `tests/test_probe_gujarat_hc_bulk.py`

**Interfaces:**
- Consumes: same as Task 5, plus reuses `check_pdf_has_text` by importing it
  from `scripts.recon.probe_supreme_court_bulk` (no duplicated logic).
- Produces: `run() -> ProbeReport` with `source="gujarat_hc_bulk"`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_probe_gujarat_hc_bulk.py
import responses

from scripts.recon.probe_gujarat_hc_bulk import (
    BUCKET_URL,
    BENCH,
    COURT_CODE,
    CANDIDATE_YEARS,
    STATS_MD_URL,
    metadata_key_for_year,
    run,
)


@responses.activate
def test_run_reports_years_present_for_gujarat(monkeypatch, tmp_path):
    responses.add(responses.GET, BUCKET_URL, body="<ListBucketResult/>", status=200)
    responses.add(responses.GET, STATS_MD_URL, body="Gujarat High Court | 24_17 | ...", status=200)

    import pyarrow as pa
    import pyarrow.parquet as pq
    from io import BytesIO

    table = pa.table({"citation": ["2023 GLR 1"], "court": ["High Court of Gujarat"]})
    buf = BytesIO()
    pq.write_table(table, buf)
    parquet_bytes = buf.getvalue()

    present_years = {2023, 2024}
    for year in CANDIDATE_YEARS:
        url = f"{BUCKET_URL}{metadata_key_for_year(year)}"
        if year in present_years:
            responses.add(responses.GET, url, body=parquet_bytes, status=200)
        else:
            responses.add(responses.GET, url, status=404)

    responses.add(
        responses.GET,
        f"{BUCKET_URL}?list-type=2&prefix=data/pdf/year=2023/court={COURT_CODE}/bench={BENCH}/&max-keys=1",
        body="<ListBucketResult/>",
        status=200,
        match_querystring=False,
    )

    monkeypatch.chdir(tmp_path)
    report = run()

    assert report.source == "gujarat_hc_bulk"
    assert report.approx_volume["years_present"] == [2023, 2024]
    assert "citation" in report.sample_fields
    assert report.licence == "CC-BY-4.0"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_probe_gujarat_hc_bulk.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.recon.probe_gujarat_hc_bulk'`

- [x] **Step 3: Write the implementation**

```python
# scripts/recon/probe_gujarat_hc_bulk.py
"""Probe: Vanga High Court bulk corpus, scoped to Gujarat HC.

Court code 24_17 / bench "gujarathc" — confirmed via court-codes.json in
https://github.com/vanga/indian-high-court-judgments. See
docs/LEGAL_DATA_SOURCES.md §7 and
docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.3.
"""

from __future__ import annotations

import io
from xml.etree import ElementTree as ET

import pyarrow.parquet as pq

from legal_ai.sources.licensing import get_licence
from scripts.recon.common import ProbeReport, now_iso, polite_get, save_sample
from scripts.recon.probe_supreme_court_bulk import check_pdf_has_text

SOURCE = "gujarat_hc_bulk"
BUCKET_URL = "https://indian-high-court-judgments.s3.ap-south-1.amazonaws.com/"
STATS_MD_URL = (
    "https://raw.githubusercontent.com/vanga/"
    "indian-high-court-judgments/main/STATS.md"
)
COURT_CODE = "24_17"
BENCH = "gujarathc"
CANDIDATE_YEARS = [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2015, 2020, 2023, 2024, 2025, 2026]

_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def metadata_key_for_year(year: int) -> str:
    return f"metadata/parquet/year={year}/court={COURT_CODE}/bench={BENCH}/metadata.parquet"


def check_bucket_reachable() -> bool:
    return polite_get(BUCKET_URL).status_code == 200


def fetch_stats_md() -> str:
    response = polite_get(STATS_MD_URL)
    return response.text if response.status_code == 200 else ""


def find_years_present(years: list[int] = CANDIDATE_YEARS) -> list[int]:
    present = []
    for year in years:
        url = f"{BUCKET_URL}{metadata_key_for_year(year)}"
        response = polite_get(url)
        if response.status_code == 200:
            present.append(year)
    return present


def fetch_sample_metadata_fields(year: int) -> list[str]:
    url = f"{BUCKET_URL}{metadata_key_for_year(year)}"
    response = polite_get(url)
    if response.status_code != 200:
        return []
    save_sample(response.content, SOURCE, f"metadata_year_{year}.parquet")
    table = pq.read_table(io.BytesIO(response.content))
    return table.column_names


def find_sample_pdf_key(year: int) -> str | None:
    url = (
        f"{BUCKET_URL}?list-type=2&prefix="
        f"data/pdf/year={year}/court={COURT_CODE}/bench={BENCH}/&max-keys=1"
    )
    response = polite_get(url)
    if response.status_code != 200:
        return None
    root = ET.fromstring(response.text)
    key_el = root.find(f"{_S3_NS}Contents/{_S3_NS}Key")
    return key_el.text if key_el is not None else None


def run() -> ProbeReport:
    notes: list[str] = []
    reachable = check_bucket_reachable()

    stats_md = fetch_stats_md()
    if not stats_md:
        notes.append("STATS.md was not reachable")

    years_present = find_years_present()
    if not years_present:
        notes.append("no candidate year had Gujarat HC metadata — check court/bench code")

    sample_fields: list[str] = []
    if years_present:
        sample_year = years_present[-1]
        sample_fields = fetch_sample_metadata_fields(sample_year)

        pdf_key = find_sample_pdf_key(sample_year)
        if pdf_key:
            pdf_response = polite_get(f"{BUCKET_URL}{pdf_key}")
            if pdf_response.status_code == 200:
                save_sample(pdf_response.content, SOURCE, pdf_key.split("/")[-1])
                if not check_pdf_has_text(pdf_response.content):
                    notes.append("sample PDF has no extractable text — may need OCR")
        else:
            notes.append(f"could not find a sample PDF key for year={sample_year}")

    licence = get_licence(SOURCE)

    return ProbeReport(
        source=SOURCE,
        reachable=reachable,
        auth_required=False,
        access_method="public_s3_https",
        sample_fields=sample_fields,
        approx_volume={
            "years_present": years_present,
            "candidate_years_checked": CANDIDATE_YEARS,
            "court_code": COURT_CODE,
            "bench": BENCH,
        },
        formats=["pdf", "json", "parquet"],
        licence=licence.licence,
        attribution_required=licence.attribution_required,
        notes=notes,
        checked_at=now_iso(),
    )


if __name__ == "__main__":
    report = run()
    print(report.model_dump_json(indent=2))
    report.save()
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_probe_gujarat_hc_bulk.py -v`
Expected: 1 passed

---

### Task 7: Probe — India Code

**Files:**
- Create: `scripts/recon/probe_india_code.py`
- Test: `tests/test_probe_india_code.py`

**Interfaces:**
- Consumes: `ProbeReport`, `polite_get`, `now_iso` from `scripts.recon.common`;
  `get_licence` from `legal_ai.sources.licensing`.
- Produces: `run() -> ProbeReport` with `source="india_code"`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_probe_india_code.py
import responses

from scripts.recon.probe_india_code import BROWSE_URL, SAMPLE_SEARCH_URL, run

BROWSE_HTML = """
<html><body>
<div class="pagination-info">1 - 20 of 1450</div>
<a href="/handle/123456789/2263">The Specific Relief Act, 1963</a>
</body></html>
"""

SEARCH_HTML = """
<html><body>
<div class="artifact-title">Specific Relief Act, 1963</div>
</body></html>
"""


@responses.activate
def test_run_reports_html_scrape_and_no_api(monkeypatch, tmp_path):
    responses.add(responses.GET, BROWSE_URL, body=BROWSE_HTML, status=200)
    responses.add(responses.GET, SAMPLE_SEARCH_URL, body=SEARCH_HTML, status=200)

    monkeypatch.chdir(tmp_path)
    report = run()

    assert report.source == "india_code"
    assert report.reachable is True
    assert report.access_method == "html_scrape"
    assert report.formats == ["html"]
    assert report.approx_volume.get("central_acts_count") == 1450
    assert any("no json api" in note.lower() or "no api" in note.lower() for note in report.notes)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_probe_india_code.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.recon.probe_india_code'`

- [x] **Step 3: Write the implementation**

```python
# scripts/recon/probe_india_code.py
"""Probe: India Code Central Acts browse/search.

See docs/LEGAL_DATA_SOURCES.md §3 and
docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.3.
"""

from __future__ import annotations

import re

from legal_ai.sources.licensing import get_licence
from scripts.recon.common import ProbeReport, now_iso, polite_get

SOURCE = "india_code"
BROWSE_URL = "https://www.indiacode.nic.in/handle/123456789/1362"
SAMPLE_SEARCH_URL = (
    "https://www.indiacode.nic.in/handle/123456789/1362/"
    "simple-search?query=specific+relief+act"
)

_COUNT_PATTERN = re.compile(r"\d+\s*-\s*\d+\s*of\s*(\d+)")


def estimate_act_count(html: str) -> int | None:
    match = _COUNT_PATTERN.search(html)
    return int(match.group(1)) if match else None


def run() -> ProbeReport:
    notes: list[str] = []

    browse_response = polite_get(BROWSE_URL)
    reachable = browse_response.status_code == 200

    act_count = None
    if reachable:
        act_count = estimate_act_count(browse_response.text)
        if act_count is None:
            notes.append("could not find a result-count element on the browse page")
    else:
        notes.append(f"browse page returned HTTP {browse_response.status_code}")

    search_response = polite_get(SAMPLE_SEARCH_URL)
    if search_response.status_code != 200 or "specific relief" not in search_response.text.lower():
        notes.append("sample search for 'Specific Relief Act' did not return the expected result")

    notes.append(
        "India Code exposes no JSON API — every field must come from HTML "
        "scraping of the browse/search/detail pages."
    )

    licence = get_licence(SOURCE)

    return ProbeReport(
        source=SOURCE,
        reachable=reachable,
        auth_required=False,
        access_method="html_scrape",
        sample_fields=["act_title", "act_url"],
        approx_volume={"central_acts_count": act_count},
        formats=["html"],
        licence=licence.licence,
        attribution_required=licence.attribution_required,
        notes=notes,
        checked_at=now_iso(),
    )


if __name__ == "__main__":
    report = run()
    print(report.model_dump_json(indent=2))
    report.save()
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_probe_india_code.py -v`
Expected: 1 passed

---

### Task 8: Probe — official Supreme Court search portal

**Files:**
- Create: `scripts/recon/probe_official_scr_search.py`
- Test: `tests/test_probe_official_scr_search.py`

**Interfaces:**
- Consumes: same as Task 7.
- Produces: `run() -> ProbeReport` with `source="official_scr_search"`, and
  `detect_rendering_mode(html: str) -> str` returning one of
  `"server_rendered" | "js_spa" | "unknown"`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_probe_official_scr_search.py
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


def test_detect_rendering_mode_flags_empty_spa_shell():
    assert detect_rendering_mode(SPA_HTML) == "js_spa"


def test_detect_rendering_mode_flags_populated_table():
    assert detect_rendering_mode(SERVER_RENDERED_HTML) == "server_rendered"


def test_detect_rendering_mode_falls_back_to_unknown():
    assert detect_rendering_mode("<html><body>hi</body></html>") == "unknown"


@responses.activate
def test_run_reports_reachability_and_rendering_mode(monkeypatch, tmp_path):
    responses.add(responses.GET, SEARCH_URL, body=SPA_HTML, status=200)

    monkeypatch.chdir(tmp_path)
    report = run()

    assert report.source == "official_scr_search"
    assert report.reachable is True
    assert report.access_method == "js_spa"
    assert any("javascript" in note.lower() or "spa" in note.lower() for note in report.notes)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_probe_official_scr_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.recon.probe_official_scr_search'`

- [x] **Step 3: Write the implementation**

```python
# scripts/recon/probe_official_scr_search.py
"""Probe: the official Supreme Court Reports search portal.

See docs/LEGAL_DATA_SOURCES.md §4 and
docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.3.
"""

from __future__ import annotations

import re

from legal_ai.sources.licensing import get_licence
from scripts.recon.common import ProbeReport, now_iso, polite_get

SOURCE = "official_scr_search"
SEARCH_URL = "https://scr.sci.gov.in/scrsearch/"

_SPA_SHELL_PATTERN = re.compile(r'id=["\'](app|root)["\']')
_POPULATED_ROW_PATTERN = re.compile(r"<tr[^>]*>.*?</tr>", re.IGNORECASE | re.DOTALL)


def detect_rendering_mode(html: str) -> str:
    rows = _POPULATED_ROW_PATTERN.findall(html)
    has_real_rows = any(re.search(r"<td", row, re.IGNORECASE) for row in rows)
    if has_real_rows:
        return "server_rendered"
    if _SPA_SHELL_PATTERN.search(html):
        return "js_spa"
    return "unknown"


def run() -> ProbeReport:
    notes: list[str] = []

    response = polite_get(SEARCH_URL)
    reachable = response.status_code == 200

    mode = "unknown"
    if reachable:
        mode = detect_rendering_mode(response.text)
        if mode == "js_spa":
            notes.append(
                "the page is a JavaScript SPA shell with no server-rendered "
                "results — this source is not scriptable with plain HTTP "
                "GETs; treat it as manual-verification-only for Phase 1"
            )
        elif mode == "unknown":
            notes.append(
                "could not determine rendering mode from the initial "
                "response — needs manual inspection before building a tool"
            )
    else:
        notes.append(f"search portal returned HTTP {response.status_code}")

    licence = get_licence(SOURCE)

    return ProbeReport(
        source=SOURCE,
        reachable=reachable,
        auth_required=False,
        access_method=mode,
        sample_fields=[],
        approx_volume={},
        formats=["html"],
        licence=licence.licence,
        attribution_required=licence.attribution_required,
        notes=notes,
        checked_at=now_iso(),
    )


if __name__ == "__main__":
    report = run()
    print(report.model_dump_json(indent=2))
    report.save()
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_probe_official_scr_search.py -v`
Expected: 4 passed

---

### Task 9: Probe — Bharat Courts SDK

**Files:**
- Create: `scripts/recon/probe_bharat_courts.py`
- Test: `tests/test_probe_bharat_courts.py`

**Interfaces:**
- Consumes: `ProbeReport`, `now_iso` from `scripts.recon.common`;
  `get_licence` from `legal_ai.sources.licensing`.
- Produces: `run() -> ProbeReport` with `source="bharat_courts"`,
  `attempt_install(package: str, timeout: int = 60) -> tuple[bool, str]`,
  `attempt_import(module_name: str = "bharat_courts") -> tuple[bool, str]`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_probe_bharat_courts.py
from scripts.recon.probe_bharat_courts import PACKAGE_CANDIDATES, run


def test_run_reports_fail_plainly_when_install_and_import_both_fail(monkeypatch, tmp_path):
    def fake_attempt_install(package, timeout=60):
        return False, f"ERROR: No matching distribution found for {package}"

    def fake_attempt_import(module_name="bharat_courts"):
        return False, "No module named 'bharat_courts'"

    import scripts.recon.probe_bharat_courts as mod

    monkeypatch.setattr(mod, "attempt_install", fake_attempt_install)
    monkeypatch.setattr(mod, "attempt_import", fake_attempt_import)
    monkeypatch.chdir(tmp_path)

    report = run()

    assert report.source == "bharat_courts"
    assert report.reachable is False
    assert report.access_method == "sdk"
    assert any("no matching distribution" in note.lower() for note in report.notes)
    assert len(report.notes) >= len(PACKAGE_CANDIDATES)


def test_run_reports_success_when_install_and_import_succeed(monkeypatch, tmp_path):
    def fake_attempt_install(package, timeout=60):
        return True, f"Successfully installed {package}"

    def fake_attempt_import(module_name="bharat_courts"):
        return True, module_name

    import scripts.recon.probe_bharat_courts as mod

    monkeypatch.setattr(mod, "attempt_install", fake_attempt_install)
    monkeypatch.setattr(mod, "attempt_import", fake_attempt_import)
    monkeypatch.chdir(tmp_path)

    report = run()

    assert report.reachable is True
    assert any("installed and importable" in note.lower() for note in report.notes)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_probe_bharat_courts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.recon.probe_bharat_courts'`

- [x] **Step 3: Write the implementation**

```python
# scripts/recon/probe_bharat_courts.py
"""Probe: the Bharat Courts SDK (github.com/iamshouvikmitra/bharat-courts).

Per docs/LEGAL_DATA_SOURCES.md §8, this is a programmatic access layer,
not a new legal authority, and its own README notes live court access
often needs CAPTCHA/session handling. A clean "does not install / does not
import" report is a valid, useful outcome here — see
docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.3.
"""

from __future__ import annotations

import importlib
import subprocess
import sys

from legal_ai.sources.licensing import get_licence
from scripts.recon.common import ProbeReport, now_iso

SOURCE = "bharat_courts"
PACKAGE_CANDIDATES = ["bharat-courts", "bharatcourts"]
MODULE_CANDIDATES = ["bharat_courts", "bharatcourts"]


def attempt_install(package: str, timeout: int = 60) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"pip install {package} timed out after {timeout}s"
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output.strip()[-500:]


def attempt_import(module_name: str = "bharat_courts") -> tuple[bool, str]:
    try:
        importlib.import_module(module_name)
        return True, module_name
    except ImportError as exc:
        return False, str(exc)


def run() -> ProbeReport:
    notes: list[str] = []
    installed = False
    imported = False

    for package, module_name in zip(PACKAGE_CANDIDATES, MODULE_CANDIDATES):
        ok, output = attempt_install(package)
        notes.append(f"pip install {package}: {'ok' if ok else 'failed'} — {output}")
        if ok:
            installed = True
            import_ok, import_output = attempt_import(module_name)
            notes.append(
                f"import {module_name}: {'ok' if import_ok else 'failed'} — {import_output}"
            )
            if import_ok:
                imported = True
                break

    if installed and imported:
        notes.append(
            "package installed and importable — needs a manual follow-up "
            "call against a real endpoint to confirm it actually works "
            "(CAPTCHA/session handling per its own README)"
        )
    elif not installed:
        notes.append(
            "could not install under either candidate package name — "
            "installing from source may be required; report this as a "
            "gap, not a blocker, per the spec's Phase-1 recommendation"
        )

    licence = get_licence(SOURCE)

    return ProbeReport(
        source=SOURCE,
        reachable=installed and imported,
        auth_required=True,
        access_method="sdk",
        sample_fields=[],
        approx_volume={},
        formats=[],
        licence=licence.licence,
        attribution_required=licence.attribution_required,
        notes=notes,
        checked_at=now_iso(),
    )


if __name__ == "__main__":
    report = run()
    print(report.model_dump_json(indent=2))
    report.save()
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_probe_bharat_courts.py -v`
Expected: 2 passed

---

### Task 10: Findings aggregator

**Files:**
- Create: `scripts/recon/aggregate.py`
- Test: `tests/test_aggregate.py`

**Interfaces:**
- Consumes: `ProbeReport`, `REPORTS_DIR` from `scripts.recon.common`.
- Produces: `load_reports(directory: Path) -> list[ProbeReport]`,
  `render_markdown(reports: list[ProbeReport]) -> str`,
  `main(reports_dir: Path = REPORTS_DIR, output_path: Path =
  Path("docs/DATA_RECON_FINDINGS.md")) -> Path`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_aggregate.py
from pathlib import Path

from scripts.recon.aggregate import load_reports, main, render_markdown
from scripts.recon.common import ProbeReport


def _sample_report(source: str, reachable: bool) -> ProbeReport:
    return ProbeReport(
        source=source,
        reachable=reachable,
        auth_required=False,
        access_method="public_s3_https",
        sample_fields=["citation"],
        approx_volume={"years": "1950-2026"},
        formats=["pdf", "parquet"],
        licence="CC-BY-4.0",
        attribution_required=True,
        notes=["all good"] if reachable else ["not reachable"],
        checked_at="2026-08-14T00:00:00+00:00",
    )


def test_load_reports_reads_all_json_files(tmp_path):
    _sample_report("supreme_court_bulk", True).save(tmp_path)
    _sample_report("india_code", False).save(tmp_path)

    reports = load_reports(tmp_path)

    assert {r.source for r in reports} == {"supreme_court_bulk", "india_code"}


def test_render_markdown_includes_summary_table_and_per_source_sections():
    reports = [_sample_report("supreme_court_bulk", True), _sample_report("india_code", False)]

    markdown = render_markdown(reports)

    assert "| Source | Reachable |" in markdown
    assert "supreme_court_bulk" in markdown
    assert "india_code" in markdown
    assert "CC-BY-4.0" in markdown


def test_main_writes_output_file(tmp_path):
    reports_dir = tmp_path / "reports"
    output_path = tmp_path / "DATA_RECON_FINDINGS.md"
    _sample_report("supreme_court_bulk", True).save(reports_dir)

    result_path = main(reports_dir=reports_dir, output_path=output_path)

    assert result_path == output_path
    assert output_path.exists()
    assert "supreme_court_bulk" in output_path.read_text()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_aggregate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.recon.aggregate'`

- [x] **Step 3: Write the implementation**

```python
# scripts/recon/aggregate.py
"""Render every scripts/recon/*.json ProbeReport into one findings doc.

See docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.4.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.recon.common import ProbeReport, REPORTS_DIR

DEFAULT_OUTPUT_PATH = Path("docs/DATA_RECON_FINDINGS.md")


def load_reports(directory: Path = REPORTS_DIR) -> list[ProbeReport]:
    if not directory.exists():
        return []
    reports = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        reports.append(ProbeReport.model_validate(data))
    return reports


def _verdict(report: ProbeReport) -> str:
    if not report.reachable:
        return "not viable for Phase 1 as probed — needs more investigation"
    if report.notes:
        return "reachable, with caveats — see notes"
    return "ready to build an ingestion adapter against"


def render_markdown(reports: list[ProbeReport]) -> str:
    lines = [
        "# Phase 1 Data Recon Findings",
        "",
        "Generated from `scripts/recon/aggregate.py` — do not hand-edit; "
        "re-run the probes and regenerate instead.",
        "",
        "## Summary",
        "",
        "| Source | Reachable | Access method | Formats | Licence | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for report in reports:
        lines.append(
            f"| {report.source} | {report.reachable} | {report.access_method} "
            f"| {', '.join(report.formats) or '—'} | {report.licence} "
            f"| {_verdict(report)} |"
        )

    lines.append("")
    lines.append("## Per-source detail")

    for report in reports:
        lines.append("")
        lines.append(f"### {report.source}")
        lines.append("")
        lines.append(f"- **Reachable:** {report.reachable}")
        lines.append(f"- **Auth required:** {report.auth_required}")
        lines.append(f"- **Access method:** {report.access_method}")
        lines.append(f"- **Sample fields:** {', '.join(report.sample_fields) or '—'}")
        lines.append(f"- **Approx volume:** `{report.approx_volume}`")
        lines.append(f"- **Formats:** {', '.join(report.formats) or '—'}")
        lines.append(
            f"- **Licence:** {report.licence} "
            f"(attribution required: {report.attribution_required})"
        )
        lines.append(f"- **Checked at:** {report.checked_at}")
        if report.notes:
            lines.append("- **Notes:**")
            for note in report.notes:
                lines.append(f"  - {note}")

    lines.append("")
    return "\n".join(lines)


def main(
    reports_dir: Path = REPORTS_DIR,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    reports = load_reports(reports_dir)
    markdown = render_markdown(reports)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown)
    return output_path


if __name__ == "__main__":
    path = main()
    print(f"Wrote {path}")
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_aggregate.py -v`
Expected: 3 passed

---

### Task 11: Run all probes for real and generate the findings doc

**Files:**
- Modify: none (execution-only task)
- Reads: every file created in Tasks 5–10

**Interfaces:**
- Consumes: `run()` from each of the five probe modules; `main()` from
  `scripts.recon.aggregate`.
- Produces: `data/recon/reports/*.json` (five files, gitignored) and
  `docs/DATA_RECON_FINDINGS.md` (committed by the user, not by this task).

This task hits the real, live sources. Everything before it was tested
against mocks — this is where the actual recon happens.

- [x] **Step 1: Run the full test suite once more before touching the network**

Run: `pytest -v`
Expected: all tests from Tasks 2–10 pass (22 passed total: 2 + 3 + 4 + 2 +
1 + 1 + 4 + 2 + 3, for Tasks 2 through 10 respectively).

- [x] **Step 2: Run each probe against the real sources**

```bash
python -m scripts.recon.probe_supreme_court_bulk
python -m scripts.recon.probe_gujarat_hc_bulk
python -m scripts.recon.probe_india_code
python -m scripts.recon.probe_official_scr_search
python -m scripts.recon.probe_bharat_courts
```

Expected: each prints a `ProbeReport` JSON blob to stdout and exits 0 (a
probe reporting `"reachable": false` is a valid exit-0 outcome — only a
Python traceback is a failure here). Confirm
`data/recon/reports/<source>.json` exists for all five after this step.

- [x] **Step 3: Generate the findings document**

Run: `python -m scripts.recon.aggregate`
Expected: prints `Wrote docs/DATA_RECON_FINDINGS.md`; the file exists and
contains five `###` sections, one per source.

- [x] **Step 4: Read the generated findings and sanity-check against the spec's success criteria**

Open `docs/DATA_RECON_FINDINGS.md` and confirm, for each of the five
sources, that the spec's six success criteria
(`docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md` §7) are
answerable from what's written: reachability + access method, real
field/column names, approximate volume, formats, licence/attribution, and a
one-line verdict. If a source's report is thin (e.g. Bharat Courts failed
to install), that thinness is itself the finding — do not fill gaps by
hand-editing the generated file; re-run the relevant probe script if a
transient failure is suspected.

- [x] **Step 5: Stop here**

Do not commit. Leave `docs/DATA_RECON_FINDINGS.md` and the new source tree
for the user to review and commit themselves, per the standing project
instruction.
