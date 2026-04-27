"""Deterministic 0-100 scoring for jobs to rank Discord alerts.

The score is intentionally simple and explainable so a glance at the breakdown
tells you why a job placed where it did. Tuned for a Toronto SWE with 2 yrs
co-op experience hunting new-grad to Engineer II roles.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from src.filters import _location_to_string, _normalize, _parse_posted_at

# Regex compiled once.
_TITLE_CORE_RE = re.compile(
    r"(?ix)\b(software\s+engineer|software\s+developer|swe|sde|backend|frontend|"
    r"full[-\s]?stack|web\s+developer|mobile\s+(?:engineer|developer))\b"
)
_TITLE_NEWGRAD_RE = re.compile(
    r"(?ix)\b(intern(?:ship)?s?|co[-\s]?op|new\s+grad(?:uate)?s?|junior|jr\.?|"
    r"associate|early[-\s]career|recent\s+graduate|campus|university\s+grad|"
    r"college\s+grad|graduate\s+program|rotational|fellow(?:ship)?|entry[-\s]level|"
    r"engineer\s*i\b|swe\s*i\b|swe\s*1\b|engineer\s*1\b)"
)
_TITLE_ENGII_RE = re.compile(
    r"(?ix)\b(engineer\s*ii|engineer\s*2|swe\s*ii|swe\s*2|software\s+engineer\s*ii|"
    r"software\s+engineer\s*2|software\s+developer\s*ii|level\s*2)\b"
)
_TITLE_NOISE_RE = re.compile(
    r"(?ix)\b(sales|recruiter|recruiting|talent\s+acquisition|marketing|"
    r"customer\s+success|account\s+executive|account\s+manager|partnerships|"
    r"business\s+development|hr\s+|human\s+resources|legal|paralegal|"
    r"operations\s+manager|finance\s+manager|hardware\s+technician|"
    r"data\s+center\s+technician|metrology|photonics)\b"
)
_JD_FRIENDLY_RE = re.compile(
    r"(?ix)\b(new\s+grad|recent\s+graduate|co[-\s]?op|early[-\s]career|"
    r"university\s+grad|campus\s+(?:hire|recruit)|0[-\s]\d?\s*years?|"
    r"no\s+experience\s+required)\b"
)


def _resolve_priority_index(location_norm: str, priority: list[str]) -> int | None:
    """Return zero-based index of best matching priority entry (lower = better)."""
    if not location_norm or not priority:
        return None
    for idx, label in enumerate(priority):
        if not label:
            continue
        if _normalize(label) in location_norm:
            return idx
    return None


def _ats_type_bonus(ats_type: str | None) -> int:
    if not ats_type:
        return 0
    t = ats_type.lower()
    if t in {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}:
        return 5
    if t in {"workday", "jazzhr"}:
        return 3
    return 0


def score_job(
    job: dict[str, Any],
    *,
    location_priority: list[str] | None = None,
) -> tuple[int, dict[str, int]]:
    """Return (score 0-100, breakdown of contributing components).

    Breakdown keys describe why each delta was applied; useful for debugging or
    showing in Discord embeds if we ever want to.
    """
    breakdown: dict[str, int] = {}

    title = job.get("title") or ""
    department = job.get("department") or ""
    title_dept_norm = _normalize(f"{title} {department}")
    location_str = _location_to_string(job.get("location"))
    location_norm = _normalize(location_str)

    if _TITLE_CORE_RE.search(title_dept_norm):
        breakdown["title_core_swe"] = 30
    elif _normalize("engineer") in title_dept_norm or _normalize("developer") in title_dept_norm:
        breakdown["title_core_swe"] = 20

    if _TITLE_NEWGRAD_RE.search(title_dept_norm):
        breakdown["title_newgrad"] = 18
    elif _TITLE_ENGII_RE.search(title_dept_norm):
        breakdown["title_engineer_ii"] = 12

    priority = location_priority or []
    idx = _resolve_priority_index(location_norm, priority)
    if idx is not None:
        # Top of the list (Toronto) gets +25; each step down loses 2 points down to a floor of +5.
        loc_pts = max(5, 25 - idx * 2)
        breakdown["location_priority"] = loc_pts

    posted = _parse_posted_at(job.get("posted_at"))
    if posted is not None:
        delta = (datetime.now(timezone.utc) - posted).days
        if delta <= 1:
            breakdown["recency"] = 15
        elif delta <= 3:
            breakdown["recency"] = 12
        elif delta <= 7:
            breakdown["recency"] = 8
        elif delta <= 14:
            breakdown["recency"] = 4

    breakdown["ats"] = _ats_type_bonus(job.get("ats_type"))

    desc = job.get("description")
    if isinstance(desc, str) and desc:
        if _JD_FRIENDLY_RE.search(desc):
            breakdown["jd_newgrad_friendly"] = 5

    if _TITLE_NOISE_RE.search(title_dept_norm):
        breakdown["title_noise_penalty"] = -25

    score = sum(breakdown.values())
    score = max(0, min(100, score))
    return score, breakdown


def rank_jobs(
    jobs: list[dict[str, Any]],
    *,
    location_priority: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Annotate each job with `_score` and `_score_breakdown`, return sorted desc by score."""
    annotated = []
    for j in jobs:
        s, br = score_job(j, location_priority=location_priority)
        j2 = dict(j)
        j2["_score"] = s
        j2["_score_breakdown"] = br
        annotated.append(j2)
    annotated.sort(
        key=lambda j: (
            j.get("_score", 0),
            # Tie-break: more recent first when scores tie.
            (j.get("posted_at") or ""),
        ),
        reverse=True,
    )
    return annotated
