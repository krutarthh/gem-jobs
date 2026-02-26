"""Load watchlist and filters from YAML and env."""

import os
from pathlib import Path

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
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "15"))


def load_watchlist() -> list[dict]:
    """Load companies and filter config from watchlist YAML."""
    path = WATCHLIST_PATH if WATCHLIST_PATH.is_absolute() else PROJECT_ROOT / WATCHLIST_PATH
    if not path.exists():
        return []
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    return data.get("companies", [])


def load_filters() -> dict:
    """Load filter lists (locations, level_keywords, title_keywords) from watchlist YAML."""
    path = WATCHLIST_PATH if WATCHLIST_PATH.is_absolute() else PROJECT_ROOT / WATCHLIST_PATH
    if not path.exists():
        return _default_filters()
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
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

    locs = filters.get("locations", defaults["locations"])
    return {
        "locations": _ensure_str_list(locs, defaults["locations"]),
        "level_keywords": _ensure_str_list(filters.get("level_keywords", defaults["level_keywords"]), defaults["level_keywords"]),
        "title_keywords": _ensure_str_list(filters.get("title_keywords", defaults["title_keywords"]), defaults["title_keywords"]),
        "exclude_keywords": _ensure_str_list(filters.get("exclude_keywords", defaults["exclude_keywords"]), defaults["exclude_keywords"]),
        "max_days_since_posted": filters.get("max_days_since_posted", defaults["max_days_since_posted"]),
        "allow_empty_location": filters.get("allow_empty_location", defaults["allow_empty_location"]),
        "require_location_field_match": filters.get("require_location_field_match", defaults["require_location_field_match"]),
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
    }
