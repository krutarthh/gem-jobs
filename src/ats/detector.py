"""Map career URL to ATS type and board token/slug."""

import re
from urllib.parse import urlparse

# (ats_type, board_id or None if not detectable)
Result = tuple[str, str | None]

# Patterns: (regex, ats_type, group index)
GREENHOUSE_PATTERNS = [
    (re.compile(r"boards\.greenhouse\.io/([^/?\"')\s]+)", re.I), "greenhouse", 1),
    (re.compile(r"job-boards\.greenhouse\.io/([^/?\"')\s]+)", re.I), "greenhouse", 1),
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

    # Workday, SmartRecruiters, custom: could add more patterns later
    return "generic", None
