"""Map career URL to ATS type and board token/slug."""

import re
from urllib.parse import urlparse

# (ats_type, board_id or None if not detectable)
Result = tuple[str, str | None]

# Patterns: (regex, ats_type, group index)
GREENHOUSE_PATTERNS = [
    (re.compile(r"boards\.greenhouse\.io/([^/?\"')\s]+)", re.I), "greenhouse", 1),
    (re.compile(r"boards\.eu\.greenhouse\.io/([^/?\"')\s]+)", re.I), "greenhouse", 1),
    (re.compile(r"job-boards\.greenhouse\.io/([^/?\"')\s]+)", re.I), "greenhouse", 1),
    (re.compile(r"job-boards\.eu\.greenhouse\.io/([^/?\"')\s]+)", re.I), "greenhouse", 1),
    (re.compile(r"jobvite\.com/[^/]+/job/[^/]+/([^/?]+)", re.I), "greenhouse", 1),
    (re.compile(r"greenhouse\.io/[^/]+/([^/?\"')\s]+)", re.I), "greenhouse", 1),
    (re.compile(r"boardToken['\"]?\s*[:=]\s*['\"]([^'\"]+)", re.I), "greenhouse", 1),
]
LEVER_PATTERNS = [
    (re.compile(r"jobs\.lever\.co/([^/?\"')\s]+)", re.I), "lever", 1),
    (re.compile(r"api\.lever\.co/v0/postings/([^/?\"')\s]+)", re.I), "lever", 1),
    (re.compile(r"lever\.co/([^/?\"')\s]+)", re.I), "lever", 1),
]
ASHBY_PATTERNS = [
    (re.compile(r"jobs\.ashbyhq\.com/([^/?\"')\s]+)", re.I), "ashby", 1),
    (re.compile(r"ashbyhq\.com/[^/]+/([^/?\"')\s]+)", re.I), "ashby", 1),
]
# Workday: board_id packs "<tenant>|<site>|wd<N>" so workday.fetch_jobs knows the host.
WORKDAY_RE = re.compile(
    r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z-]{2,5}/)?([^/?\"')\s]+)",
    re.I,
)
# SmartRecruiters: slug comes from public careers subdomain or API base.
SMARTRECRUITERS_PATTERNS = [
    (re.compile(r"careers\.smartrecruiters\.com/([^/?\"')\s]+)", re.I), "smartrecruiters", 1),
    (re.compile(r"jobs\.smartrecruiters\.com/([^/?\"')\s]+)", re.I), "smartrecruiters", 1),
    (re.compile(r"api\.smartrecruiters\.com/v1/companies/([^/?\"')\s]+)/postings", re.I), "smartrecruiters", 1),
]
# JazzHR / applytojob: subdomain is the board id.
JAZZHR_RE = re.compile(r"([a-z0-9-]+)\.applytojob\.com", re.I)
# Workable: apply.workable.com/<slug> or <slug>.workable.com.
WORKABLE_PATTERNS = [
    (re.compile(r"apply\.workable\.com/([a-z0-9-]+)", re.I), "workable", 1),
    (re.compile(r"jobs\.workable\.com/([a-z0-9-]+)", re.I), "workable", 1),
    (re.compile(r"([a-z0-9-]+)\.workable\.com", re.I), "workable", 1),
]
# Recruitee: <slug>.recruitee.com.
RECRUITEE_RE = re.compile(r"([a-z0-9-]+)\.recruitee\.com", re.I)
# iCIMS: jobs-<tenant>.icims.com or careers-<tenant>.icims.com or <tenant>.icims.com.
ICIMS_RE = re.compile(r"(?:careers-|jobs-)?([a-z0-9-]+)\.icims\.com", re.I)


def _detect_workable(text: str) -> Result | None:
    for pattern, ats_type, group in WORKABLE_PATTERNS:
        m = pattern.search(text)
        if m:
            slug = m.group(group).strip("'\"").lower()
            # Skip the marketing host www.workable.com / apply.workable.com themselves.
            if slug in {"www", "apply", "jobs", "api", "static"}:
                continue
            if 1 < len(slug) <= 60:
                return ats_type, slug
    return None


def _detect_recruitee(text: str) -> Result | None:
    m = RECRUITEE_RE.search(text)
    if not m:
        return None
    slug = m.group(1).lower()
    if slug in {"www", "api", "support"} or len(slug) > 60:
        return None
    return "recruitee", slug


def _detect_icims(text: str) -> Result | None:
    m = ICIMS_RE.search(text)
    if not m:
        return None
    slug = m.group(1).lower()
    if slug in {"www", "api", "static", "support"} or len(slug) < 2 or len(slug) > 80:
        return None
    return "icims", slug


def _detect_workday(text: str) -> Result | None:
    m = WORKDAY_RE.search(text)
    if not m:
        return None
    tenant, wd, site = m.group(1), m.group(2).lower(), m.group(3)
    site = site.split("?")[0].rstrip("/")
    if not site or len(site) > 80:
        return None
    return "workday", f"{tenant}|{site}|{wd}"


def _detect_jazzhr(text: str) -> Result | None:
    m = JAZZHR_RE.search(text)
    if not m:
        return None
    sub = m.group(1).lower()
    if sub in {"info", "www", "api"} or len(sub) > 60:
        return None
    return "jazzhr", sub


def detect_ats_from_html(html: str) -> Result:
    """
    Scan page content for ATS links or script config (e.g. Greenhouse embed).
    Return (ats_type, board_id) or ('generic', None).
    """
    if not html:
        return "generic", None
    text = html[:200_000]  # limit scan size
    for pattern, ats_type, group in GREENHOUSE_PATTERNS:
        m = pattern.search(text)
        if m:
            board_id = m.group(group).strip("'\"").split("?")[0].rstrip("/")
            if board_id and len(board_id) < 80:
                return ats_type, board_id
    for pattern, ats_type, group in LEVER_PATTERNS:
        m = pattern.search(text)
        if m:
            board_id = m.group(group).strip("'\"").split("?")[0].rstrip("/")
            if board_id and len(board_id) < 80:
                return ats_type, board_id
    for pattern, ats_type, group in ASHBY_PATTERNS:
        m = pattern.search(text)
        if m:
            board_id = m.group(group).strip("'\"").split("?")[0].rstrip("/")
            if board_id and len(board_id) < 80:
                return ats_type, board_id
    for pattern, ats_type, group in SMARTRECRUITERS_PATTERNS:
        m = pattern.search(text)
        if m:
            board_id = m.group(group).strip("'\"").split("?")[0].rstrip("/")
            if board_id and len(board_id) < 80:
                return ats_type, board_id
    wd = _detect_workday(text)
    if wd is not None:
        return wd
    jz = _detect_jazzhr(text)
    if jz is not None:
        return jz
    wk = _detect_workable(text)
    if wk is not None:
        return wk
    rc = _detect_recruitee(text)
    if rc is not None:
        return rc
    ic = _detect_icims(text)
    if ic is not None:
        return ic
    return "generic", None


def detect_ats(careers_url: str) -> Result:
    """
    Given a career page URL, return (ats_type, board_id).
    ats_type: 'greenhouse' | 'lever' | 'ashby' | 'generic'
    board_id: token/slug for API (e.g. Greenhouse board token, Lever company slug).
    """
    if not careers_url or not careers_url.strip():
        return "generic", None
    url = careers_url.strip()
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = (parsed.path or "").strip("/")
    full_url = url.lower()

    for pattern, ats_type, group in GREENHOUSE_PATTERNS:
        m = pattern.search(full_url)
        if m:
            return ats_type, m.group(group)

    for pattern, ats_type, group in LEVER_PATTERNS:
        m = pattern.search(full_url)
        if m:
            return ats_type, m.group(group)

    for pattern, ats_type, group in ASHBY_PATTERNS:
        m = pattern.search(full_url)
        if m:
            return ats_type, m.group(group)

    for pattern, ats_type, group in SMARTRECRUITERS_PATTERNS:
        m = pattern.search(full_url)
        if m:
            return ats_type, m.group(group)

    wd = _detect_workday(full_url)
    if wd is not None:
        return wd
    jz = _detect_jazzhr(full_url)
    if jz is not None:
        return jz
    wk = _detect_workable(full_url)
    if wk is not None:
        return wk
    rc = _detect_recruitee(full_url)
    if rc is not None:
        return rc
    ic = _detect_icims(full_url)
    if ic is not None:
        return ic

    return "generic", None
