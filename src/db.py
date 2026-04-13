"""SQLite schema, upsert jobs, query new since last run."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.config import DB_PATH

# Resolve DB path relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = DB_PATH if DB_PATH.is_absolute() else _PROJECT_ROOT / DB_PATH


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                careers_url TEXT NOT NULL,
                ats_type TEXT,
                board_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_careers_url
                ON companies(careers_url);

            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                external_id TEXT NOT NULL,
                title TEXT,
                location TEXT,
                department TEXT,
                url TEXT,
                posted_at TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_company_external
                ON jobs(company_id, external_id);

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                companies_checked INTEGER DEFAULT 0,
                new_jobs_count INTEGER DEFAULT 0
            );
        """)
        # Migration: add posted_at if missing (existing DBs)
        try:
            info = c.execute("PRAGMA table_info(jobs)").fetchall()
            columns = [row[1] for row in info]
            if "posted_at" not in columns:
                c.execute("ALTER TABLE jobs ADD COLUMN posted_at TEXT")
            if "description" not in columns:
                c.execute("ALTER TABLE jobs ADD COLUMN description TEXT")
        except sqlite3.OperationalError:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_company(
    name: str,
    careers_url: str,
    ats_type: str | None = None,
    board_id: str | None = None,
) -> int:
    """Insert or update company; return company id."""
    now = _now()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO companies (name, careers_url, ats_type, board_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(careers_url) DO UPDATE SET
                name = excluded.name,
                ats_type = excluded.ats_type,
                board_id = excluded.board_id,
                updated_at = excluded.updated_at
            """,
            (name, careers_url, ats_type, board_id, now, now),
        )
        row = c.execute(
            "SELECT id FROM companies WHERE careers_url = ?",
            (careers_url,),
        ).fetchone()
        return row["id"]


def upsert_job(
    company_id: int,
    external_id: str,
    title: str | None,
    location: str | None,
    department: str | None,
    url: str | None,
    posted_at: str | None = None,
    description: str | None = None,
) -> tuple[int, bool]:
    """
    Insert or update job. Return (job_id, is_new).
    is_new is True only when the job was just inserted (first time seen).
    posted_at: optional ISO date from ATS (used for recency filter).
    description: optional full JD text for experience-based filtering.
    """
    now = _now()
    with _conn() as c:
        existing = c.execute(
            "SELECT id FROM jobs WHERE company_id = ? AND external_id = ?",
            (company_id, external_id),
        ).fetchone()
        is_new = existing is None
        c.execute(
            """
            INSERT INTO jobs (company_id, external_id, title, location, department, url, posted_at, description, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, external_id) DO UPDATE SET
                title = excluded.title,
                location = excluded.location,
                department = excluded.department,
                url = excluded.url,
                posted_at = COALESCE(excluded.posted_at, jobs.posted_at),
                description = excluded.description,
                last_seen_at = excluded.last_seen_at
            """,
            (company_id, external_id, title, location, department, url, posted_at, description, now, now),
        )
        row = c.execute(
            "SELECT id FROM jobs WHERE company_id = ? AND external_id = ?",
            (company_id, external_id),
        ).fetchone()
        return row["id"], is_new


def get_new_jobs_since(since: datetime) -> list[dict[str, Any]]:
    """Return jobs where first_seen_at >= since, with company name joined."""
    since_str = since.isoformat()
    with _conn() as c:
        rows = c.execute(
            """
            SELECT j.id, j.company_id, j.external_id, j.title, j.location, j.department, j.url,
                   j.posted_at, j.description, j.first_seen_at, c.name AS company_name
            FROM jobs j
            JOIN companies c ON c.id = j.company_id
            WHERE j.first_seen_at >= ?
            ORDER BY j.first_seen_at DESC
            """,
            (since_str,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_jobs_first_seen_within_days(days: int) -> list[dict[str, Any]]:
    """Jobs whose first_seen_at is within the last `days` days (for filter breakdown / analytics)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = cutoff.isoformat()
    with _conn() as c:
        rows = c.execute(
            """
            SELECT j.id, j.company_id, j.external_id, j.title, j.location, j.department, j.url,
                   j.posted_at, j.description, j.first_seen_at, c.name AS company_name
            FROM jobs j
            JOIN companies c ON c.id = j.company_id
            WHERE j.first_seen_at >= ?
            ORDER BY j.first_seen_at DESC
            """,
            (since_str,),
        ).fetchall()
    return [dict(r) for r in rows]


def start_run() -> int:
    """Record run start; return run id."""
    now = _now()
    with _conn() as c:
        c.execute("INSERT INTO runs (started_at) VALUES (?)", (now,))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def finish_run(run_id: int, companies_checked: int, new_jobs_count: int) -> None:
    """Update run with finished_at and counts."""
    now = _now()
    with _conn() as c:
        c.execute(
            "UPDATE runs SET finished_at = ?, companies_checked = ?, new_jobs_count = ? WHERE id = ?",
            (now, companies_checked, new_jobs_count, run_id),
        )


def run_database_cleanup(cfg: dict) -> dict[str, Any]:
    """
    Prune old rows to keep the SQLite file small (e.g. CI cache / state branch).
    Config from watchlist `db_cleanup:` (see load_db_cleanup).
    Returns stats: jobs_deleted, runs_deleted, companies_deleted, vacuumed, skipped.
    """
    out: dict[str, Any] = {
        "skipped": False,
        "jobs_deleted": 0,
        "runs_deleted": 0,
        "companies_deleted": 0,
        "descriptions_cleared": 0,
        "vacuumed": False,
    }
    if not cfg.get("enabled", True):
        out["skipped"] = True
        return out

    jobs_days = cfg.get("delete_jobs_last_seen_older_than_days")
    runs_days = cfg.get("delete_runs_older_than_days")

    with _conn() as c:
        if isinstance(jobs_days, int) and jobs_days > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=jobs_days)).isoformat()
            cur = c.execute("DELETE FROM jobs WHERE last_seen_at < ?", (cutoff,))
            out["jobs_deleted"] = cur.rowcount or 0

        if cfg.get("delete_orphan_companies"):
            cur = c.execute(
                """
                DELETE FROM companies WHERE id NOT IN (SELECT DISTINCT company_id FROM jobs)
                """
            )
            out["companies_deleted"] = cur.rowcount or 0

        if isinstance(runs_days, int) and runs_days > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=runs_days)).isoformat()
            cur = c.execute("DELETE FROM runs WHERE started_at < ?", (cutoff,))
            out["runs_deleted"] = cur.rowcount or 0

        if cfg.get("strip_job_descriptions", True):
            cur = c.execute("UPDATE jobs SET description = NULL WHERE description IS NOT NULL")
            out["descriptions_cleared"] = cur.rowcount or 0

    if cfg.get("vacuum", True):
        # VACUUM cannot run inside a transaction with pending changes in some cases; use a fresh connection.
        vac = sqlite3.connect(str(_DB_PATH))
        try:
            vac.execute("VACUUM")
            vac.commit()
            out["vacuumed"] = True
        finally:
            vac.close()

    return out
