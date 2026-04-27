"""Load watchlist and filters from YAML and env."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

# Paths (env overrides)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_WATCHLIST = str(PROJECT_ROOT / "config" / "watchlist.yaml")
_DEFAULT_DB = str(PROJECT_ROOT / "data" / "jobs.db")
WATCHLIST_PATH = Path(os.getenv("WATCHLIST_PATH", _DEFAULT_WATCHLIST))
DB_PATH = Path(os.getenv("DB_PATH", _DEFAULT_DB))

# Discord and scheduler
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
# Optional second webhook for Tier B (core match but failed JD or recency — review queue)
DISCORD_REVIEW_WEBHOOK_URL = os.getenv("DISCORD_REVIEW_WEBHOOK_URL", "")
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "15"))


def _read_watchlist_yaml() -> dict:
    path = WATCHLIST_PATH if WATCHLIST_PATH.is_absolute() else PROJECT_ROOT / WATCHLIST_PATH
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def load_watchlist() -> list[dict]:
    """Load companies and filter config from watchlist YAML."""
    data = _read_watchlist_yaml()
    return data.get("companies", [])


def load_filters() -> dict:
    """Load filter lists (locations, level_keywords, title_keywords) from watchlist YAML."""
    data = _read_watchlist_yaml()
    if not data:
        return _default_filters()
    filters = data.get("filters", {})
    defaults = _default_filters()

    def _ensure_str_list(raw: list, default: list) -> list:
        out = []
        for x in raw if isinstance(raw, list) else default:
            if isinstance(x, str):
                out.append(x)
            elif x is True:
                out.append("ON")  # YAML parses unquoted "ON" as bool True
            elif x is False:
                out.append("OFF")
            else:
                out.append(str(x))
        return out

    def _ensure_group_list(raw: Any, default: list[list[str]]) -> list[list[str]]:
        if not isinstance(raw, list):
            return default
        out: list[list[str]] = []
        for group in raw:
            if isinstance(group, list):
                out.append(_ensure_str_list(group, []))
            elif isinstance(group, dict) and "keywords" in group:
                out.append(_ensure_str_list(group.get("keywords"), []))
        # Drop empty groups.
        return [g for g in out if g] or default

    locs = filters.get("locations", defaults["locations"])
    return {
        "locations": _ensure_str_list(locs, defaults["locations"]),
        "level_keywords": _ensure_str_list(filters.get("level_keywords", defaults["level_keywords"]), defaults["level_keywords"]),
        "title_keywords": _ensure_str_list(filters.get("title_keywords", defaults["title_keywords"]), defaults["title_keywords"]),
        "exclude_keywords": _ensure_str_list(filters.get("exclude_keywords", defaults["exclude_keywords"]), defaults["exclude_keywords"]),
        "max_days_since_posted": filters.get("max_days_since_posted", defaults["max_days_since_posted"]),
        "allow_empty_location": filters.get("allow_empty_location", defaults["allow_empty_location"]),
        "require_location_field_match": filters.get("require_location_field_match", defaults["require_location_field_match"]),
        "entry_level_only": filters.get("entry_level_only", defaults["entry_level_only"]),
        "use_jd_experience_filter": filters.get("use_jd_experience_filter", defaults["use_jd_experience_filter"]),
        "jd_filter_mode": filters.get("jd_filter_mode", defaults["jd_filter_mode"]),
        "match_mode": filters.get("match_mode", defaults["match_mode"]),
        "title_synonym_groups": _ensure_group_list(
            filters.get("title_synonym_groups"), defaults["title_synonym_groups"]
        ),
        "location_accept_aliases": _ensure_str_list(
            filters.get("location_accept_aliases", defaults["location_accept_aliases"]),
            defaults["location_accept_aliases"],
        ),
        "allow_title_canada_signal": filters.get(
            "allow_title_canada_signal", defaults["allow_title_canada_signal"]
        ),
        "newgrad_title_rescue": filters.get(
            "newgrad_title_rescue", defaults["newgrad_title_rescue"]
        ),
        "max_yoe_accept": int(filters.get("max_yoe_accept", defaults["max_yoe_accept"])),
        "location_priority": _ensure_str_list(
            filters.get("location_priority", defaults["location_priority"]),
            defaults["location_priority"],
        ),
    }


def _default_filters() -> dict:
    return {
        "locations": [
            "Canada",
            "Toronto",
            "Greater Toronto Area",
            "GTA",
            "Ontario",
            "ON",
            "Remote - Canada",
            "Vancouver",
            "British Columbia",
            "BC",
            "Montreal",
            "Quebec",
            "QC",
            "Alberta",
            "Calgary",
            "Ottawa",
        ],
        "level_keywords": [
            "intern",
            "internship",
            "new grad",
            "new graduate",
            "SWE I",
            "Software Engineer I",
            "entry level",
            "entry-level",
        ],
        "title_keywords": [
            "software",
            "backend",
            "full stack",
            "fullstack",
            "developer",
            "engineer",
        ],
        "exclude_keywords": [
            "senior", "staff", "principal", "lead ", "architect", "director",
            "distinguished", "fellow", "head of", "vp ", "vice president", "sr.", "manager",
            "l5", "l6", "l7", "engineer ii", "engineer iii", "engineer 2", "engineer 3",
            "software engineer ii", "software engineer iii", "tech lead",
        ],
        "max_days_since_posted": 30,
        "allow_empty_location": False,
        "require_location_field_match": False,
        "entry_level_only": True,
        "use_jd_experience_filter": True,
        "jd_filter_mode": "standard",
        "match_mode": "word",
        "title_synonym_groups": [
            ["software engineer", "software developer", "swe", "sde", "application engineer"],
            ["backend", "back end", "full stack", "frontend", "front end", "mobile", "ios", "android"],
            ["data engineer", "analytics engineer", "data scientist", "applied scientist"],
            ["ml engineer", "machine learning engineer", "ai engineer", "ai resident", "research engineer"],
            ["platform engineer", "infrastructure engineer", "systems engineer", "site reliability", "sre", "devops", "cloud engineer"],
        ],
        "location_accept_aliases": [
            "united states & canada",
            "united states and canada",
            "us & canada",
            "us and canada",
            "americas",
            "north america",
            "global",
            "worldwide",
            "anywhere",
        ],
        "allow_title_canada_signal": True,
        "newgrad_title_rescue": True,
        "max_yoe_accept": 3,
        "location_priority": [
            "Toronto",
            "Greater Toronto Area",
            "GTA",
            "Ontario",
            "Remote - Canada",
            "Canada Remote",
            "Canada",
        ],
    }


def load_db_cleanup() -> dict:
    """Load SQLite retention settings from watchlist YAML (`db_cleanup:`)."""
    data = _read_watchlist_yaml()
    defaults = _default_db_cleanup()
    if not data:
        return defaults
    raw = data.get("db_cleanup")
    if not isinstance(raw, dict):
        return defaults
    merged = {**defaults}
    for key in defaults:
        if key in raw:
            merged[key] = raw[key]
    return merged


def _default_db_cleanup() -> dict:
    return {
        "enabled": True,
        "delete_jobs_last_seen_older_than_days": 90,
        "delete_runs_older_than_days": 180,
        "delete_orphan_companies": True,
        # Clears stored JD HTML/text after each run; next scrape repopulates for live listings.
        # Keeps jobs.db small (GitHub rejects files > 100 MB on normal git push).
        "strip_job_descriptions": True,
        "vacuum": True,
    }
