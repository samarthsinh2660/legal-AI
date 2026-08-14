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


def test_run_reports_reachable_only_when_a_real_call_actually_returns_data(monkeypatch, tmp_path):
    """Installed + importable is not enough to call this source reachable —
    only a live call that actually returns data proves it works."""

    def fake_attempt_install(package, timeout=60):
        return True, f"Successfully installed {package}"

    def fake_attempt_import(module_name="bharat_courts"):
        return True, module_name

    def fake_attempt_live_call(limit=3):
        return (
            True,
            ["title", "court_name", "case_number", "judgment_date", "pdf_url", "source_id"],
            "list_recent_judgments(limit=3) returned 3 real, current Supreme "
            "Court judgments with no CAPTCHA required",
        )

    import scripts.recon.probe_bharat_courts as mod

    monkeypatch.setattr(mod, "attempt_install", fake_attempt_install)
    monkeypatch.setattr(mod, "attempt_import", fake_attempt_import)
    monkeypatch.setattr(mod, "attempt_live_call", fake_attempt_live_call)
    monkeypatch.chdir(tmp_path)

    report = run()

    assert report.reachable is True
    assert "title" in report.sample_fields
    assert "case_number" in report.sample_fields
    assert "json" in report.formats
    assert any("no captcha required" in note.lower() for note in report.notes)


def test_run_reports_installed_but_not_reachable_when_the_live_call_fails(monkeypatch, tmp_path):
    """Installing and importing cleanly, but the actual data call failing
    (dead endpoint, changed markup, network issue) must not be reported as
    success — that's exactly the kind of false positive this fix exists to
    prevent."""

    def fake_attempt_install(package, timeout=60):
        return True, f"Successfully installed {package}"

    def fake_attempt_import(module_name="bharat_courts"):
        return True, module_name

    def fake_attempt_live_call(limit=3):
        return False, [], "list_recent_judgments() raised: ConnectionError(...)"

    import scripts.recon.probe_bharat_courts as mod

    monkeypatch.setattr(mod, "attempt_install", fake_attempt_install)
    monkeypatch.setattr(mod, "attempt_import", fake_attempt_import)
    monkeypatch.setattr(mod, "attempt_live_call", fake_attempt_live_call)
    monkeypatch.chdir(tmp_path)

    report = run()

    assert report.reachable is False
    assert report.sample_fields == []
    assert any("raised" in note.lower() for note in report.notes)
