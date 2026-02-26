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
            # Multi-location postings: location can be list of str or list of dicts
            if isinstance(location, list):
                parts = []
                for x in location:
                    if isinstance(x, dict):
                        p = x.get("name") or x.get("location") or x.get("value")
                        if p is not None and str(p).strip():
                            parts.append(str(p).strip())
                    elif x is not None and str(x).strip():
                        parts.append(str(x).strip())
                # Dedupe by normalized form (first occurrence wins)
                seen_lev: set[str] = set()
                unique = []
                for p in parts:
                    if not p:
                        continue
                    k = p.lower().strip()
                    if k not in seen_lev:
                        seen_lev.add(k)
                        unique.append(p)
                location = " | ".join(unique) if unique else None
            department = cats.get("department")
        else:
            location = department = None
        url = j.get("hostedUrl") or j.get("applyUrl")
        raw_id = j.get("id")
        out.append({
            "id": str(raw_id) if raw_id is not None else url,
            "title": j.get("text"),
            "location": location,
            "department": department,
            "url": url,
            "posted_at": j.get("createdAt"),
        })
    return out
