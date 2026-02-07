"""
Run the scraper every SCRAPE_INTERVAL_MINUTES. For 24/7 monitoring.
Usage: python scripts/run_scheduler.py
"""

import sys
import time
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import SCRAPE_INTERVAL_MINUTES
from src.main import run_once


def main() -> int:
    interval_seconds = max(60, SCRAPE_INTERVAL_MINUTES * 60)
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"Run failed: {e}", flush=True)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    sys.exit(main())
