"""Discord webhook notifications for new jobs."""

import requests
from typing import Any

from src.config import DISCORD_WEBHOOK_URL

# Discord allows up to 10 embeds per message; we batch to avoid rate limits
EMBEDS_PER_MESSAGE = 10


def _embed_for_job(job: dict[str, Any]) -> dict[str, Any]:
    """Build a single Discord embed for one job."""
    title = (job.get("title") or "Untitled")[:256]
    url = job.get("url") or ""
    company = (job.get("company_name") or "").strip() or "Unknown"
    location = (job.get("location") or "").strip() or "—"
    return {
        "title": title,
        "url": url if url.startswith("http") else None,
        "color": 0x2E86AB,
        "fields": [
            {"name": "Company", "value": company[:1024], "inline": True},
            {"name": "Location", "value": location[:1024], "inline": True},
            {"name": "Apply", "value": url[:1024] if url else "—", "inline": False},
        ],
    }


def send_discord_new_jobs(jobs: list[dict[str, Any]]) -> bool:
    """
    Send new job alerts to Discord. Batches into messages of up to 10 embeds.
    Returns True if webhook is configured and send succeeded (or no jobs).
    """
    if not DISCORD_WEBHOOK_URL or not DISCORD_WEBHOOK_URL.strip():
        return False
    if not jobs:
        return True
    embeds = [_embed_for_job(j) for j in jobs]
    for i in range(0, len(embeds), EMBEDS_PER_MESSAGE):
        chunk = embeds[i : i + EMBEDS_PER_MESSAGE]
        payload = {
            "content": None,
            "embeds": chunk,
        }
        try:
            r = requests.post(
                DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=10,
            )
            r.raise_for_status()
        except requests.RequestException:
            return False
    return True
