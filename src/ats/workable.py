"""Fetch jobs from Workable boards.

Workable's public endpoints are heavily JS-rendered, and their JSON API requires
a per-tenant ``shortcode`` (not exposed on apply.workable.com). For the small set
of Workable boards on the watchlist we use the SPA-rendering fetcher, falling back
to the generic HTML scraper. ``board_id`` here is just the Workable slug
(e.g. ``automattic``), and we build the canonical apply URL.
"""

from __future__ import annotations

from typing import Any

from src.ats.generic import fetch_jobs as generic_fetch
from src.ats.spa_lightpanda import fetch_jobs as spa_fetch

JobDict = dict[str, Any]


def _board_url(slug: str) -> str:
    return f"https://apply.workable.com/{slug.strip('/')}/"


def fetch_jobs(slug: str) -> list[JobDict]:
    s = (slug or "").strip().strip("/")
    if not s:
        return []
    url = _board_url(s)
    jobs = spa_fetch(url)
    if jobs:
        return jobs
    return generic_fetch(url)
