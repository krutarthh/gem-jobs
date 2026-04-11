"""Filter jobs by location, new-grad level, keywords; exclude senior roles; optional recency."""

import json
import re
import unicodedata
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any

# #region agent log
_DEBUG_LOG_PATH = str(Path(__file__).resolve().parent.parent / ".cursor" / "debug-cad17e.log")
def _debug_log(session_id: str, location: str, message: str, data: dict, hypothesis_id: str, run_id: str = "run1") -> None:
    try:
        payload = {"sessionId": session_id, "runId": run_id, "hypothesisId": hypothesis_id, "location": location, "message": message, "data": data, "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000)}
        with open(_DEBUG_LOG_PATH, "a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
# #endregion

# Default: reject if title/department contains any of these (senior/staff/lead)
DEFAULT_EXCLUDE_KEYWORDS = [
    "senior", "staff", "principal", "lead ", "lead,", "architect",
    "director", "distinguished", "fellow", "head of", "vp ", "vp,", "vice president",
    "sr.", "sr ", "sr,", "manager", "l5", "l6", "l7", "engineer ii", "engineer iii",
    "engineer 2", "engineer 3", "software engineer ii", "software engineer iii",
    "senior software", "staff software", "principal engineer", "tech lead",
]


def _normalize(s: str | None | Any) -> str:
    """Normalize for matching: strip, lower, and remove accents (e.g. Montréal -> montreal)."""
    if s is None:
        return ""
    if not isinstance(s, str):
        s = "ON" if s is True else "OFF" if s is False else str(s)  # YAML parses unquoted ON/off as bool
    # #region agent log
    if s and not isinstance(s, str):
        _debug_log("cad17e", "filters.py:_normalize", "non-str value passed to _normalize", {"type": type(s).__name__, "repr": repr(s)}, "B")
    # #endregion
    t = (s or "").strip().lower()
    # NFD and drop combining characters so accents don't block matches
    nfd = unicodedata.normalize("NFD", t)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _location_to_string(location: Any) -> str:
    """
    Normalize job location to a single string for matching.
    Jobs may have location as: str, list of str (multiple locations), or dict (e.g. {"name": "..."}).
    We merge all into one string so Canada/Toronto matching works when a job has multiple locations.
    """
    if location is None:
        return ""
    if isinstance(location, list):
        parts = []
        for item in location:
            if isinstance(item, dict):
                parts.append(item.get("name") or item.get("location") or item.get("value") or "")
            elif item is not None and str(item).strip():
                parts.append(str(item).strip())
        return " ".join(parts)
    if isinstance(location, dict):
        return (
            (location.get("name") or location.get("location") or location.get("value")) or ""
        ).strip()
    return (str(location) or "").strip()


def _matches_any(text: str, keywords: list[str]) -> bool:
    # #region agent log
    non_str = [(i, type(k).__name__, repr(k)) for i, k in enumerate(keywords) if not isinstance(k, str)]
    if non_str:
        _debug_log("cad17e", "filters.py:_matches_any", "keywords contained non-str entries", {"indices_and_types": non_str, "total_keywords": len(keywords)}, "A")
    # #endregion
    if not keywords:
        return True
    t = _normalize(text)
    return any(_normalize(k) in t for k in keywords)


def _contains_any(text: str, keywords: list[str]) -> bool:
    """Return True if text (normalized) contains any of the keywords."""
    if not keywords:
        return False
    t = _normalize(text)
    return any(_normalize(k) in t for k in keywords)


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities for plain-text analysis."""
    if not html or not isinstance(html, str):
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


# Exclude if JD asks for any professional experience (or 3+ years generic). Internship experience OK.
# Any amount of "professional experience" → exclude unless clearly internship context.
_JD_ANY_PROFESSIONAL_PATTERNS = [
    re.compile(r"\bprofessional\s+experience\b", re.I),
    re.compile(r"\byears?\s+of\s+professional\s+experience\b", re.I),
    re.compile(r"\b(1[0-9]|[0-9])\s*\+?\s*years?\s+of\s+professional\s+experience\b", re.I),
    re.compile(r"\b(1[0-9]|[0-9])\s*\+?\s*years?\s+professional\s+experience\b", re.I),
    re.compile(r"\bprofessional\s+experience\s+in\b", re.I),
    re.compile(r"\brelevant\s+professional\s+experience\b", re.I),
    re.compile(r"\bprior\s+professional\s+experience\b", re.I),
]
# 3+ years generic (non-internship) → exclude. If match is near "intern/internship", allow.
_JD_GENERIC_YOE_PATTERNS = [
    re.compile(r"\b(1[0-9]|[3-9])\s*\+\s*years?\b", re.I),
    re.compile(r"\b(1[0-9]|[3-9])\s*\+\s*yrs?\b", re.I),
    re.compile(r"\bminimum\s+(1[0-9]|[3-9])\s*years?\b", re.I),
    re.compile(r"\bat\s+least\s+(1[0-9]|[3-9])\s*years?\b", re.I),
    re.compile(r"\b(1[0-9]|[3-9])\s*[-–]\s*(1[0-9]|[3-9])\s*\+?\s*years?\b", re.I),
    re.compile(r"\b(1[0-9]|[3-9])\s*\+?\s*years?\s+of\s+(?:relevant\s+)?experience\b", re.I),
]
# Unambiguous senior wording — no internship exception
_JD_SENIOR_LEVEL_PATTERNS = [
    re.compile(r"\bsenior\s+level\s+experience\b", re.I),
    re.compile(r"\bstaff\s+level\s+experience\b", re.I),
    re.compile(r"\bprincipal\s+level\s+experience\b", re.I),
    re.compile(r"\bextensive\s+experience\s+in\s+", re.I),
]

_JD_INTERNSHIP_CONTEXT = re.compile(r"\binterns?\b|\binternship\b", re.I)
_JD_CONTEXT_WINDOW = 120  # chars before/after a match; if "intern" in window, treat as internship OK


def _jd_asks_senior_experience(
    description: str | None,
    *,
    include_professional_phrases: bool = True,
) -> bool:
    """
    Return True if the JD requires professional experience or 3+ years (generic).
    Exclude if JD asks for any professional experience (even 1 year). Internship experience is allowed.
    New-grad/entry-level JDs: do not exclude solely on bare "1+ years" or "2+ years" (no "professional").
    When include_professional_phrases is False (yoe_and_senior_only mode), skip boilerplate
    "professional experience" patterns and only apply senior-level and 3+ year YOE heuristics.
    """
    if not description or not isinstance(description, str) or len(description.strip()) < 50:
        return False
    text = _strip_html(description)
    text_norm = _normalize(text)
    for pat in _JD_SENIOR_LEVEL_PATTERNS:
        if pat.search(text_norm):
            return True
    if include_professional_phrases:
        for pat in _JD_ANY_PROFESSIONAL_PATTERNS:
            m = pat.search(text_norm)
            if m:
                start = max(0, m.start() - _JD_CONTEXT_WINDOW)
                end = min(len(text_norm), m.end() + _JD_CONTEXT_WINDOW)
                window = text_norm[start:end]
                if _JD_INTERNSHIP_CONTEXT.search(window):
                    continue  # e.g. "professional internship experience" or internship context
                return True
    for pat in _JD_GENERIC_YOE_PATTERNS:
        m = pat.search(text_norm)
        if m:
            start = max(0, m.start() - _JD_CONTEXT_WINDOW)
            end = min(len(text_norm), m.end() + _JD_CONTEXT_WINDOW)
            window = text_norm[start:end]
            if _JD_INTERNSHIP_CONTEXT.search(window):
                continue
            return True
    return False


def _parse_posted_at(posted_at: str | None) -> datetime | None:
    """Parse ISO-ish posted_at; return None if missing or invalid."""
    if not posted_at or not str(posted_at).strip():
        return None
    try:
        s = str(posted_at).strip()
        if "T" in s:
            # Drop timezone suffix for simplicity (treat as UTC)
            if s.endswith("Z") or "+" in s or "-" in s[-6:]:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _jd_include_professional_phrases(jd_filter_mode: str) -> bool:
    """standard: full JD rules; yoe_and_senior_only: skip 'professional experience' boilerplate patterns."""
    return jd_filter_mode != "yoe_and_senior_only"


def filter_failure_reason(
    job: dict[str, Any],
    locations: list[str],
    level_keywords: list[str],
    title_keywords: list[str],
    exclude_keywords: list[str] | None = None,
    max_days_since_posted: int | None = None,
    allow_empty_location: bool = False,
    require_location_field_match: bool = False,
    entry_level_only: bool = True,
    use_jd_experience_filter: bool = True,
    jd_filter_mode: str = "standard",
) -> str | None:
    """
    Return None if the job passes all filters; otherwise the first failing stage name.
    Stages: location, location_field, entry_level, title_keywords, exclude_keywords,
    jd_experience, recency.
    """
    title = _normalize(job.get("title") or "")
    location_str = _location_to_string(job.get("location"))
    location = _normalize(location_str)
    department = _normalize(job.get("department") or "")
    combined = f"{title} {location} {department}"
    title_dept = f"{title} {department}"

    if allow_empty_location and not location_str.strip():
        pass
    elif not _matches_any(combined, locations):
        return "location"
    if require_location_field_match and location_str.strip() and not _matches_any(location_str, locations):
        return "location_field"
    if entry_level_only and not _matches_any(title_dept, level_keywords):
        return "entry_level"
    if not _matches_any(title_dept, title_keywords):
        return "title_keywords"

    exclude = exclude_keywords if exclude_keywords is not None else DEFAULT_EXCLUDE_KEYWORDS
    if _contains_any(title_dept, exclude):
        return "exclude_keywords"

    if use_jd_experience_filter:
        desc = job.get("description") if isinstance(job.get("description"), str) else None
        prof = _jd_include_professional_phrases(jd_filter_mode)
        if _jd_asks_senior_experience(desc, include_professional_phrases=prof):
            return "jd_experience"

    if max_days_since_posted is not None and max_days_since_posted > 0:
        posted = _parse_posted_at(job.get("posted_at"))
        if posted is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=max_days_since_posted)
            if posted < cutoff:
                return "recency"
    return None


def passes_filters(
    job: dict[str, Any],
    locations: list[str],
    level_keywords: list[str],
    title_keywords: list[str],
    exclude_keywords: list[str] | None = None,
    max_days_since_posted: int | None = None,
    allow_empty_location: bool = False,
    require_location_field_match: bool = False,
    entry_level_only: bool = True,
    use_jd_experience_filter: bool = True,
    jd_filter_mode: str = "standard",
) -> bool:
    """
    Return True if job passes all filters (new-grad only, no senior/staff, optional recency).
    - Location: title/location/department contains one of locations (location can be str or list of
      locations; multiple locations are merged so e.g. Canada/Toronto is matched if any location matches).
      If allow_empty_location is True, missing/empty location is treated as passing the location check.
      If require_location_field_match is True, the job's location field must also contain a location keyword.
    - Level: title or department contains one of level_keywords (intern, new grad, SWE I, etc.)
    - Keywords: title or department contains one of title_keywords
    - Exclude: title or department must NOT contain any of exclude_keywords (senior, staff, etc.)
    - Recency: if max_days_since_posted set and job has posted_at, reject if older than that
    """
    return (
        filter_failure_reason(
            job,
            locations,
            level_keywords,
            title_keywords,
            exclude_keywords=exclude_keywords,
            max_days_since_posted=max_days_since_posted,
            allow_empty_location=allow_empty_location,
            require_location_field_match=require_location_field_match,
            entry_level_only=entry_level_only,
            use_jd_experience_filter=use_jd_experience_filter,
            jd_filter_mode=jd_filter_mode,
        )
        is None
    )


def filter_jobs(
    jobs: list[dict[str, Any]],
    locations: list[str],
    level_keywords: list[str],
    title_keywords: list[str],
    exclude_keywords: list[str] | None = None,
    max_days_since_posted: int | None = None,
    allow_empty_location: bool = False,
    require_location_field_match: bool = False,
    entry_level_only: bool = True,
    use_jd_experience_filter: bool = True,
    jd_filter_mode: str = "standard",
) -> list[dict[str, Any]]:
    """Return only jobs that pass all filters (new-grad only, no senior, optional recency)."""
    # #region agent log
    loc_types = [type(x).__name__ for x in locations]
    non_str_idx = [i for i, x in enumerate(locations) if not isinstance(x, str)]
    _debug_log("cad17e", "filters.py:filter_jobs", "locations list types", {"types": loc_types, "non_str_indices": non_str_idx, "len": len(locations)}, "A")
    # #endregion
    return [
        j
        for j in jobs
        if passes_filters(
            j,
            locations,
            level_keywords,
            title_keywords,
            exclude_keywords=exclude_keywords,
            max_days_since_posted=max_days_since_posted,
            allow_empty_location=allow_empty_location,
            require_location_field_match=require_location_field_match,
            entry_level_only=entry_level_only,
            use_jd_experience_filter=use_jd_experience_filter,
            jd_filter_mode=jd_filter_mode,
        )
    ]
