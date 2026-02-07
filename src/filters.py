"""Filter jobs by location, new-grad level, keywords; exclude senior roles; optional recency."""

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
    if s is None:
        return ""
    return (s or "").strip().lower()


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
) -> bool:
    """
    Return True if job passes all filters (new-grad only, no senior/staff, optional recency).
    - Location: title/location/department contains one of locations
    - Level: title or department contains one of level_keywords (intern, new grad, SWE I, etc.)
    - Keywords: title or department contains one of title_keywords
    - Exclude: title or department must NOT contain any of exclude_keywords (senior, staff, etc.)
    - Recency: if max_days_since_posted set and job has posted_at, reject if older than that
    """
    title = _normalize(job.get("title") or "")
    location = _normalize(job.get("location") or "")
    department = _normalize(job.get("department") or "")
    combined = f"{title} {location} {department}"
    title_dept = f"{title} {department}"

    if not _matches_any(combined, locations):
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
        )
    ]
