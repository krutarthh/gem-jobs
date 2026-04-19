"""Fallback scraper for career pages without a dedicated ATS fetcher.

Strategy, in order:
1. Parse JSON-LD ``JobPosting`` entries (``application/ld+json``). Many large
   career portals (Google, Apple, Meta subpages, Workday public boards) embed
   these and they carry title, datePosted, location, description.
2. Fall back to an anchor-link heuristic with a few site-specific cases
   (Google ``/about/careers/applications/jobs/results/``, JazzHR ``/apply/``).

Returns a list of normalized job dicts. May still be empty or partial for
heavy SPAs.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

TIMEOUT = 15

JobDict = dict[str, Any]

LINK_PATTERNS = [
    re.compile(r"job", re.I),
    re.compile(r"position", re.I),
    re.compile(r"role", re.I),
    re.compile(r"career", re.I),
    re.compile(r"opening", re.I),
    # JazzHR / Resumator boards on *.applytojob.com (job links look like /apply/{id}/{slug})
    re.compile(r"/apply/[A-Za-z0-9]+/"),
]


def _looks_like_google_job(parsed_url) -> bool:
    """Google careers detail pages: /about/careers/applications/jobs/results/<numeric-id>-<slug>."""
    host = (parsed_url.netloc or "").lower()
    if "google.com" not in host:
        return False
    path = (parsed_url.path or "").lower()
    marker = "/about/careers/applications/jobs/results/"
    if marker not in path:
        return False
    tail = path.split(marker, 1)[1]
    return bool(tail) and tail[0].isdigit()


def _location_from_jobposting(entry: dict) -> str | None:
    """Extract a flat location string from schema.org JobPosting jobLocation."""
    loc = entry.get("jobLocation")
    if loc is None:
        return None
    items = loc if isinstance(loc, list) else [loc]
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        addr = item.get("address")
        if isinstance(addr, dict):
            chunks = [
                str(addr.get(k) or "").strip()
                for k in ("addressLocality", "addressRegion", "addressCountry")
                if addr.get(k)
            ]
            joined = ", ".join([c for c in chunks if c])
            if joined:
                parts.append(joined)
        elif isinstance(addr, str) and addr.strip():
            parts.append(addr.strip())
    if not parts:
        applicant = entry.get("applicantLocationRequirements")
        if isinstance(applicant, dict):
            nm = (applicant.get("name") or "").strip()
            if nm:
                parts.append(nm)
        elif isinstance(applicant, list):
            for a in applicant:
                if isinstance(a, dict) and a.get("name"):
                    parts.append(str(a["name"]).strip())
    # Dedupe, join
    seen: set[str] = set()
    deduped: list[str] = []
    for p in parts:
        k = p.lower()
        if p and k not in seen:
            seen.add(k)
            deduped.append(p)
    return " | ".join(deduped) or None


def _iter_jsonld_blocks(soup: BeautifulSoup) -> Iterable[Any]:
    """Yield every parsed JSON-LD block (``<script type="application/ld+json">``)."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        # Some pages concatenate multiple objects; try loads then fall back.
        try:
            yield json.loads(raw)
            continue
        except (ValueError, TypeError):
            pass
        # Strip HTML comments sometimes wrapped around JSON-LD.
        cleaned = re.sub(r"<!--.*?-->", "", raw, flags=re.S).strip()
        if cleaned:
            try:
                yield json.loads(cleaned)
            except (ValueError, TypeError):
                continue


