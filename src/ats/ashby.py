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
        # Ashby job shape: id, title, location, department, etc.
        loc = j.get("location") or j.get("locationName")
        if isinstance(loc, dict):
            loc = loc.get("name") or loc.get("value")
        out.append({
            "id": j.get("id"),
            "title": j.get("title"),
            "location": loc,
            "department": j.get("department"),
            "url": j.get("url") or j.get("applicationUrl") or j.get("jobUrl"),
            "posted_at": j.get("publishedAt") or j.get("createdAt"),
        })
    return out
