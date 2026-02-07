"""
Detect ATS (Greenhouse/Lever/Ashby) for each company in the watchlist.
Run: python scripts/detect_ats_for_watchlist.py
Prints which companies have known ATS vs generic, so you can add ats_type/board_id
to the watchlist for reliable job fetching.
"""

import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_watchlist
from src.ats.detector import detect_ats, detect_ats_from_html
from src.ats.greenhouse import fetch_jobs as gh_fetch
from src.ats.lever import fetch_jobs as lever_fetch
from src.ats.ashby import fetch_jobs as ashby_fetch


def main() -> None:
    companies = load_watchlist()
    print("ATS detection for watchlist companies\n" + "=" * 60)
    for entry in companies:
        name = entry.get("name") or "?"
        url = (entry.get("careers_url") or "").strip()
        override_type = entry.get("ats_type")
        override_id = entry.get("board_id")
        if not url:
            print(f"  {name}: (no URL)")
            continue
        if override_type and override_id:
            # Verify API works
            count = 0
            if override_type == "greenhouse":
                count = len(gh_fetch(override_id))
            elif override_type == "lever":
                count = len(lever_fetch(override_id))
            elif override_type == "ashby":
                count = len(ashby_fetch(override_id))
            print(f"  {name}: {override_type} / {override_id} (override, {count} jobs)")
            continue
        # Resolve redirect and detect from URL, then from page HTML
        try:
            r = requests.get(url, timeout=10, allow_redirects=True, headers={"User-Agent": "GoldGemJobs/1.0"})
            final_url = r.url
            html = r.text
        except requests.RequestException:
            final_url = url
            html = ""
        ats_type, board_id = detect_ats(final_url)
        if not board_id and ats_type != "generic":
            ats_type, board_id = detect_ats(url)
        if (ats_type == "generic" or not board_id) and html:
            ats_type, board_id = detect_ats_from_html(html)
        if board_id:
            count = 0
            if ats_type == "greenhouse":
                count = len(gh_fetch(board_id))
            elif ats_type == "lever":
                count = len(lever_fetch(board_id))
            elif ats_type == "ashby":
                count = len(ashby_fetch(board_id))
            print(f"  {name}: {ats_type} / {board_id} (auto, {count} jobs)")
        else:
            print(f"  {name}: generic (add ats_type + board_id to watchlist if you know them)")


if __name__ == "__main__":
    main()
