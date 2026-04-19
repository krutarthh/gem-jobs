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

# Phrases that, when present in the job location text, should be treated as Canada-accepting
# (e.g. a JD listing "United States & Canada" or "Americas" is usually a global req hiring in Canada too).
DEFAULT_LOCATION_ACCEPT_ALIASES = [
    "united states & canada",
    "united states and canada",
    "us & canada",
    "us and canada",
    "americas",
    "north america",
    "global",
    "worldwide",
    "anywhere",
]

# Title tokens that signal a new-grad-safe role (skip JD senior filter when any of these appears
# in the title, because many new-grad JDs reuse senior boilerplate copy).
TITLE_LEVEL_RESCUE_RE = re.compile(
    r"(?ix)"
    r"\b(?:intern(?:ship)?s?|co[-\s]?op|new\s+grad(?:uate)?s?|junior|jr\.?|associate|"
    r"early[-\s]career|recent\s+graduate|campus\s+(?:hire|recruit)|"
    r"university\s+grad|college\s+grad|graduate\s+program|rotational\s+program|"
    r"fellow(?:ship)?|entry[-\s]level|apprentice(?:ship)?|"
    r"level\s*1|l1|l2|l3|e3|ic1|ic2|"
    r"(?:swe|sde|software\s+(?:engineer|developer))\s*(?:i|1))\b"
)

# Title signals the role is based in Canada — skip strict location check when any of these match
# (e.g. "Software Engineer, Toronto" even when location field says just "Hybrid").
TITLE_CANADA_RE = re.compile(
    r"(?ix)"
    r"\b(?:canada|canadian|toronto|greater\s+toronto|ontario|vancouver|"
    r"montreal|mont?real|quebec|calgary|ottawa|waterloo|edmonton|halifax|"
    r"remote\s+canada|canada\s+remote)\b"
)

# Separators used to split multi-location strings into discrete region tokens.
_LOCATION_SPLIT_RE = re.compile(r"[|/;]|,\s+|\s+and\s+|\s+&\s+|\s+or\s+")


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
    Jobs may have location as: str, list of str, or dict (e.g. {"name": "..."}).
    We merge all into one string (pipe-joined) so downstream matchers can split it again
    or treat the whole blob as a single searchable blob.
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
        return " | ".join(p for p in parts if p)
    if isinstance(location, dict):
        return (
            (location.get("name") or location.get("location") or location.get("value")) or ""
        ).strip()
    return (str(location) or "").strip()


def _split_location_parts(location_str: str) -> list[str]:
    """Break a location string like "Toronto, ON | Remote - US" into discrete chunks."""
    if not location_str:
        return []
    pieces = _LOCATION_SPLIT_RE.split(location_str)
    return [p.strip() for p in pieces if p and p.strip()]


def _escape_word_keyword(kw: str) -> str:
    """Escape regex metachars in a keyword, but preserve spaces so multi-word phrases work."""
    return re.escape(kw).replace("\\ ", "\\s+")


def _compile_word_pattern(keywords: list[str]) -> re.Pattern | None:
    if not keywords:
        return None
    parts = []
    for k in keywords:
        norm = _normalize(k)
        if not norm:
            continue
        parts.append(_escape_word_keyword(norm))
    if not parts:
        return None
    pat = r"(?<![A-Za-z0-9])(?:" + "|".join(parts) + r")(?![A-Za-z0-9])"
    return re.compile(pat)


def _matches_any(text: str, keywords: list[str], *, mode: str = "substring") -> bool:
    """
    Return True if any keyword appears in ``text``.
    mode=substring: classic contains match (fast, legacy behavior).
    mode=word: word-boundary regex match (avoids "lead" matching "leadership").
    """
    # #region agent log
    non_str = [(i, type(k).__name__, repr(k)) for i, k in enumerate(keywords) if not isinstance(k, str)]
    if non_str:
        _debug_log("cad17e", "filters.py:_matches_any", "keywords contained non-str entries", {"indices_and_types": non_str, "total_keywords": len(keywords)}, "A")
    # #endregion
    if not keywords:
        return True
    t = _normalize(text)
    if mode == "word":
        pat = _compile_word_pattern(keywords)
        return bool(pat and pat.search(t))
    return any(_normalize(k) in t for k in keywords)


def _contains_any(text: str, keywords: list[str], *, mode: str = "substring") -> bool:
    """True if text contains any keyword. Same ``mode`` semantics as ``_matches_any``."""
    if not keywords:
        return False
    t = _normalize(text)
    if mode == "word":
        pat = _compile_word_pattern(keywords)
        return bool(pat and pat.search(t))
    return any(_normalize(k) in t for k in keywords)


