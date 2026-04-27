#!/usr/bin/env python3
"""
Mark jobs in the local SQLite DB as applied / dismissed / annotated, so the
scraper stops re-alerting on them.

Examples:
  python scripts/track.py applied https://example.com/jobs/123
  python scripts/track.py dismissed https://example.com/jobs/123
  python scripts/track.py note https://example.com/jobs/123 "Reached out via referral"
  python scripts/track.py applied --bulk < urls.txt   # one URL per line
  python scripts/track.py list --applied              # show applied jobs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.db import _conn, init_db, mark_job  # noqa: E402


def _read_urls_from_args_or_stdin(urls: list[str], use_stdin: bool) -> list[str]:
    if use_stdin:
        return [line.strip() for line in sys.stdin if line.strip()]
    return [u for u in urls if u and u.strip()]


def _cmd_applied(args: argparse.Namespace) -> int:
    init_db()
    urls = _read_urls_from_args_or_stdin(args.urls, args.bulk)
    if not urls:
        print("No URLs provided.")
        return 1
    ok = miss = 0
    for u in urls:
        rid = mark_job(url=u, applied=True)
        if rid > 0:
            ok += 1
            print(f"  applied: {u}")
        else:
            miss += 1
            print(f"  not found: {u}")
    print(f"\n{ok} marked applied, {miss} not found.")
    return 0 if miss == 0 else 2


def _cmd_dismissed(args: argparse.Namespace) -> int:
    init_db()
    urls = _read_urls_from_args_or_stdin(args.urls, args.bulk)
    if not urls:
        print("No URLs provided.")
        return 1
    ok = miss = 0
    for u in urls:
        rid = mark_job(url=u, dismissed=True)
        if rid > 0:
            ok += 1
            print(f"  dismissed: {u}")
        else:
            miss += 1
            print(f"  not found: {u}")
    print(f"\n{ok} dismissed, {miss} not found.")
    return 0 if miss == 0 else 2


def _cmd_note(args: argparse.Namespace) -> int:
    init_db()
    rid = mark_job(url=args.url, note=args.text)
    if rid <= 0:
        print(f"  not found: {args.url}")
        return 2
    print(f"  noted: {args.url}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    init_db()
    where = []
    if args.applied:
        where.append("j.applied_at IS NOT NULL")
    if args.dismissed:
        where.append("j.dismissed_at IS NOT NULL")
    if not where:
        where.append("j.applied_at IS NOT NULL")
    sql = (
        "SELECT j.applied_at, j.dismissed_at, j.title, j.url, c.name AS company_name "
        "FROM jobs j JOIN companies c ON c.id = j.company_id "
        "WHERE " + " OR ".join(where) + " "
        "ORDER BY COALESCE(j.applied_at, j.dismissed_at) DESC LIMIT ?"
    )
    with _conn() as c:
        rows = c.execute(sql, (args.limit,)).fetchall()
    if not rows:
        print("(no rows)")
        return 0
    for r in rows:
        when = (r["applied_at"] or r["dismissed_at"] or "")[:19]
        tag = "applied" if r["applied_at"] else "dismissed"
        print(f"{when}  [{tag}]  {r['company_name']} | {r['title']}\n    {r['url']}")
    return 0


def _cmd_clear(args: argparse.Namespace) -> int:
    init_db()
    rid = mark_job(
        url=args.url,
        applied=args.applied,
        dismissed=args.dismissed,
        note="" if args.note else None,
        clear=True,
    )
    if rid <= 0:
        print(f"  not found: {args.url}")
        return 2
    print(f"  cleared: {args.url}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark jobs applied / dismissed / annotated.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_app = sub.add_parser("applied", help="Mark one or more URLs as applied.")
    p_app.add_argument("urls", nargs="*", help="Job URL(s).")
    p_app.add_argument("--bulk", action="store_true", help="Read URLs from stdin (one per line).")
    p_app.set_defaults(func=_cmd_applied)

    p_dis = sub.add_parser("dismissed", help="Mark one or more URLs as dismissed (won't re-alert).")
    p_dis.add_argument("urls", nargs="*", help="Job URL(s).")
    p_dis.add_argument("--bulk", action="store_true", help="Read URLs from stdin (one per line).")
    p_dis.set_defaults(func=_cmd_dismissed)

    p_note = sub.add_parser("note", help="Attach a free-form note to a job by URL.")
    p_note.add_argument("url")
    p_note.add_argument("text")
    p_note.set_defaults(func=_cmd_note)

    p_list = sub.add_parser("list", help="List recent applied/dismissed jobs.")
    p_list.add_argument("--applied", action="store_true")
    p_list.add_argument("--dismissed", action="store_true")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=_cmd_list)

    p_clear = sub.add_parser("clear", help="Unmark applied/dismissed/note for a URL.")
    p_clear.add_argument("url")
    p_clear.add_argument("--applied", action="store_true")
    p_clear.add_argument("--dismissed", action="store_true")
    p_clear.add_argument("--note", action="store_true")
    p_clear.set_defaults(func=_cmd_clear)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
