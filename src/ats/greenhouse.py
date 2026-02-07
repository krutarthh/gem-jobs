"""Fetch jobs from Greenhouse Job Board API (public JSON)."""

import requests
from typing import Any

TIMEOUT = 15

# Normalized job: id, title, location, department, url, posted_at
JobDict = dict[str, Any]


def fetch_jobs(board_token: str) -> list[JobDict]:
    """
    Fetch all jobs for a Greenhouse board.
    GET https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return []
    jobs = data.get("jobs") or []
    out: list[JobDict] = []
    for j in jobs:
        loc = j.get("location") or {}
        location_name = loc.get("name") if isinstance(loc, dict) else str(loc) if loc else None
        departments = j.get("departments")
        department = None
        if departments and isinstance(departments, list) and len(departments) > 0:
            d = departments[0]
            department = d.get("name") if isinstance(d, dict) else str(d)
        # Prefer first_published for "new" postings; fallback to updated_at
        posted_at = j.get("first_published") or j.get("updated_at")
        out.append({
            "id": str(j.get("id", "")),
            "title": j.get("title"),
            "location": location_name,
            "department": department,
            "url": j.get("absolute_url"),
            "posted_at": posted_at,
        })
    return out
