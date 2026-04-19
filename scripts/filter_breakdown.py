#!/usr/bin/env python3
"""
Print per-stage filter rejection counts for jobs stored in the DB.

Uses the same filter rules as production (watchlist.yaml). Helpful for tuning
locations, JD rules, and recency without guessing.

Usage:
  python scripts/filter_breakdown.py
  python scripts/filter_breakdown.py --days 14 --sample 5
  python scripts/filter_breakdown.py --discord   # post summary to DISCORD_REVIEW_WEBHOOK_URL
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Any

# Allow running from repo root without PYTHONPATH
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.config import DB_PATH, DISCORD_REVIEW_WEBHOOK_URL, load_filters  # noqa: E402
from src.db import get_jobs_first_seen_within_days, init_db  # noqa: E402
from src.filters import filter_failure_reason  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Filter rejection breakdown for recent jobs in DB")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Include jobs first seen in the last N days (default: 7)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max jobs to analyze (0 = no limit)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Print up to N example titles per rejection stage (0 = none)",
    )
    parser.add_argument(
        "--discord",
        action="store_true",
        help="Also post the summary line to DISCORD_REVIEW_WEBHOOK_URL (if set)",
    )
    args = parser.parse_args()

    init_db()
    filters = load_filters()
    jobs = get_jobs_first_seen_within_days(args.days)
    if args.limit and args.limit > 0:
        jobs = jobs[: args.limit]

    if not jobs:
        print(f"No jobs with first_seen_at in the last {args.days} days.")
        print(f"DB path: {DB_PATH}")
        return 0

    reasons: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}

    for j in jobs:
        r = filter_failure_reason(
            j,
            filters["locations"],
            filters["level_keywords"],
            filters["title_keywords"],
            exclude_keywords=filters.get("exclude_keywords"),
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
        if r is None:
            reasons["passed"] += 1
        else:
            reasons[r] += 1
            if args.sample > 0 and len(examples.get(r, [])) < args.sample:
                examples.setdefault(r, []).append(
                    f"{(j.get('company_name') or '?')[:40]} | {(j.get('title') or '')[:80]}"
                )

    total = len(jobs)
    print(f"Jobs analyzed: {total} (first_seen_in_last_{args.days}_days)")
    print(f"Watchlist: {os.getenv('WATCHLIST_PATH', 'config/watchlist.yaml')}")
    print()
    order = ["passed", "location", "location_field", "entry_level", "title_keywords", "exclude_keywords", "jd_experience", "recency"]
    for key in order:
        if key not in reasons:
            continue
        n = reasons[key]
        pct = 100.0 * n / total if total else 0
        print(f"  {key:20} {n:6}  ({pct:5.1f}%)")
    print()
    for k in sorted(reasons.keys()):
        if k not in order:
            print(f"  {k:20} {reasons[k]:6}  ({100.0 * reasons[k] / total:5.1f}%)")

    if args.sample > 0 and examples:
        print("\nExamples (per stage):")
        for stage in sorted(examples.keys()):
            print(f"\n  [{stage}]")
            for line in examples[stage]:
                print(f"    {line}")

    if args.discord:
        _post_summary_to_discord(args.days, total, reasons, examples)

    return 0


def _post_summary_to_discord(
    days: int,
    total: int,
    reasons: Counter[str],
    examples: dict[str, list[str]],
) -> None:
    url = (DISCORD_REVIEW_WEBHOOK_URL or "").strip()
    if not url:
        print("[filter_breakdown] --discord skipped: DISCORD_REVIEW_WEBHOOK_URL unset")
        return
    try:
        import requests  # local import so CI without network tools still runs the script
    except ImportError:
        return
    order = ["passed", "location", "location_field", "entry_level", "title_keywords", "exclude_keywords", "jd_experience", "recency"]
    parts = [f"{k}={reasons.get(k, 0)}" for k in order if k in reasons]
    header = f"filter_breakdown (last {days}d, n={total}): " + " ".join(parts)
    example_block = ""
    stage_of_interest = max(
        (k for k in reasons.keys() if k != "passed"),
        key=lambda k: reasons[k],
        default=None,
    )
    if stage_of_interest and examples.get(stage_of_interest):
        sample = "\n".join(examples[stage_of_interest][:3])
        example_block = f"\ntop excludes in `{stage_of_interest}`:\n{sample}"
    payload: dict[str, Any] = {"content": (header + example_block)[:1900]}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:  # pragma: no cover — best effort
        print(f"[filter_breakdown] discord post failed: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
