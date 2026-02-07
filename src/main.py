"""
Entry: load config, run scraper, diff, notify.
Run once: python -m src.main
"""

import sys
from datetime import datetime, timezone

import requests

from src.config import load_filters, load_watchlist
from src.db import (
    finish_run,
    get_new_jobs_since,
    init_db,
    start_run,
    upsert_company,
    upsert_job,
)
from src.ats import detect_ats, detect_ats_from_html, fetch_jobs_for_company
from src.filters import filter_jobs
from src.notify import send_discord_new_jobs

REQUEST_TIMEOUT = 10


def _resolve_redirect(url: str) -> str:
    """Follow redirects and return final URL for ATS detection."""
    try:
        r = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            headers={"User-Agent": "GoldGemJobs/1.0"},
        )
        return r.url
    except requests.RequestException:
        return url


def run_once() -> None:
    """One full cycle: scrape all companies, upsert, filter new jobs, notify."""
    init_db()
    companies = load_watchlist()
    filters = load_filters()
    run_id = start_run()
    run_started = datetime.now(timezone.utc)
    companies_checked = 0
    new_count = 0

    for entry in companies:
        name = entry.get("name") or "Unknown"
        careers_url = (entry.get("careers_url") or "").strip()
        if not careers_url:
            continue
        # Use watchlist override if set (e.g. Toast -> Greenhouse board "toast")
        ats_type = entry.get("ats_type")
        board_id = entry.get("board_id")
        if not ats_type or not board_id:
            final_url = _resolve_redirect(careers_url)
            ats_type, board_id = detect_ats(final_url)
            if not board_id and ats_type != "generic":
                ats_type, board_id = detect_ats(careers_url)
            # If still generic, fetch page and scan for ATS (Greenhouse/Lever/Ashby) in HTML
            if ats_type == "generic" or not board_id:
                try:
                    r = requests.get(
                        careers_url,
                        timeout=REQUEST_TIMEOUT,
                        headers={"User-Agent": "GoldGemJobs/1.0"},
                    )
                    if r.ok:
                        discovered_type, discovered_id = detect_ats_from_html(r.text)
                        if discovered_id:
                            ats_type, board_id = discovered_type, discovered_id
                except requests.RequestException:
                    pass
        company_id = upsert_company(
            name=name,
            careers_url=careers_url,
            ats_type=ats_type,
            board_id=board_id,
        )
        companies_checked += 1
        jobs = fetch_jobs_for_company(ats_type, board_id, careers_url)
        for j in jobs:
            external_id = j.get("id")
            if external_id is None:
                external_id = j.get("url") or ""
            external_id = str(external_id)
            posted_at = j.get("posted_at")
            if posted_at is not None:
                posted_at = str(posted_at).strip() or None
            _, is_new = upsert_job(
                company_id=company_id,
                external_id=external_id,
                title=j.get("title"),
                location=j.get("location"),
                department=j.get("department"),
                url=j.get("url"),
                posted_at=posted_at,
            )
            if is_new:
                new_count += 1

    new_jobs = get_new_jobs_since(run_started)
    filtered = filter_jobs(
        new_jobs,
        locations=filters["locations"],
        level_keywords=filters["level_keywords"],
        title_keywords=filters["title_keywords"],
        exclude_keywords=filters.get("exclude_keywords"),
        max_days_since_posted=filters.get("max_days_since_posted"),
    )
    if filtered:
        send_discord_new_jobs(filtered)
    finish_run(run_id, companies_checked, new_count)


def main() -> int:
    run_once()
    return 0


if __name__ == "__main__":
    sys.exit(main())
