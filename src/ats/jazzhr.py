"""Fetch jobs from JazzHR / ApplyToJob boards.

JazzHR no longer exposes an RSS/JSON feed on *.applytojob.com, but the board
HTML is predictable: an h2 "Current Openings" followed by alternating h3 blocks
that are either a department name or a job title (with a nearby apply link).

We walk the DOM in order, track the current department, and emit a normalized
job dict for every /apply/<token>/<slug> link.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

TIMEOUT = 20

JobDict = dict[str, Any]

_JOB_PATH_RE = re.compile(r"^/apply/[A-Za-z0-9]+/", re.I)


def _looks_like_job_link(href: str) -> bool:
    if not href:
        return False
    # Accept both absolute and relative URLs.
    path = href
    if href.startswith("http"):
        i = href.find("/apply/")
        path = href[i:] if i >= 0 else ""
    return bool(_JOB_PATH_RE.match(path))


def fetch_jobs(subdomain: str) -> list[JobDict]:
    """Scrape `https://<subdomain>.applytojob.com/apply` for all open roles."""
    sub = (subdomain or "").strip().strip("/")
    if not sub:
        return []
    base = f"https://{sub}.applytojob.com"
    page_url = f"{base}/apply"
    try:
        r = requests.get(page_url, timeout=TIMEOUT, headers={"User-Agent": "GoldGemJobs/1.0"})
        r.raise_for_status()
        html = r.text
    except requests.RequestException:
        return []

    soup = BeautifulSoup(html, "html.parser")

    # Walk all h3 nodes in page order; a h3 is either a department header or a job block.
    # A job block has an <a href="/apply/..."> descendant.
    out: list[JobDict] = []
    seen_urls: set[str] = set()
    current_dept: str | None = None

    for h3 in soup.find_all(["h2", "h3"]):
        text = (h3.get_text() or "").strip()
        if not text or text.lower().startswith("this website uses"):
            continue
        # JazzHR wraps each job title in <h3><a href="/apply/..."> directly; we don't scan
        # outside the heading because department headings and job headings live in separate
        # containers and sibling-scanning leaks across them.
        a = h3.find("a", href=True)
        job_link = a if (a and _looks_like_job_link(a.get("href", ""))) else None
        if job_link is None:
            # Department label or structural heading.
            if h3.name == "h3":
                current_dept = text
            continue

        href = job_link.get("href", "").strip()
        full_url = urljoin(base + "/", href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        ext_id = full_url.split("?")[0].rstrip("/")
        # Try to pick a clean title: prefer the anchor's own text, else the heading's text.
        anchor_text = (job_link.get_text() or "").strip()
        title = anchor_text if len(anchor_text) >= 3 else text
        out.append({
            "id": ext_id,
            "title": title[:200] if title else None,
            "location": None,
            "department": current_dept,
            "url": full_url,
            "posted_at": None,
            "description": None,
        })
    return out
