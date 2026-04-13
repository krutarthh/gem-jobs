"""
Entry: load config, run scraper, diff, notify.
Run once: python -m src.main
"""

import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

import requests

from src.config import DISCORD_REVIEW_WEBHOOK_URL, load_db_cleanup, load_filters, load_watchlist
from src.db import (
    finish_run,
    get_new_jobs_since,
    init_db,
    run_database_cleanup,
    start_run,
    upsert_company,
    upsert_job,
)
from src.ats import detect_ats, detect_ats_from_html, fetch_jobs_for_company
from src.filters import filter_jobs
from src.notify import send_discord_new_jobs, send_discord_review_jobs

REQUEST_TIMEOUT = 10


def _dedupe_jobs_by_company_title_url(jobs: list[dict]) -> list[dict]:
    seen_key: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for j in jobs:
        key = (
            (j.get("company_name") or "").strip(),
            (j.get("title") or "").strip(),
            (j.get("url") or "").strip(),
        )
        if key in seen_key:
            continue
        seen_key.add(key)
        out.append(j)
    return out


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


def _normalize_external_id(external_id: str, job_url: str | None) -> str:
    """
    Return a stable external_id so the same job always maps to the same DB row.
    - Numeric/opaque ids: use as-is (string).
    - URL-based ids: strip query, fragment, trailing slash and lowercase so
      https://x.com/job?ref=1 and https://x.com/job are the same.
    """
    s = (external_id or "").strip()
    if not s and job_url:
        s = (job_url or "").strip()
    if not s:
        return ""
    # If it looks like a URL, canonicalize so we don't get duplicates from ?ref= etc.
    if s.startswith("http://") or s.startswith("https://"):
        try:
            parsed = urlparse(s)
            # scheme, netloc, path only; no query, fragment; path rstrip /
            path = (parsed.path or "/").rstrip("/") or "/"
            canonical = urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))
            return canonical
        except Exception:
            return s
    return s


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
            raw_id = j.get("id")
            if raw_id is None:
                raw_id = j.get("url") or ""
            external_id = _normalize_external_id(str(raw_id).strip(), j.get("url"))
            if not external_id:
                continue
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
                description=j.get("description"),
            )
            if is_new:
                new_count += 1

    new_jobs = get_new_jobs_since(run_started)
    jd_mode = filters.get("jd_filter_mode", "standard")
    shared_kw = dict(
        locations=filters["locations"],
        level_keywords=filters["level_keywords"],
        title_keywords=filters["title_keywords"],
        exclude_keywords=filters.get("exclude_keywords"),
        allow_empty_location=filters.get("allow_empty_location", False),
        require_location_field_match=filters.get("require_location_field_match", False),
        entry_level_only=filters.get("entry_level_only", True),
        jd_filter_mode=jd_mode,
    )
    filtered = filter_jobs(
        new_jobs,
        max_days_since_posted=filters.get("max_days_since_posted"),
        use_jd_experience_filter=filters.get("use_jd_experience_filter", True),
        **shared_kw,
    )
    deduped = _dedupe_jobs_by_company_title_url(filtered)
    if deduped:
        send_discord_new_jobs(deduped)

    # Tier B: core match (no JD / no recency) minus strict pass — optional second webhook
    if DISCORD_REVIEW_WEBHOOK_URL.strip():
        core_pass = filter_jobs(
            new_jobs,
            max_days_since_posted=None,
            use_jd_experience_filter=False,
            **shared_kw,
        )
        core_deduped = _dedupe_jobs_by_company_title_url(core_pass)
        strict_keys = {
            (
                (j.get("company_name") or "").strip(),
                (j.get("title") or "").strip(),
                (j.get("url") or "").strip(),
            )
            for j in deduped
        }
        review = [
            j
            for j in core_deduped
            if (
                (j.get("company_name") or "").strip(),
                (j.get("title") or "").strip(),
                (j.get("url") or "").strip(),
            )
            not in strict_keys
        ]
        if review:
            send_discord_review_jobs(review)

    finish_run(run_id, companies_checked, new_count)

    cleanup_stats = run_database_cleanup(load_db_cleanup())
    if not cleanup_stats.get("skipped") and os.getenv("GITHUB_ACTIONS"):
        print(
            "db_cleanup:",
            f"jobs_removed={cleanup_stats.get('jobs_deleted', 0)}",
            f"runs_removed={cleanup_stats.get('runs_deleted', 0)}",
            f"companies_removed={cleanup_stats.get('companies_deleted', 0)}",
            f"descriptions_cleared={cleanup_stats.get('descriptions_cleared', 0)}",
            f"vacuum={cleanup_stats.get('vacuumed', False)}",
        )


def main() -> int:
    run_once()
    return 0


if __name__ == "__main__":
    sys.exit(main())
