"""Filter jobs by location, new-grad level, keywords; exclude senior roles; optional recency."""

import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Any

# Default: reject if title/department contains any of these (senior/staff/lead)
DEFAULT_EXCLUDE_KEYWORDS = [
    "senior", "staff", "principal", "lead ", "lead,", "architect",
    "director", "distinguished", "fellow", "head of", "vp ", "vp,", "vice president",
    "sr.", "sr ", "sr,", "manager", "l5", "l6", "l7", "engineer ii", "engineer iii",
    "engineer 2", "engineer 3", "software engineer ii", "software engineer iii",
    "senior software", "staff software", "principal engineer", "tech lead",
]


def _normalize(s: str | None) -> str:
    """Normalize for matching: strip, lower, and remove accents (e.g. Montréal -> montreal)."""
    if s is None:
        return ""
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


def passes_filters(
    job: dict[str, Any],
    locations: list[str],
    level_keywords: list[str],
    title_keywords: list[str],
    exclude_keywords: list[str] | None = None,
    max_days_since_posted: int | None = None,
    allow_empty_location: bool = False,
    require_location_field_match: bool = False,
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
    title = _normalize(job.get("title") or "")
    location_str = _location_to_string(job.get("location"))
    location = _normalize(location_str)
    department = _normalize(job.get("department") or "")
    combined = f"{title} {location} {department}"
    title_dept = f"{title} {department}"

    # Location check: combined text or (if allow_empty_location) empty location passes
    if allow_empty_location and not location_str.strip():
        pass  # treat empty location as passing
    elif not _matches_any(combined, locations):
        return False
    if require_location_field_match and location_str.strip() and not _matches_any(location_str, locations):
        return False
    if not _matches_any(title_dept, level_keywords):
        return False
    if not _matches_any(title_dept, title_keywords):
        return False

    exclude = exclude_keywords if exclude_keywords is not None else DEFAULT_EXCLUDE_KEYWORDS
    if _contains_any(title_dept, exclude):
        return False

    if max_days_since_posted is not None and max_days_since_posted > 0:
        posted = _parse_posted_at(job.get("posted_at"))
        if posted is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=max_days_since_posted)
            if posted < cutoff:
                return False
    return True


def filter_jobs(
    jobs: list[dict[str, Any]],
    locations: list[str],
    level_keywords: list[str],
    title_keywords: list[str],
    exclude_keywords: list[str] | None = None,
    max_days_since_posted: int | None = None,
    allow_empty_location: bool = False,
    require_location_field_match: bool = False,
) -> list[dict[str, Any]]:
    """Return only jobs that pass all filters (new-grad only, no senior, optional recency)."""
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
        )
    ]
