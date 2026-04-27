"""Fetch jobs from Recruitee public offers feed.

Endpoint: ``https://<slug>.recruitee.com/api/offers/`` returns
``{"offers": [{"id": ..., "title": ..., ...}]}``. Empty list / error → no jobs.
"""

from __future__ import annotations

from typing import Any

import requests

TIMEOUT = 20

JobDict = dict[str, Any]


def _location_string(o: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for key in ("city", "state_code", "country"):
        v = o.get(key)
        if v and str(v).strip():
            parts.append(str(v).strip())
    if not parts:
        return None
    return ", ".join(parts)


def fetch_jobs(slug: str) -> list[JobDict]:
    s = (slug or "").strip().strip("/")
    if not s:
        return []
    url = f"https://{s}.recruitee.com/api/offers/"
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "GoldGemJobs/1.0", "Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return []
    offers = data.get("offers") if isinstance(data, dict) else None
    if not isinstance(offers, list):
        return []
    out: list[JobDict] = []
    for o in offers:
        if not isinstance(o, dict):
            continue
        oid = o.get("id")
        if oid is None:
            continue
        external_id = str(oid)
        title = o.get("title") or o.get("position")
        url_apply = (
            o.get("careers_apply_url")
            or o.get("careers_url")
            or o.get("public_url")
            or o.get("url")
        )
        department = None
        d = o.get("department")
        if isinstance(d, dict):
            department = d.get("name") or d.get("title")
        elif isinstance(d, str):
            department = d
        out.append({
            "id": external_id,
            "title": title,
            "location": _location_string(o),
            "department": department,
            "url": url_apply,
            "posted_at": o.get("published_at") or o.get("created_at"),
            "description": o.get("description") if isinstance(o.get("description"), str) else None,
        })
    return out
