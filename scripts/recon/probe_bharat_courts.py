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


def attempt_live_call(limit: int = 3) -> tuple[bool, list[str], str]:
    """Attempt one real, low-cost call: SCIClient.list_recent_judgments().

    Confirmed by hand-inspection of the SDK's docstring that this specific
    method needs no CAPTCHA — it scrapes the SC homepage's public "Latest
    Judgements" feed. This is different from search_by_party/search_by_year,
    which the SDK itself marks not-implemented, and from the official
    portal's CAPTCHA-gated diary-number search form (see
    probe_official_scr_search.py) that this SDK does not attempt to solve
    for that particular endpoint.
    """
    import asyncio

    try:
        import bharat_courts
    except ImportError as exc:
        return False, [], f"bharat_courts not importable: {exc}"

    async def _call():
        async with bharat_courts.SCIClient() as client:
            return await client.list_recent_judgments(limit=limit)

    try:
        results = asyncio.run(_call())
    except Exception as exc:  # noqa: BLE001 - live network/API failure is a valid finding
        return False, [], f"list_recent_judgments() raised: {exc}"

    if not results:
        return False, [], "list_recent_judgments() returned zero results"

    fields = sorted(vars(results[0]).keys())
    return (
        True,
        fields,
        f"list_recent_judgments(limit={limit}) returned {len(results)} real, "
        "current Supreme Court judgments with no CAPTCHA required",
    )


def run() -> ProbeReport:
    notes: list[str] = []
    installed = False
    imported = False
    working_module = None

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
                working_module = module_name
                break

    sample_fields: list[str] = []
    formats: list[str] = []
    approx_volume: dict = {}
    live_call_ok = False

    if installed and imported and working_module == "bharat_courts":
        live_call_ok, sample_fields, live_note = attempt_live_call()
        notes.append(live_note)
        if live_call_ok:
            formats = ["json", "pdf"]
            approx_volume = {"list_recent_judgments_cap": 50}
    elif installed and imported:
        notes.append(
            f"installed under fallback module '{working_module}' — no known "
            "live-call target for this module name, needs manual follow-up"
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
        reachable=installed and imported and live_call_ok,
        auth_required=True,
        access_method="sdk",
        sample_fields=sample_fields,
        approx_volume=approx_volume,
        formats=formats,
        licence=licence.licence,
        attribution_required=licence.attribution_required,
        notes=notes,
        checked_at=now_iso(),
    )


if __name__ == "__main__":
    report = run()
    print(report.model_dump_json(indent=2))
    report.save()
