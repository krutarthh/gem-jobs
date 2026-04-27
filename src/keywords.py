"""Tech keyword extractor for JD bodies.

Loads ``config/keywords.yaml`` once, compiles a single combined regex per label,
and returns the top N labels by match count for a given description string.
The output is purely informational (shown in Discord embeds) so we keep it
deterministic and lightweight — no NLP dependencies.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_KEYWORDS_PATH = Path(__file__).resolve().parent.parent / "config" / "keywords.yaml"


@lru_cache(maxsize=1)
def _load_keyword_map() -> list[tuple[str, re.Pattern]]:
    """Return [(display_label, compiled regex), ...] sorted alphabetically."""
    if not _KEYWORDS_PATH.exists():
        return []
    try:
        data = yaml.safe_load(_KEYWORDS_PATH.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return []
    raw = data.get("keywords") or {}
    out: list[tuple[str, re.Pattern]] = []
    for label, phrases in raw.items():
        if not isinstance(label, str) or not isinstance(phrases, list):
            continue
        cleaned = [p for p in phrases if isinstance(p, str) and p.strip()]
        if not cleaned:
            continue
        # Build a single non-capturing alternation with word-boundary guards.
        body = "|".join(p.strip() for p in cleaned)
        try:
            pat = re.compile(r"(?<![A-Za-z0-9])(?:" + body + r")(?![A-Za-z0-9])", re.I)
        except re.error:
            continue
        out.append((label, pat))
    out.sort(key=lambda x: x[0].lower())
    return out


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


def extract_top_keywords(description: str | None, *, limit: int = 5) -> list[str]:
    """Return up to ``limit`` keyword labels found in the description, ordered by frequency."""
    if not description or not isinstance(description, str):
        return []
    text = _strip_html(description) if "<" in description else description
    if not text:
        return []
    hits: list[tuple[str, int]] = []
    for label, pat in _load_keyword_map():
        n = len(pat.findall(text))
        if n > 0:
            hits.append((label, n))
    if not hits:
        return []
    # Sort by count desc, then alpha for stable ties.
    hits.sort(key=lambda x: (-x[1], x[0].lower()))
    return [h[0] for h in hits[:limit]]


def annotate_with_keywords(jobs: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    """In-place annotate each job with `_keywords`. Returns the same list for chaining."""
    for j in jobs:
        if j.get("_keywords"):
            continue
        j["_keywords"] = extract_top_keywords(j.get("description"), limit=limit)
    return jobs
