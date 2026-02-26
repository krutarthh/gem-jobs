"""Fetch jobs from Ashby job board API (public JSON)."""

import requests
from typing import Any

TIMEOUT = 15

JobDict = dict[str, Any]


def fetch_jobs(client_name: str) -> list[JobDict]:
    """
    Fetch all jobs for an Ashby job board.
    GET https://api.ashbyhq.com/posting-api/job-board/<clientname>
    """
    url = f"https://api.ashbyhq.com/posting-api/job-board/{client_name}"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return []
    # Ashby returns { "jobs": [ ... ] } or similar
    jobs = data.get("jobs") if isinstance(data, dict) else []
    if not isinstance(jobs, list):
        return []
    out: list[JobDict] = []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        # Ashby: primary location + secondaryLocations (multi-location jobs)
        loc = j.get("location") or j.get("locationName")
        location_parts: list[str] = []
        if isinstance(loc, list):
            for x in loc:
                if isinstance(x, dict):
                    p = x.get("name") or x.get("location") or x.get("value")
                    if p is not None and str(p).strip():
                        location_parts.append(str(p).strip())
                elif x is not None and str(x).strip():
                    location_parts.append(str(x).strip())
        elif isinstance(loc, dict):
            p = loc.get("name") or loc.get("value")
            if p:
                location_parts.append(str(p).strip())
        elif loc:
            location_parts.append(str(loc).strip())
        for sec in j.get("secondaryLocations") or []:
            if isinstance(sec, dict):
                s = sec.get("location") or sec.get("name") or sec.get("value")
            else:
                s = sec
            if s and str(s).strip():
                location_parts.append(str(s).strip())
        # Dedupe by normalized form (first occurrence wins)
        seen: set[str] = set()
        unique = []
        for p in location_parts:
            if not p:
                continue
            k = p.lower().strip()
            if k not in seen:
                seen.add(k)
                unique.append(p)
        loc = " | ".join(unique) if unique else None
        url = j.get("url") or j.get("applicationUrl") or j.get("jobUrl")
        raw_id = j.get("id")
        out.append({
            "id": str(raw_id) if raw_id is not None else url,
            "title": j.get("title"),
            "location": loc,
            "department": j.get("department"),
            "url": url,
            "posted_at": j.get("publishedAt") or j.get("createdAt"),
        })
    return out
