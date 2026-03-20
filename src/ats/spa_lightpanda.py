"""
Fetch jobs from JS-rendered (SPA) career pages using Lightpanda via CDP.

Use for sites like jobs.rbc.com where the job list is loaded client-side.
Requires: Lightpanda running (./lightpanda serve --port 9222).

Set in watchlist:
  ats_type: spa
  board_id: <full job board URL to scrape, e.g. https://jobs.rbc.com/ca/en/rbc-borealis>
"""

import os
from typing import Any

CDP_URL = os.getenv("LIGHTPANDA_CDP_URL", "http://127.0.0.1:9222")
PAGE_TIMEOUT_MS = 45_000

JobDict = dict[str, Any]


def _extract_jobs_js() -> str:
    """Return JS to run in page context. Extracts job links (Workday-style /job/ID/Title, RBC, etc.)."""
    return """
    () => {
        const jobs = [];
        const seen = new Set();
        const base = window.location.origin;
        const skip = ['facebook','instagram','twitter','youtube','linkedin','privacy','cookie','glassdoor'];
        for (const a of document.querySelectorAll('a[href]')) {
            const href = (a.getAttribute('href') || '').trim();
            if (!href || href.startsWith('#')) continue;
            let full;
            try { full = (a.href || (href.startsWith('http') ? href : new URL(href, base).href)); } catch(e) { continue; }
            if (seen.has(full)) continue;
            const path = (new URL(full).pathname || '').toLowerCase();
            const text = (a.textContent || '').trim().replace(/\\s+/g,' ');
            if (skip.some(s => full.toLowerCase().includes(s))) continue;
            if (path.includes('/job/') && path.split('/').filter(Boolean).length >= 4) {
                seen.add(full);
                jobs.push({ url: full, title: (text && text.length > 2 && text.length < 200) ? text : null });
            }
        }
        return jobs;
    }
    """


def fetch_jobs(job_board_url: str) -> list[JobDict]:
    """
    Use Lightpanda (CDP) to load the job board, let JS render, then extract job links.
    Falls back to empty list if Lightpanda is unavailable.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    url = (job_board_url or "").strip()
    if not url or not url.startswith("http"):
        return []

    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL, timeout=8_000)
        except Exception:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception:
                return []
        try:
            ctx = browser.contexts[0] if browser.contexts else None
            if not ctx:
                ctx = browser.new_context()
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                page.wait_for_load_state("networkidle", timeout=25_000)
                page.wait_for_timeout(2_000)
            except Exception:
                pass
            raw = page.evaluate(_extract_jobs_js())
            page.close()
        finally:
            try:
                browser.close()
            except Exception:
                pass

    out: list[JobDict] = []
    seen_urls: set[str] = set()
    for item in raw or []:
        u = (item.get("url") or "").strip()
        t = (item.get("title") or "").strip()
        if not u or u in seen_urls:
            continue
        if "facebook" in u or "instagram" in u or "twitter" in u or "youtube" in u or "linkedin" in u:
            continue
        if len(t) < 3:
            t = None
        if len(t or "") > 200:
            t = (t or "")[:200]
        seen_urls.add(u)
        ext_id = u.split("?")[0].rstrip("/") or u
        out.append({
            "id": ext_id,
            "title": t or None,
            "location": None,
            "department": None,
            "url": u,
            "posted_at": None,
        })
    return out
