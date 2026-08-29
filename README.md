# DeadTracker

A live game tracker for [Deadlock](https://www.playdeadlock.com/), built on the community-run [deadlock-api.com](https://api.deadlock-api.com/docs) REST API.

## What's here

- **`DeadTracker.py`** — FastAPI backend. Serves the frontend and these JSON endpoints:
  - `GET /resolve` — resolves a Steam profile URL, SteamID64, raw account_id, or persona name to an `account_id`.
  - `GET /players/{account_id}/matches` — recent match history, rank labels, heroes played, and a decoded match mode (`match_mode_label`/`is_ranked`) for separating ranked from standard games.
  - `GET /players/{account_id}/live` — whether the player is currently in a match, labels hero and team.
  - `GET /players/live-batch` — the same live-status check for a comma-separated list of account_ids in one call.
  - `GET /players/{account_id}/stats` — win rate, KDA, and per-hero breakdown, both all-time and over the most recent N games, split into `ranked`/`standard` sections.
  - `GET /matches/{match_id}/players/{account_id}/items` — a player's build for one match: item purchase timing, ability upgrade timing, and a net worth/K/D/A time series sampled through the match.
  - `GET /compare/build` — the same build timeline for two players' matches side by side (`a_match_id`, `a_account_id`, `b_match_id`, `b_account_id`).
  - `GET /compare/performance` — net worth and K/D/A curves over relative game time for two players on given heroes, from their last 30 days of matches.
  - `GET /heroes` — currently-released heroes, for populating a picker.
  - `GET /heroes/{hero_id}/winrate` — community-wide win rate for a hero, broken down by rank tier plus an overall/unranked summary.
  - `GET /heroes/{hero_id}/trend` — community-wide weekly win rate for a hero, to see meta shifts across patches.
  - `GET /heroes/{hero_id}/matchups` — best/toughest hero matchups by head-to-head win rate.
  - `GET /players/{account_id}/percentile` — real rank percentile ("better than X% of ranked players"), computed from deadlock-api's population-wide badge distribution.
  - `GET /patches` — Deadlock's patch notes, pulled live from Steam's news feed — no manual upkeep needed as new patches ship.
- **`cache.py`** — SQLite-backed cache (`deadtracker.db`) for everything the app fetches from deadlock-api.com (heroes, ranks, items, match history/metadata, live status, performance curves, hero meta-stats, badge distribution, patch notes), each with its own TTL. Community-wide/meta datasets share one generic `blob_cache` table rather than a dedicated table per type. Also tracks which accounts have been queried, so the background refresh loop knows what to keep active.
- **`fetch_match_history.py`** — the underlying deadlock-api.com client functions
- **`stats.py`** — pure computation over already-fetched match history (win rate, KDA, per-hero breakdown, both all-time and over the recent window). No network or DB access.
- **`static/index.html`** — a single-page frontend that resolves whatever you type into the input, then polls the endpoints above and displays:
  - Live status, a Friends panel tracking other players' live status alongside your own (saved locally in the browser), and a "Get Complete Data" panel pointing at deadlock-api's official [ingest tool](https://deadlock-api.com/ingest-cache) for closing the match-history/live-tracking coverage gaps.
  - Stats split into collapsible Ranked/Standard sections (each with its own win/loss trend chart, all-time/recent win rate + KDA, and by-hero breakdown), plus a real rank-percentile histogram (where you fall in the population of ranked players) and community-wide hero win rates by rank — plus, per hero, a weekly win-rate trend chart and best/toughest matchup bars.
  - Match History, also split into collapsible Ranked/Standard sections, each still grouped by week internally.
  - A per-match view — a team-vs-enemy net worth chart (when did the game actually swing), a net-worth/K-D-A curve *for that specific match* (not an aggregate), and item purchases/sales plus ability level-ups plotted against match time — the chart is the only way to inspect the build now (no list underneath), so every point has a styled hover tooltip with the item's in-game shop icon, name, and timing. Shows for any match you click, and for both players at once in Compare Build (alongside the separate 30-day aggregate net worth comparison curve).
  - A collapsible patch notes feed that highlights and surfaces changes to whichever heroes you've played most in your recent matches.

A background task inside the FastAPI app sweeps tracked players/accounts every 10 minutes (`DEADTRACKER_REFRESH_INTERVAL_S` env var to override), so match history and patch notes stay fresh even with no active viewers.

## Setup

```
pip install -r requirements.txt
uvicorn DeadTracker:app --reload
```

Then open `http://127.0.0.1:8000/` and enter a Steam profile URL, SteamID64, account_id, or persona name.

For a quick one-off lookup without the server:

```
python fetch_match_history.py <account_id_or_steam_name>
```