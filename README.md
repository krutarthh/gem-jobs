# Gold Gem Jobs Tracker

Catch new job postings **before** LinkedIn/Indeed by scraping direct ATS and career pages, storing results in SQLite, and notifying via Discord when new Toronto SWE/intern/new-grad jobs appear.

## How it works

1. **Watchlist** — You maintain a list of company career URLs in `config/watchlist.yaml`.
2. **Scrape** — The tool checks each URL every N minutes (default 15), detects ATS type (Greenhouse, Lever, Ashby), and fetches jobs from public JSON APIs where possible.
3. **Diff** — New jobs (first time seen) are stored; only new postings trigger alerts.
4. **Filter** — Alerts are sent only for jobs matching Toronto (or GTA/remote Canada), intern/new grad/SWE I level, and optional title keywords.
5. **Notify** — Discord webhook sends an embed per new matching job.

## Setup

1. **Clone and install**

   ```bash
   cd gold-gem-jobs
   python -m venv .venv
   source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. **Discord webhook**

   - In your Discord server: Server Settings → Integrations → Webhooks → New Webhook.
   - Copy the webhook URL.

3. **Environment**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set:

   - `DISCORD_WEBHOOK_URL` — your webhook URL.
   - `SCRAPE_INTERVAL_MINUTES` — e.g. `15` (or `5` for more frequent checks).

## Adding companies

Edit `config/watchlist.yaml`. Add entries under `companies`:

```yaml
companies:
  - name: Company Name
    careers_url: https://company.com/careers
```

If the career page redirects to Greenhouse/Lever/Ashby, the tool will detect it and use the public JSON API. For **custom domains** (e.g. careers.toasttab.com) that use Greenhouse but don’t redirect, add the ATS and board ID so jobs are fetched from the API:

```yaml
  - name: Toast
    careers_url: https://careers.toasttab.com/
    ats_type: greenhouse
    board_id: toast
```

**Making sure every site works**

1. **Auto-detection** — The scraper detects ATS from (a) the final URL after redirects and (b) the page HTML (e.g. Greenhouse embeds). Many sites work with no extra config.
2. **Check detection** — Run:
   ```bash
   python scripts/detect_ats_for_watchlist.py
   ```
   It prints each company’s ATS and job count. If you see `generic`, that site is using the fallback HTML scraper (which can miss jobs on JS-heavy pages).
3. **Add known boards** — If you know a company uses Greenhouse/Lever/Ashby (e.g. from their job URL or support), add `ats_type` and `board_id` to that company in `config/watchlist.yaml`. Common Greenhouse board IDs are often the company name (e.g. `stripe`, `figma`, `vercel`).

## Running

- **Once (manual or cron):**

  ```bash
  python -m src.main
  ```

- **Continuously (every N minutes):**

  ```bash
  python scripts/run_scheduler.py
  ```

For 24/7 use, run the scheduler on a cheap VPS (e.g. $5/month) or use a cron job that runs `python -m src.main` every 5–30 minutes.

## Deploy with GitHub Actions (run every 15 min)

The repo includes a workflow that runs the scraper **every 15 minutes** on GitHub’s servers. No server to manage; the SQLite DB is persisted between runs via cache.

1. **Push the repo to GitHub**
   - Create a new repo on GitHub (e.g. `gold-gem-jobs`).
   - From your machine:
   ```bash
   cd gold-gem-jobs
   git init
   git add .
   git commit -m "Initial commit: Gold Gem Jobs tracker"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/gold-gem-jobs.git
   git push -u origin main
   ```

2. **Add your Discord webhook as a secret**
   - In the repo: **Settings → Secrets and variables → Actions**.
   - **New repository secret**: name `DISCORD_WEBHOOK_URL`, value = your webhook URL (same as in `.env`).

3. **Enable the workflow**
   - **Actions** tab → select **“Run scraper every 15 min”** → **Run workflow** (optional; it will also run on the schedule).
   - The workflow runs every 15 minutes via `schedule`; you can also trigger it manually with **Run workflow**.

The first run will have an empty DB (all jobs are “new”); you may get many Discord alerts. Later runs only alert when a job appears for the first time.

## Filters

Filters are defined in `config/watchlist.yaml` under `filters`:

- **locations** — Job location text must match one of these (e.g. Toronto, GTA, Remote - Canada).
- **level_keywords** — Title or department must contain one of these (e.g. intern, new grad, SWE I).
- **title_keywords** — If non-empty, title or department must contain one of these (e.g. software, backend).

Optional filter flags (under `filters` in the YAML):

- **allow_empty_location** (default: false) — If true, jobs with no location (e.g. from the generic scraper) pass the location check instead of being excluded.
- **require_location_field_match** (default: false) — If true, at least one location keyword must appear in the job’s location field (not only in title/department).

Only jobs passing all filters are included in Discord alerts.

## Project layout

- `config/watchlist.yaml` — Company list and filter config.
- `src/main.py` — Entry point: load config, scrape, upsert, filter, notify.
- `src/db.py` — SQLite schema and “new since last run” queries.
- `src/ats/` — ATS detector and fetchers (Greenhouse, Lever, Ashby, generic).
- `src/filters.py` — Location/level/keyword filtering.
- `src/notify.py` — Discord webhook.
- `scripts/run_scheduler.py` — Loop with sleep for continuous runs.
- `scripts/detect_ats_for_watchlist.py` — Report ATS and job count per company.
- `.github/workflows/run-scraper.yml` — GitHub Actions: run scraper every 15 min.
- `data/jobs.db` — SQLite DB (created automatically; in `.gitignore`).

## Optional env

- `WATCHLIST_PATH` — Override path to watchlist YAML.
- `DB_PATH` — Override path to SQLite file.
