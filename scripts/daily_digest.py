#!/usr/bin/env python3
"""
Post a once-daily Top-K digest of unapplied, Toronto-leaning new jobs to a
dedicated Discord webhook.

Reads jobs first seen in the last N hours from the SQLite DB, applies the same
filter rules as the scraper, scores them, and sends the top-K embeds to
``DISCORD_DIGEST_WEBHOOK_URL`` (falls back to ``DISCORD_REVIEW_WEBHOOK_URL``,
then ``DISCORD_WEBHOOK_URL``).

Usage:
  python scripts/daily_digest.py
  python scripts/daily_digest.py --hours 24 --top 20
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import (  # noqa: E402
    DISCORD_REVIEW_WEBHOOK_URL,
    DISCORD_WEBHOOK_URL,
    load_filters,
)
from src.db import get_new_jobs_since, init_db  # noqa: E402
from src.filters import filter_jobs  # noqa: E402
from src.keywords import annotate_with_keywords  # noqa: E402
from src.notify import _embed_for_job  # noqa: E402
from src.scoring import rank_jobs  # noqa: E402

DIGEST_WEBHOOK = os.getenv("DISCORD_DIGEST_WEBHOOK_URL", "").strip()


def _resolve_webhook() -> str:
    """Pick the digest webhook (digest > review > main)."""
    if DIGEST_WEBHOOK:
        return DIGEST_WEBHOOK
    if (DISCORD_REVIEW_WEBHOOK_URL or "").strip():
        return DISCORD_REVIEW_WEBHOOK_URL.strip()
    return (DISCORD_WEBHOOK_URL or "").strip()


def _post_chunks(url: str, embeds: list[dict], header: str) -> bool:
    try:
        import requests  # local import — keep startup cheap
    except ImportError:
        return False
    if not embeds:
        try:
            requests.post(url, json={"content": header}, timeout=10).raise_for_status()
            return True
        except Exception:
            return False
    # First message includes the header; subsequent batches embeds-only.
    for i in range(0, len(embeds), 10):
        chunk = embeds[i : i + 10]
        payload = {"content": header if i == 0 else None, "embeds": chunk}
        try:
            r = requests.post(url, json=payload, timeout=10)
            r.raise_for_status()
        except Exception as e:
            print(f"[daily_digest] post failed: {e}")
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Post top-K unapplied job digest to Discord.")
    parser.add_argument("--hours", type=int, default=24, help="Look back N hours (default: 24)")
    parser.add_argument("--top", type=int, default=20, help="Max jobs to include (default: 20)")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout instead of posting")
    args = parser.parse_args()

    init_db()
    filters = load_filters()

    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    rows = get_new_jobs_since(since, exclude_handled=True)
    if not rows:
        print(f"[daily_digest] no new jobs in last {args.hours}h")
        return 0

    passed = filter_jobs(
        rows,
        locations=filters["locations"],
        level_keywords=filters["level_keywords"],
        title_keywords=filters["title_keywords"],
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
        max_yoe_accept=int(filters.get("max_yoe_accept", 3)),
    )
    ranked = rank_jobs(passed, location_priority=filters.get("location_priority"))
    annotate_with_keywords(ranked)
    top = ranked[: max(1, int(args.top))]

    header = (
        f"Daily digest: top {len(top)} unapplied jobs (last {args.hours}h)"
        f" | candidate pool: {len(passed)} of {len(rows)} new rows"
    )

    if args.dry_run:
        print(header)
        for j in top:
            kws = ", ".join(j.get("_keywords") or [])
            print(
                f"  [{int(j.get('_score', 0)):>3}] {j.get('company_name')} | "
                f"{j.get('title')} | {j.get('location') or '—'}"
                + (f" | {kws}" if kws else "")
            )
            print(f"        {j.get('url')}")
        return 0

    url = _resolve_webhook()
    if not url:
        print("[daily_digest] no webhook configured; set DISCORD_DIGEST_WEBHOOK_URL")
        return 1
    embeds = [_embed_for_job(j) for j in top]
    ok = _post_chunks(url, embeds, header)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
