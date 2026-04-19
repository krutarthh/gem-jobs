"""Fetch jobs from Workday CXS public search API.

board_id packs (tenant, site, wdN) so the dispatcher can call the right host.
Format: "<tenant>|<site>|wd<N>"   e.g. "crowdstrike|crowdstrikecareers|wd5"
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

TIMEOUT = 20
PAGE_LIMIT = 20  # Workday caps at 20 per request
MAX_PAGES = 50   # hard safety cap -> up to 1000 jobs

JobDict = dict[str, Any]

_RELATIVE_DAYS_RE = re.compile(r"(\d+)\s+day", re.I)
_POSTED_TODAY_RE = re.compile(r"posted\s+today", re.I)
_POSTED_YESTERDAY_RE = re.compile(r"yesterday", re.I)
_POSTED_30_PLUS_RE = re.compile(r"30\+\s+day", re.I)


def _parse_board_id(board_id: str) -> tuple[str, str, str] | None:
    """Split "tenant|site|wdN" into its parts. Returns None if invalid."""
    if not board_id or "|" not in board_id:
        return None
    parts = [p.strip() for p in board_id.split("|")]
    if len(parts) != 3:
        return None
    tenant, site, wd = parts
    if not tenant or not site or not wd:
        return None
    if not wd.startswith("wd"):
        return None
    return tenant, site, wd


def _relative_to_iso(posted_on: str | None) -> str | None:
    """Workday returns relative strings like "Posted 6 Days Ago". Convert to ISO date."""
    if not posted_on or not isinstance(posted_on, str):
        return None
    text = posted_on.strip()
    now = datetime.now(timezone.utc)
    if _POSTED_TODAY_RE.search(text):
        return now.date().isoformat()
    if _POSTED_YESTERDAY_RE.search(text):
        return (now - timedelta(days=1)).date().isoformat()
    if _POSTED_30_PLUS_RE.search(text):
        return (now - timedelta(days=30)).date().isoformat()
    m = _RELATIVE_DAYS_RE.search(text)
    if m:
        try:
            days = int(m.group(1))
            return (now - timedelta(days=days)).date().isoformat()
        except ValueError:
            return None
    return None


def fetch_jobs(board_id: str) -> list[JobDict]:
    """Page through Workday CXS search endpoint and normalize results."""
    parts = _parse_board_id(board_id)
    if parts is None:
        return []
    tenant, site, wd = parts
    host = f"https://{tenant}.{wd}.myworkdayjobs.com"
    endpoint = f"{host}/wday/cxs/{tenant}/{site}/jobs"
    job_url_base = f"{host}/en-US/{site}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "GoldGemJobs/1.0",
    }

    out: list[JobDict] = []
    seen_ids: set[str] = set()
    offset = 0
    for _ in range(MAX_PAGES):
        payload = {
            "appliedFacets": {},
            "limit": PAGE_LIMIT,
            "offset": offset,
            "searchText": "",
        }
        try:
            r = requests.post(endpoint, json=payload, headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError):
            break
        postings = data.get("jobPostings") or []
        if not postings:
            break
        for j in postings:
            ext = (j.get("externalPath") or "").strip()
            if not ext:
                continue
            ext_id = ext.rstrip("/").split("/")[-1] or ext
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)
            url = f"{job_url_base}{ext}" if ext.startswith("/") else f"{job_url_base}/{ext}"
            posted_at = _relative_to_iso(j.get("postedOn"))
            out.append({
                "id": ext_id,
                "title": j.get("title"),
                "location": j.get("locationsText"),
                "department": None,
                "url": url,
                "posted_at": posted_at,
                "description": None,
            })
        offset += PAGE_LIMIT
        # Some Workday instances return total only on the first page; stop when a page is short.
        if len(postings) < PAGE_LIMIT:
            break
    return out
