# Phase 1 Data Recon Findings

Generated from `scripts/recon/aggregate.py` — do not hand-edit; re-run the probes and regenerate instead.

## Summary

| Source | Reachable | Access method | Formats | Licence | Verdict |
|---|---|---|---|---|---|
| bharat_courts | True | sdk | json, pdf | Programmatic access layer over official sources | reachable, with caveats — see notes |
| gujarat_hc_bulk | True | public_s3_https | pdf, json, parquet | CC-BY-4.0 | ready to build an ingestion adapter against |
| india_code | True | html_scrape | html | Government of India — primary legislative source | reachable, with caveats — see notes |
| official_scr_search | True | captcha_protected | html | Government of India — official court portal | reachable, with caveats — see notes |
| supreme_court_bulk | True | public_s3_https | pdf, json, parquet | CC-BY-4.0 | ready to build an ingestion adapter against |

## Per-source detail

### bharat_courts

- **Reachable:** True
- **Auth required:** True
- **Access method:** sdk
- **Sample fields:** bench_type, case_number, citation, court_name, judges, judgment_date, metadata, pdf_bytes, pdf_url, source_id, source_url, title
- **Approx volume:** `{'list_recent_judgments_cap': 50}`
- **Formats:** json, pdf
- **Licence:** Programmatic access layer over official sources (attribution required: False)
- **Checked at:** 2026-08-14T20:57:05.278169+00:00
- **Notes:**
  - pip install bharat-courts: ok — >bharat-courts) (1.2.2)
Requirement already satisfied: typing-inspection>=0.4.0 in ./.venv/lib/python3.12/site-packages (from pydantic-settings>=2.7->bharat-courts) (0.4.4)
Requirement already satisfied: annotated-types>=0.6.0 in ./.venv/lib/python3.12/site-packages (from pydantic>=2.7.0->pydantic-settings>=2.7->bharat-courts) (0.8.0)
Requirement already satisfied: pydantic-core==2.46.4 in ./.venv/lib/python3.12/site-packages (from pydantic>=2.7.0->pydantic-settings>=2.7->bharat-courts) (2.46.4)
  - import bharat_courts: ok — bharat_courts
  - list_recent_judgments(limit=3) returned 3 real, current Supreme Court judgments with no CAPTCHA required

### gujarat_hc_bulk

- **Reachable:** True
- **Auth required:** False
- **Access method:** public_s3_https
- **Sample fields:** court_code, title, description, judge, pdf_link, cnr, date_of_registration, decision_date, disposal_nature, court, raw_html, pdf_exists
- **Approx volume:** `{'years_present': [2000, 2010, 2015, 2020, 2023, 2024, 2025, 2026], 'candidate_years_checked': [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2015, 2020, 2023, 2024, 2025, 2026], 'court_code': '24_17', 'bench': 'gujarathc'}`
- **Formats:** pdf, json, parquet
- **Licence:** CC-BY-4.0 (attribution required: True)
- **Checked at:** 2026-08-14T20:23:42.369716+00:00

### india_code

- **Reachable:** True
- **Auth required:** False
- **Access method:** html_scrape
- **Sample fields:** act_title, act_url
- **Approx volume:** `{'central_acts_count': 845}`
- **Formats:** html
- **Licence:** Government of India — primary legislative source (attribution required: False)
- **Checked at:** 2026-08-14T20:56:55.442871+00:00
- **Notes:**
  - India Code exposes no JSON API — every field must come from HTML scraping of the browse/search/detail pages.

### official_scr_search

- **Reachable:** True
- **Auth required:** False
- **Access method:**
- **Sample fields:** —
- **Approx volume:** `{}`
- **Formats:** html
- **Licence:** Government of India — official court portal (attribution required: False)
- **Checked at:** 2026-08-14T20:57:00.353960+00:00
- **Notes:**

### supreme_court_bulk

- **Reachable:** True
- **Auth required:** False
- **Access method:** public_s3_https
- **Sample fields:** title, petitioner, respondent, description, judge, author_judge, citation, case_id, cnr, decision_date, disposal_nature, court, available_languages, raw_html, path, nc_display, scraped_at, year
- **Approx volume:** `{'dataset_sizes_csv_rows': 78}`
- **Formats:** pdf, json, parquet
- **Licence:** CC-BY-4.0 (attribution required: True)
- **Checked at:** 2026-08-14T20:23:01.228361+00:00
