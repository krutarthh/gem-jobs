"""Resolve ATS type and board_id for a watchlist row (same rules as the scraper)."""

from __future__ import annotations

from typing import Any

import requests

from src.ats.detector import detect_ats, detect_ats_from_html

REQUEST_TIMEOUT = 10
_HEADERS = {"User-Agent": "GoldGemJobs/1.0"}


def _resolve_redirect(url: str) -> str:
    try:
        r = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            headers=_HEADERS,
        )
        return r.url
    except requests.RequestException:
        return url


def resolve_ats_for_entry(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Return (ats_type, board_id) for a watchlist company dict.
    Mirrors src.main.run_once so diagnostics and scraper stay aligned.
    """
    careers_url = (entry.get("careers_url") or "").strip()
    if not careers_url:
        return None, None
    ats_type = entry.get("ats_type")
    board_id = entry.get("board_id")
    if not ats_type or not board_id:
        final_url = _resolve_redirect(careers_url)
        ats_type, board_id = detect_ats(final_url)
        if not board_id and ats_type != "generic":
            ats_type, board_id = detect_ats(careers_url)
        if ats_type == "generic" or not board_id:
            try:
                r = requests.get(
                    careers_url,
                    timeout=REQUEST_TIMEOUT,
                    headers=_HEADERS,
                )
                if r.ok:
                    discovered_type, discovered_id = detect_ats_from_html(r.text)
                    if discovered_id:
                        ats_type, board_id = discovered_type, discovered_id
            except requests.RequestException:
                pass
    return ats_type, board_id
