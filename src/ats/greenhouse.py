"""Fetch jobs from Greenhouse Job Board API (public JSON)."""

import requests
from typing import Any

TIMEOUT = 15

# US + EU public job-board APIs (EU-hosted boards may only appear on the EU host).
_GREENHOUSE_API_BASES = (
    "https://boards-api.greenhouse.io/v1",
    "https://boards.eu.greenhouse.io/v1",
)

# Normalized job: id, title, location, department, url, posted_at
JobDict = dict[str, Any]


def _normalize_job(raw: dict[str, Any]) -> JobDict:
    location_parts: list[str] = []
    loc = raw.get("location") or {}
    if isinstance(loc, dict) and loc.get("name"):
        location_parts.append(str(loc["name"]).strip())
    elif loc and not isinstance(loc, dict):
        location_parts.append(str(loc).strip())
    for office in raw.get("offices") or []:
        if not isinstance(office, dict):
            continue
        if office.get("name"):
            location_parts.append(str(office["name"]).strip())
        if office.get("location"):
            location_parts.append(str(office["location"]).strip())
    seen: set[str] = set()
    unique = []
    for p in location_parts:
        if not p:
            continue
        k = p.lower().strip()
        if k not in seen:
            seen.add(k)
            unique.append(p)
    location_name = " | ".join(unique) or None
    departments = raw.get("departments")
    department = None
    if departments and isinstance(departments, list) and len(departments) > 0:
        d = departments[0]
        department = d.get("name") if isinstance(d, dict) else str(d)
    posted_at = raw.get("first_published") or raw.get("updated_at")
    description = raw.get("content") if isinstance(raw.get("content"), str) else None
    return {
        "id": str(raw.get("id", "")),
        "title": raw.get("title"),
        "location": location_name,
        "department": department,
        "url": raw.get("absolute_url"),
        "posted_at": posted_at,
        "description": description,
    }


def _prefer_job(a: JobDict, b: JobDict) -> JobDict:
    """Pick the richer duplicate when merging US + EU API responses."""
    a_desc = len((a.get("description") or ""))
    b_desc = len((b.get("description") or ""))
    if a_desc != b_desc:
        return a if a_desc > b_desc else b
    a_url = (a.get("url") or "").lower()
    b_url = (b.get("url") or "").lower()
    a_eu = "job-boards.eu.greenhouse.io" in a_url
    b_eu = "job-boards.eu.greenhouse.io" in b_url
    if a_eu and not b_eu:
        return a
    if b_eu and not a_eu:
        return b
    return a


def _fetch_from_base(api_base: str, board_token: str) -> list[JobDict]:
    url = f"{api_base}/boards/{board_token}/jobs?content=true"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return []
    jobs = data.get("jobs") or []
    return [_normalize_job(j) for j in jobs if isinstance(j, dict)]


def fetch_jobs(board_token: str) -> list[JobDict]:
    """
    Fetch all jobs for a Greenhouse board from US and EU public APIs, merged by job id.
    Uses content=true for offices + JD text. EU listings (e.g. job-boards.eu.greenhouse.io)
    are included when either API returns them.
    """
    merged: dict[str, JobDict] = {}
    for base in _GREENHOUSE_API_BASES:
        for job in _fetch_from_base(base, board_token):
            jid = job.get("id")
            if not jid:
                continue
            if jid in merged:
                merged[jid] = _prefer_job(merged[jid], job)
            else:
                merged[jid] = job
    return list(merged.values())
