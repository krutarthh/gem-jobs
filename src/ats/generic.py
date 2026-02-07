"""Fallback: scrape job links and titles from unknown career pages (requests + BS4)."""

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

TIMEOUT = 15

JobDict = dict[str, Any]

# Common selectors for job listing links (anchor or div with link)
# Many sites use data-attributes or classes like job-title, role, open-position
LINK_PATTERNS = [
    re.compile(r"job", re.I),
    re.compile(r"position", re.I),
    re.compile(r"role", re.I),
    re.compile(r"career", re.I),
    re.compile(r"opening", re.I),
]


def fetch_jobs(careers_url: str) -> list[JobDict]:
    """
    Best-effort scrape of job links and titles from a career page.
    Returns normalized list; may be empty or incomplete for SPAs.
    """
    try:
        r = requests.get(careers_url, timeout=TIMEOUT, headers={"User-Agent": "GoldGemJobs/1.0"})
        r.raise_for_status()
        html = r.text
    except requests.RequestException:
        return []
    soup = BeautifulSoup(html, "html.parser")
    base = careers_url
    seen: set[str] = set()
    out: list[JobDict] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith("#") or href in seen:
            continue
        full_url = urljoin(base, href)
        text = (a.get_text() or "").strip()
        # Heuristic: link looks like a job (path or text)
        path_lower = urlparse(full_url).path.lower()
        text_lower = text.lower()
        if not any(p.search(path_lower) or p.search(text_lower) for p in LINK_PATTERNS):
            continue
        # Avoid external sites and common non-job links
        if "linkedin.com" in full_url or "indeed.com" in full_url or "glassdoor" in full_url:
            continue
        if len(text) < 3 or len(text) > 200:
            continue
        seen.add(href)
        # Use path or a hash as external_id for deduplication
        external_id = full_url.split("?")[0].rstrip("/") or full_url
        out.append({
            "id": external_id,
            "title": text or None,
            "location": None,
            "department": None,
            "url": full_url,
            "posted_at": None,
        })
    return out
