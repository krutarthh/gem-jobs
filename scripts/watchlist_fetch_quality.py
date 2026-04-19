#!/usr/bin/env python3
"""
Fetch job counts for every watchlist company using the same ATS resolution + fetch
path as the scraper (src.main). Use for CI or local quality checks.

Run from repo root:
  python scripts/watchlist_fetch_quality.py
  python scripts/watchlist_fetch_quality.py --json
  python scripts/watchlist_fetch_quality.py --save-baseline baseline.json
  python scripts/watchlist_fetch_quality.py --baseline baseline.json --min-jobs 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ats import fetch_jobs_for_company  # noqa: E402
from src.ats.resolve import resolve_ats_for_entry  # noqa: E402
from src.config import load_watchlist  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-company job fetch counts (scraper parity)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")
    parser.add_argument(
        "--save-baseline",
        metavar="PATH",
        help="Write the current per-company counts to PATH as JSON (use for future regression checks)",
    )
    parser.add_argument(
        "--baseline",
        metavar="PATH",
        help="Compare counts against a previously saved baseline JSON file",
    )
    parser.add_argument(
        "--min-jobs",
        type=int,
        default=0,
        help=(
            "Regression threshold: non-zero exit if any company present in --baseline with "
            ">= N jobs now returns 0. Requires --baseline. (default 0 = disabled)"
        ),
    )
    args = parser.parse_args()

    companies = load_watchlist()
    rows: list[dict] = []
    errors: list[str] = []
    zero: list[str] = []

    for entry in companies:
        name = entry.get("name") or "?"
        url = (entry.get("careers_url") or "").strip()
        if not url:
            rows.append(
                {
                    "name": name,
                    "jobs": None,
                    "ats_type": None,
                    "board_id": None,
                    "status": "skip",
                    "note": "no careers_url",
                }
            )
            continue
        try:
            ats_type, board_id = resolve_ats_for_entry(entry)
            jobs = fetch_jobs_for_company(ats_type or "generic", board_id, url)
            n = len(jobs)
            note = ""
            if n == 0:
                zero.append(name)
                if (ats_type or "") == "generic" or not board_id:
                    note = "0 jobs (generic/unknown ATS — page may be JS-only or empty)"
                else:
                    note = "0 jobs (board may have no open roles or API issue)"
            rows.append(
                {
                    "name": name,
                    "jobs": n,
                    "ats_type": ats_type,
                    "board_id": board_id,
                    "status": "ok" if n > 0 else "warn",
                    "note": note,
                }
            )
        except Exception as e:
            errors.append(f"{name}: {e}")
            rows.append(
                {
                    "name": name,
                    "jobs": None,
                    "ats_type": entry.get("ats_type"),
                    "board_id": entry.get("board_id"),
                    "status": "error",
                    "note": str(e),
                }
            )

    with_job_count = sum(1 for r in rows if isinstance(r.get("jobs"), int))
    ok_count = sum(1 for r in rows if r.get("status") == "ok")
    warn_count = sum(1 for r in rows if r.get("status") == "warn")
    err_count = sum(1 for r in rows if r.get("status") == "error")
    skip_count = sum(1 for r in rows if r.get("status") == "skip")

    if args.json:
        print(
            json.dumps(
                {
                    "companies": len(companies),
                    "with_job_count": with_job_count,
                    "with_jobs_gt_zero": ok_count,
                    "with_zero_jobs": warn_count,
                    "errors": err_count,
                    "skipped_no_url": skip_count,
                    "rows": rows,
                    "error_messages": errors,
                },
                indent=2,
            )
        )
        return 1 if err_count else 0

    w = max(len(r["name"]) for r in rows) if rows else 40
    print("Watchlist fetch quality (same resolution + fetch as python -m src.main)\n" + "=" * (w + 55))
    print(f"{'Company':<{w}}  {'Jobs':>6}  {'ATS':<12}  board_id / note")
    print("-" * (w + 55))
    for r in rows:
        ats = (r.get("ats_type") or "—")[:12]
        bid = (str(r.get("board_id") or "—"))[:40]
        if r["status"] == "skip":
            jobs_s = "—"
            extra = f"(no URL)"
        elif r["status"] == "error":
            jobs_s = "ERR"
            extra = r.get("note", "")[:60]
        else:
            jobs_s = str(r.get("jobs", 0))
            extra = bid if r.get("jobs") else (r.get("note") or bid)[:60]
        print(f"{r['name']:<{w}}  {jobs_s:>6}  {ats:<12}  {extra}")
    print("=" * (w + 55))
    print(f"Total rows: {len(rows)} | jobs>0: {ok_count} | zero jobs: {warn_count} | errors: {err_count} | no URL: {skip_count}")
    if errors:
        print("\nExceptions:")
        for e in errors:
            print(f"  {e}")
    if zero and not args.json:
        print(f"\nCompanies with 0 jobs ({len(zero)}): {', '.join(zero[:20])}" + (" …" if len(zero) > 20 else ""))

    current_counts = {r["name"]: r.get("jobs") for r in rows if isinstance(r.get("jobs"), int)}

    if args.save_baseline:
        try:
            with open(args.save_baseline, "w") as f:
                json.dump({"counts": current_counts}, f, indent=2, sort_keys=True)
            print(f"\nBaseline written to {args.save_baseline} ({len(current_counts)} companies)")
        except OSError as e:
            print(f"\n[warn] could not write baseline: {e}")

    regressions: list[str] = []
    if args.baseline:
        try:
            with open(args.baseline, "r") as f:
                base = json.load(f)
            baseline_counts = base.get("counts") or {}
        except (OSError, ValueError) as e:
            print(f"\n[warn] could not read baseline {args.baseline}: {e}")
            baseline_counts = {}
        threshold = max(1, int(args.min_jobs or 0))
        for name, old in baseline_counts.items():
            if not isinstance(old, int) or old < threshold:
                continue
            new = current_counts.get(name)
            if new is None or new == 0:
                regressions.append(f"  {name}: {old} -> {new if new is not None else 'missing'}")
        if regressions:
            print(f"\nRegressions against baseline (>= {threshold} jobs dropped to 0):")
            for line in regressions:
                print(line)

    if regressions and args.min_jobs > 0:
        return 2
    return 1 if err_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
