"""Best-effort iCIMS HTML scraper.

iCIMS is a hosted ATS where each tenant runs at a custom subdomain like
``careers-<tenant>.icims.com``. They expose a server-rendered search page at
``/jobs/search?ss=1&pr=<page>`` that contains anchor tags pointing at
``/jobs/<id>/<slug>/job``. We page until no new job IDs appear.

``board_id`` may be either:
  * a bare slug (e.g. ``crowdstrike``) -> treated as ``careers-<slug>.icims.com``
  * a full hostname (e.g. ``careers.scotiabank.com``) -> used as-is
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

TIMEOUT = 20
MAX_PAGES = 25  # cap pages traversed (~ several hundred jobs)

JobDict = dict[str, Any]

_JOB_PATH_RE = re.compile(r"/jobs/(\d+)/", re.I)


def _resolve_base(board_id: str) -> str:
    s = (board_id or "").strip().strip("/")
    if not s:
        return ""
    if s.startswith("http://") or s.startswith("https://"):
        return s.rstrip("/")
    if "icims.com" in s:
        return f"https://{s.rstrip('/')}"
    # Treat as slug; default to the canonical careers- prefix used by most boards.
    return f"https://careers-{s}.icims.com"


def fetch_jobs(board_id: str) -> list[JobDict]:
    base = _resolve_base(board_id)
    if not base:
        return []
    headers = {"User-Agent": "Mozilla/5.0 GoldGemJobs/1.0"}
    out: list[JobDict] = []
    seen_ids: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        url = f"{base}/jobs/search?ss=1&pr={page}"
        try:
            r = requests.get(url, timeout=TIMEOUT, headers=headers, allow_redirects=True)
            r.raise_for_status()
        except requests.RequestException:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        page_count_before = len(seen_ids)
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            m = _JOB_PATH_RE.search(href)
            if not m:
                continue
            job_id = m.group(1)
            if job_id in seen_ids:
                continue
            full_url = urljoin(base + "/", href)
            title = (a.get_text() or "").strip()
            if not title or len(title) < 3:
                continue
            seen_ids.add(job_id)
            out.append({
                "id": job_id,
                "title": title[:200],
                "location": None,
                "department": None,
                "url": full_url,
                "posted_at": None,
                "description": None,
            })
        if len(seen_ids) == page_count_before:
            break  # page returned no new jobs => stop paging.
    return out