def _location_matches(
    location_str: str,
    title_dept: str,
    locations: list[str],
    *,
    accept_aliases: list[str] | None = None,
    allow_title_canada_signal: bool = True,
) -> bool:
    """
    True if the job's location (or title/department) signals a match with our target regions.
    Steps:
      1. Title signals (e.g. "... - Toronto") short-circuit to True.
      2. Any alias phrase (e.g. "Americas", "US & Canada") in the location string short-circuits True.
      3. Each chunk in the location string is matched against ``locations``; ANY match passes.
    """
    if allow_title_canada_signal and TITLE_CANADA_RE.search(title_dept or ""):
        return True
    location_norm = _normalize(location_str)
    if location_norm:
        aliases = accept_aliases if accept_aliases is not None else DEFAULT_LOCATION_ACCEPT_ALIASES
        for alias in aliases:
            if alias and _normalize(alias) in location_norm:
                return True
    chunks = _split_location_parts(location_str) or [location_str]
    for chunk in chunks:
        if _matches_any(chunk, locations, mode="substring"):
            return True
    # Also run the combined blob as a last resort (catches "United States, Canada" when split
    # punctuation variants differ).
    return _matches_any(location_str, locations, mode="substring")


def _title_signals_newgrad(title_dept: str) -> bool:
    return bool(title_dept) and TITLE_LEVEL_RESCUE_RE.search(title_dept) is not None


def _title_matches_synonyms(title_dept: str, synonym_groups: list[list[str]] | None) -> bool:
    """True if title/department hits at least one phrase in any synonym group (word mode)."""
    if not synonym_groups:
        return False
    for group in synonym_groups:
        if _matches_any(title_dept, group, mode="word"):
            return True
    return False


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
    match_mode: str = "substring",
    title_synonym_groups: list[list[str]] | None = None,
    location_accept_aliases: list[str] | None = None,
    allow_title_canada_signal: bool = True,
    newgrad_title_rescue: bool = True,
) -> str | None:
    """
    Return None if the job passes all filters; otherwise the first failing stage name.
    Stages: location, location_field, entry_level, title_keywords, exclude_keywords,
    jd_experience, recency.
    """
    title = _normalize(job.get("title") or "")
    location_str = _location_to_string(job.get("location"))
    department = _normalize(job.get("department") or "")
    title_dept = f"{title} {department}"

    # --- Location check -------------------------------------------------------
    combined_for_loc = f"{title_dept} {_normalize(location_str)}"
    if allow_empty_location and not location_str.strip():
        pass
    elif not (
        _location_matches(
            location_str,
            title_dept,
            locations,
            accept_aliases=location_accept_aliases,
            allow_title_canada_signal=allow_title_canada_signal,
        )
        or _matches_any(combined_for_loc, locations, mode="substring")
    ):
        return "location"
    if (
        require_location_field_match
        and location_str.strip()
        and not _location_matches(
            location_str,
            "",  # disable title-signal rescue here; this toggle is specifically about the field
            locations,
            accept_aliases=location_accept_aliases,
            allow_title_canada_signal=False,
        )
    ):
        return "location_field"

    # --- Level / title --------------------------------------------------------
    if entry_level_only and not _matches_any(title_dept, level_keywords, mode=match_mode):
        return "entry_level"
    if not (
        _matches_any(title_dept, title_keywords, mode=match_mode)
        or _title_matches_synonyms(title_dept, title_synonym_groups)
    ):
        return "title_keywords"

    # --- Exclude --------------------------------------------------------------
    exclude = exclude_keywords if exclude_keywords is not None else DEFAULT_EXCLUDE_KEYWORDS
    if _contains_any(title_dept, exclude, mode=match_mode):
        return "exclude_keywords"

    # --- JD experience (skip for rescued new-grad titles) --------------------
    if use_jd_experience_filter:
        desc = job.get("description") if isinstance(job.get("description"), str) else None
        prof = _jd_include_professional_phrases(jd_filter_mode)
        if not (newgrad_title_rescue and _title_signals_newgrad(title_dept)):
            if _jd_asks_senior_experience(desc, include_professional_phrases=prof):
                return "jd_experience"

    # --- Recency --------------------------------------------------------------
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
    match_mode: str = "substring",
    title_synonym_groups: list[list[str]] | None = None,
    location_accept_aliases: list[str] | None = None,
    allow_title_canada_signal: bool = True,
    newgrad_title_rescue: bool = True,
) -> bool:
    """Return True if job passes all filters (new-grad only, no senior/staff, optional recency)."""
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
            match_mode=match_mode,
            title_synonym_groups=title_synonym_groups,
            location_accept_aliases=location_accept_aliases,
            allow_title_canada_signal=allow_title_canada_signal,
            newgrad_title_rescue=newgrad_title_rescue,
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
    match_mode: str = "substring",
    title_synonym_groups: list[list[str]] | None = None,
    location_accept_aliases: list[str] | None = None,
    allow_title_canada_signal: bool = True,
    newgrad_title_rescue: bool = True,
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
            match_mode=match_mode,
            title_synonym_groups=title_synonym_groups,
            location_accept_aliases=location_accept_aliases,
            allow_title_canada_signal=allow_title_canada_signal,
            newgrad_title_rescue=newgrad_title_rescue,
        )
    ]
