"""Fetch jobs from Greenhouse Job Board API (public JSON)."""

import requests
from typing import Any

TIMEOUT = 15

# Normalized job: id, title, location, department, url, posted_at
JobDict = dict[str, Any]


def fetch_jobs(board_token: str) -> list[JobDict]:
    """
    Fetch all jobs for a Greenhouse board.
    Uses content=true to get offices array so we include every location (multi-location jobs).
    GET https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs?content=true
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return []
    jobs = data.get("jobs") or []
    out: list[JobDict] = []
    for j in jobs:
        # Merge all locations: main location + every office (name + location) for multi-location jobs
        location_parts: list[str] = []
        loc = j.get("location") or {}
        if isinstance(loc, dict) and loc.get("name"):
            location_parts.append(str(loc["name"]).strip())
        elif loc and not isinstance(loc, dict):
            location_parts.append(str(loc).strip())
        for office in j.get("offices") or []:
            if not isinstance(office, dict):
                continue
            if office.get("name"):
                location_parts.append(str(office["name"]).strip())
            if office.get("location"):
                location_parts.append(str(office["location"]).strip())
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
        location_name = " | ".join(unique) or None
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
