"""Fetch jobs from SmartRecruiters public API (v1 postings feed)."""

from __future__ import annotations

from typing import Any

import requests

TIMEOUT = 20
PAGE_LIMIT = 100
MAX_PAGES = 30  # cap at 3000 jobs; typical corporate boards are far smaller

JobDict = dict[str, Any]


def _location_string(loc: Any) -> str | None:
    if not isinstance(loc, dict):
        return None
    full = (loc.get("fullLocation") or "").strip()
    if full:
        return full
    parts = [str(loc.get(k, "")).strip() for k in ("city", "region", "country") if loc.get(k)]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


def fetch_jobs(company_slug: str) -> list[JobDict]:
    """Page through `api.smartrecruiters.com/v1/companies/<slug>/postings`."""
    slug = (company_slug or "").strip().strip("/")
    if not slug:
        return []
    out: list[JobDict] = []
    seen: set[str] = set()
    offset = 0
    for _ in range(MAX_PAGES):
        url = (
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
            f"?limit={PAGE_LIMIT}&offset={offset}"
        )
        try:
            r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "GoldGemJobs/1.0"})
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError):
            break
        postings = data.get("content") or []
        if not postings:
            break
        for j in postings:
            posting_id = str(j.get("id") or j.get("uuid") or "")
            if not posting_id or posting_id in seen:
                continue
            seen.add(posting_id)
            ref = j.get("ref") or ""
            apply_url = (
                j.get("applyUrl")
                or (f"https://jobs.smartrecruiters.com/{slug}/{posting_id}" if posting_id else None)
            )
            title = j.get("name") or j.get("title")
            dept = None
            d = j.get("department")
            if isinstance(d, dict):
                dept = d.get("label") or d.get("name")
            elif isinstance(d, str):
                dept = d
            posted_at = j.get("releasedDate") or j.get("createdOn") or j.get("postingDate")
            out.append({
                "id": posting_id,
                "title": title,
                "location": _location_string(j.get("location")),
                "department": dept,
                "url": apply_url or ref,
                "posted_at": posted_at,
                "description": None,
            })
        total = data.get("totalFound") or 0
        offset += PAGE_LIMIT
        if offset >= total:
            break
    return out
