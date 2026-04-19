"""
Verify watchlist ATS boards return jobs and that Canada/Toronto filter yields results.
Run: python scripts/verify_toronto_jobs.py
Prints per company: total jobs fetched, count passing location filter, sample titles+locations.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_watchlist, load_filters
from src.ats.greenhouse import fetch_jobs as gh_fetch
from src.ats.lever import fetch_jobs as lever_fetch
from src.ats.ashby import fetch_jobs as ashby_fetch
from src.filters import filter_jobs


def main() -> None:
    companies = load_watchlist()
    filters = load_filters()
    locations = filters.get("locations") or []
    level_keywords = filters.get("level_keywords") or []
    title_keywords = filters.get("title_keywords") or []
    exclude_keywords = filters.get("exclude_keywords")

    # Only companies with explicit ATS (the ones we care about for Toronto)
    with_ats = [
        (e.get("name"), e.get("ats_type"), e.get("board_id"))
        for e in companies
        if e.get("ats_type") and e.get("board_id")
    ]

    print("Toronto/Canada job verification (boards + location filter)\n" + "=" * 70)
    print(f"Location keywords (first 8): {locations[:8]}...")
    print()

    total_fetched = 0
    total_passing = 0
    samples = []

    for name, ats_type, board_id in with_ats:
        jobs = []
        try:
            if ats_type == "greenhouse":
                jobs = gh_fetch(board_id)
            elif ats_type == "lever":
                jobs = lever_fetch(board_id)
            elif ats_type == "ashby":
                jobs = ashby_fetch(board_id)
        except Exception as e:
            print(f"  {name} ({ats_type}/{board_id}): ERROR - {e}")
            continue

        for j in jobs:
            j["company_name"] = name

        filtered = filter_jobs(
            jobs,
            locations=locations,
            level_keywords=level_keywords,
            title_keywords=title_keywords,
            exclude_keywords=exclude_keywords,
            max_days_since_posted=filters.get("max_days_since_posted"),
            allow_empty_location=filters.get("allow_empty_location", False),
            require_location_field_match=filters.get("require_location_field_match", False),
            entry_level_only=filters.get("entry_level_only", True),
            use_jd_experience_filter=filters.get("use_jd_experience_filter", True),
            jd_filter_mode=filters.get("jd_filter_mode", "standard"),
            match_mode=filters.get("match_mode", "substring"),
            title_synonym_groups=filters.get("title_synonym_groups"),
            location_accept_aliases=filters.get("location_accept_aliases"),
            allow_title_canada_signal=filters.get("allow_title_canada_signal", True),
            newgrad_title_rescue=filters.get("newgrad_title_rescue", True),
        )

        total_fetched += len(jobs)
        total_passing += len(filtered)
        n = len(jobs)
        m = len(filtered)
        status = "OK" if n > 0 else "ZERO"
        print(f"  {name}: {n} jobs fetched, {m} pass Canada/Toronto filter [{status}]")

        for j in filtered[:3]:
            loc = (j.get("location") or "")[:60]
            title = (j.get("title") or "")[:50]
            samples.append((name, title, loc))

    print()
    print("=" * 70)
    print(f"Total: {total_fetched} jobs fetched, {total_passing} pass filter")
    print()
    print("Sample Toronto/Canada jobs (title | location):")
    for name, title, loc in samples[:15]:
        print(f"  {name}: {title!r} | {loc!r}")


if __name__ == "__main__":
    main()