def _flatten_jsonld(node: Any) -> Iterable[dict]:
    """Yield every dict in a possibly nested JSON-LD tree."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _flatten_jsonld(v)
    elif isinstance(node, list):
        for item in node:
            yield from _flatten_jsonld(item)


def _extract_jsonld_jobs(html: str, base_url: str) -> list[JobDict]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[JobDict] = []
    seen_urls: set[str] = set()
    for block in _iter_jsonld_blocks(soup):
        for entry in _flatten_jsonld(block):
            t = entry.get("@type")
            if isinstance(t, list):
                is_job = any(str(x).lower() == "jobposting" for x in t)
            else:
                is_job = isinstance(t, str) and t.lower() == "jobposting"
            if not is_job:
                continue
            title = entry.get("title") or entry.get("name")
            url = entry.get("url") or entry.get("sameAs")
            if isinstance(url, list):
                url = next((u for u in url if isinstance(u, str)), None)
            if isinstance(url, str):
                url = urljoin(base_url, url.strip())
            ext_id = (
                str(entry.get("identifier", {}).get("value"))
                if isinstance(entry.get("identifier"), dict)
                else str(entry.get("identifier") or url or title or "")
            )
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            hiring = entry.get("hiringOrganization")
            department = None
            if isinstance(entry.get("industry"), str):
                department = entry["industry"]
            found.append({
                "id": (ext_id or url)[:200],
                "title": str(title)[:200],
                "location": _location_from_jobposting(entry),
                "department": department,
                "url": url,
                "posted_at": entry.get("datePosted"),
                "description": entry.get("description") if isinstance(entry.get("description"), str) else None,
            })
    return found


def _extract_link_jobs(html: str, base_url: str) -> list[JobDict]:
    soup = BeautifulSoup(html, "html.parser")
    base_host = (urlparse(base_url).netloc or "").lower()
    is_google_results_board = (
        "google.com" in base_host
        and "/about/careers/applications/jobs/results" in (urlparse(base_url).path or "").lower()
    )
    seen: set[str] = set()
    out: list[JobDict] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith("#") or href in seen:
            continue
        if is_google_results_board and href.startswith("jobs/results/"):
            full_url = urljoin("https://www.google.com/about/careers/applications/", href)
        else:
            full_url = urljoin(base_url, href)
        text = (a.get_text() or "").strip()
        parsed = urlparse(full_url)
        path_norm = parsed.path.rstrip("/").lower()
        if "applytojob.com" in (parsed.netloc or "").lower() and path_norm in ("/apply", ""):
            continue
        path_lower = parsed.path.lower()
        text_lower = text.lower()
        google_job_link = _looks_like_google_job(parsed)
        if is_google_results_board and not google_job_link:
            continue
        if not google_job_link and not any(p.search(path_lower) or p.search(text_lower) for p in LINK_PATTERNS):
            continue
        if "linkedin.com" in full_url or "indeed.com" in full_url or "glassdoor" in full_url:
            continue
        if "info.jazzhr.com" in full_url.lower() or "job-seekers" in path_lower:
            continue
        if google_job_link and len(text) < 3:
            tail = parsed.path.lower().split("/jobs/results/", 1)[1]
            slug = tail.split("-", 1)[1] if "-" in tail else tail
            text = slug.replace("-", " ").strip().title()[:200]
        # Try to pull posted_at from a nearby <time datetime=...> element
        posted_at = None
        time_el = a.find("time") if hasattr(a, "find") else None
        if time_el is None and hasattr(a, "parent") and a.parent is not None:
            time_el = a.parent.find("time")
        if time_el is not None and time_el.get("datetime"):
            posted_at = time_el.get("datetime")
        if len(text) < 3 or len(text) > 200:
            continue
        seen.add(href)
        external_id = full_url.split("?")[0].rstrip("/") or full_url
        out.append({
            "id": external_id,
            "title": text or None,
            "location": None,
            "department": None,
            "url": full_url,
            "posted_at": posted_at,
            "description": None,
        })
    return out


def fetch_jobs(careers_url: str) -> list[JobDict]:
    """Best-effort scrape: JSON-LD first, then anchor heuristics."""
    try:
        r = requests.get(
            careers_url,
            timeout=TIMEOUT,
            headers={"User-Agent": "GoldGemJobs/1.0"},
        )
        r.raise_for_status()
        html = r.text
    except requests.RequestException:
        return []

    jsonld_jobs = _extract_jsonld_jobs(html, careers_url)
    if jsonld_jobs:
        return jsonld_jobs
    return _extract_link_jobs(html, careers_url)
