# ATS-specific fetchers and detector

from src.ats.detector import detect_ats, detect_ats_from_html
from src.ats.greenhouse import fetch_jobs as greenhouse_fetch
from src.ats.lever import fetch_jobs as lever_fetch
from src.ats.ashby import fetch_jobs as ashby_fetch
from src.ats.generic import fetch_jobs as generic_fetch


def fetch_jobs_for_company(ats_type: str, board_id: str | None, careers_url: str) -> list[dict]:
    """
    Dispatch to the right fetcher. Returns list of normalized jobs:
    id, title, location, department, url, posted_at.
    """
    if ats_type == "greenhouse" and board_id:
        return greenhouse_fetch(board_id)
    if ats_type == "lever" and board_id:
        return lever_fetch(board_id)
    if ats_type == "ashby" and board_id:
        return ashby_fetch(board_id)
    return generic_fetch(careers_url)
