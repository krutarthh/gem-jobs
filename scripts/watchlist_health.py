#!/usr/bin/env python3
"""
One-line per-company health summary: live job count + days since the last new
posting was first seen. Helps spot boards that have gone stale.

Usage:
  python scripts/watchlist_health.py
  python scripts/watchlist_health.py --json
  python scripts/watchlist_health.py --stale-days 30
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ats import fetch_jobs_for_company  # noqa: E402
from src.ats.resolve import resolve_ats_for_entry  # noqa: E402
from src.config import load_watchlist  # noqa: E402
from src.db import _conn, init_db  # noqa: E402


def _last_seen_per_company() -> dict[str, str]:
    init_db()
    with _conn() as c:
        rows = c.execute(
            """
            SELECT c.name AS name, MAX(j.first_seen_at) AS last_seen
            FROM companies c
            LEFT JOIN jobs j ON j.company_id = c.id
            GROUP BY c.name
            """
        ).fetchall()
    return {r["name"]: r["last_seen"] for r in rows if r["last_seen"]}


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - dt).days)


def main() -> int:
    parser = argparse.ArgumentParser(description="Watchlist health summary.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=30,
        help="Flag companies with no new postings seen in this many days (default: 30)",
    )
    args = parser.parse_args()

    last_seen = _last_seen_per_company()
    rows: list[dict] = []
    stale: list[str] = []

    for entry in load_watchlist():
        name = entry.get("name") or "?"
        url = (entry.get("careers_url") or "").strip()
        if not url:
            rows.append({"name": name, "jobs": None, "ats": None, "days_since_last_seen": None, "status": "skip"})
            continue
        try:
            ats_type, board_id = resolve_ats_for_entry(entry)
            jobs = fetch_jobs_for_company(ats_type or "generic", board_id, url)
        except Exception as e:
            rows.append({"name": name, "jobs": None, "ats": ats_type, "days_since_last_seen": None, "status": "error", "note": str(e)[:80]})
            continue
        days = _days_since(last_seen.get(name))
        status = "ok"
        if not jobs:
            status = "warn_zero"
        elif days is not None and days >= args.stale_days:
            status = "warn_stale"
            stale.append(name)
        rows.append({
            "name": name,
            "jobs": len(jobs),
            "ats": ats_type,
            "board_id": board_id,
            "days_since_last_seen": days,
            "status": status,
        })

    if args.json:
        print(json.dumps({"rows": rows, "stale": stale}, indent=2))
        return 0

    name_w = max((len(r["name"]) for r in rows), default=20)
    print(f"{'Company':<{name_w}}  {'Jobs':>5}  {'Days':>5}  ATS / status")
    print("-" * (name_w + 35))
    for r in rows:
        jobs_s = str(r.get("jobs") if r.get("jobs") is not None else "—")
        days_s = str(r.get("days_since_last_seen") if r.get("days_since_last_seen") is not None else "—")
        ats_s = (r.get("ats") or "—")[:14]
        tag = "" if r["status"] == "ok" else f" [{r['status']}]"
        print(f"{r['name']:<{name_w}}  {jobs_s:>5}  {days_s:>5}  {ats_s}{tag}")
    print("-" * (name_w + 35))
    print(f"Companies: {len(rows)} | stale (>={args.stale_days}d): {len(stale)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
