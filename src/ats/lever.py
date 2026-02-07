"""Fetch jobs from Lever Postings API (public JSON)."""

import requests
from typing import Any

TIMEOUT = 15

JobDict = dict[str, Any]


def fetch_jobs(company_slug: str) -> list[JobDict]:
    """
    Fetch all postings for a Lever company.
    GET https://api.lever.co/v0/postings/<company>?mode=json
    """
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return []
    if not isinstance(data, list):
        return []
    out: list[JobDict] = []
    for j in data:
        cats = j.get("categories") or {}
        if isinstance(cats, dict):
            location = cats.get("location")
            department = cats.get("department")
        else:
            location = department = None
        out.append({
            "id": j.get("id"),
            "title": j.get("text"),
            "location": location,
            "department": department,
            "url": j.get("hostedUrl") or j.get("applyUrl"),
            "posted_at": j.get("createdAt"),
        })
    return out
