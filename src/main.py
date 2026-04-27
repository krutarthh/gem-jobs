"""
Entry: load config, run scraper, diff, notify.
Run once: python -m src.main
"""

import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from src.config import DISCORD_REVIEW_WEBHOOK_URL, load_db_cleanup, load_filters, load_watchlist
from src.db import (
    finish_run,
    get_new_jobs_since,
    has_notified_key,
    init_db,
    remember_notified_keys,
    run_database_cleanup,
    start_run,
    upsert_company,
    upsert_job,
)
from src.ats import fetch_jobs_for_company
from src.ats.resolve import resolve_ats_for_entry
from src.filters import filter_jobs
from src.keywords import annotate_with_keywords
from src.notify import send_discord_new_jobs, send_discord_review_jobs
from src.scoring import rank_jobs


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


def _normalized_notify_key(job: dict) -> str:
    """Stable identity that survives repostings under different external_ids."""
    company = (job.get("company_name") or "").strip().lower()
    title = (job.get("title") or "").strip().lower()
    # Collapse runs of whitespace/punct so "Software Engineer, II" == "software engineer ii".
    title = re.sub(r"[^a-z0-9]+", " ", title).strip()
    return f"{company}|{title}"


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
        ats_type, board_id = resolve_ats_for_entry(entry)
        company_id = upsert_company(
            name=name,
            careers_url=careers_url,
            ats_type=ats_type,
            board_id=board_id,
        )
        companies_checked += 1
        jobs = fetch_jobs_for_company(ats_type, board_id, careers_url)
        # Surface zero-job companies so CI logs catch silent watchlist rot.
        if not jobs:
            print(f"[warn] 0-jobs: {name} (ats={ats_type or 'unknown'} board={board_id or '-'})", flush=True)
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
        match_mode=filters.get("match_mode", "substring"),
        title_synonym_groups=filters.get("title_synonym_groups"),
        location_accept_aliases=filters.get("location_accept_aliases"),
        allow_title_canada_signal=filters.get("allow_title_canada_signal", True),
        newgrad_title_rescue=filters.get("newgrad_title_rescue", True),
        max_yoe_accept=int(filters.get("max_yoe_accept", 3)),
    )
    filtered = filter_jobs(
        new_jobs,
        max_days_since_posted=filters.get("max_days_since_posted"),
        use_jd_experience_filter=filters.get("use_jd_experience_filter", True),
        **shared_kw,
    )
    deduped = _dedupe_jobs_by_company_title_url(filtered)
    # Cross-run dedupe: never re-notify the same (company, normalized_title) pair.
    fresh: list[dict] = []
    fresh_keys: list[str] = []
    for j in deduped:
        key = _normalized_notify_key(j)
        if not key or has_notified_key(key):
            continue
        fresh.append(j)
        fresh_keys.append(key)
    deduped = fresh
    deduped = rank_jobs(deduped, location_priority=filters.get("location_priority"))
    annotate_with_keywords(deduped)
    if deduped:
        if send_discord_new_jobs(deduped):
            remember_notified_keys(fresh_keys)

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
        review = rank_jobs(review, location_priority=filters.get("location_priority"))
        annotate_with_keywords(review)
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
