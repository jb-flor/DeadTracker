# DeadTracker

A live game tracker for [Deadlock](https://www.playdeadlock.com/), built on the community-run [deadlock-api.com](https://api.deadlock-api.com/docs) REST API.

## What's here

- **`DeadTracker.py`** — FastAPI backend. Serves the frontend and these JSON endpoints:
  - `GET /resolve` — resolves a Steam profile URL, SteamID64, raw account_id, or persona name to an `account_id`.
  - `GET /players/{account_id}/matches` — recent match history, rank labels, and heroes played.
  - `GET /players/{account_id}/live` — whether the player is currently in a match, labels hero and team.
  - `GET /players/{account_id}/stats` — win rate, KDA, and per-hero breakdown, both all-time and over the most recent N games.
  - `GET /matches/{match_id}/players/{account_id}/items` — a player's build for one match: item purchase timing and ability upgrade timing.
  - `GET /compare/build` — the same build timeline for two players' matches side by side (`a_match_id`, `a_account_id`, `b_match_id`, `b_account_id`).
  - `GET /compare/performance` — net worth and K/D/A curves over relative game time (0-100%) for two players on given heroes, from their last 30 days of matches.
  - `GET /heroes` — currently-released heroes (excludes anything still in development), for populating a picker.
  - `GET /heroes/{hero_id}/winrate` — community-wide win rate for a hero, broken down by rank tier (each tier's 6 subtiers grouped into I-III / IV-VI) plus an overall/unranked summary.
  - `GET /patches` — Deadlock's patch notes, pulled live from Steam's news feed (deadlock-api.com aggregates it) — no manual upkeep needed as new patches ship.
- **`cache.py`** — SQLite-backed cache (`deadtracker.db`) for heroes, ranks, match history, and live status, each with its own TTL. Also tracks which accounts have been queried, so the background refresh loop knows what to keep active.
- **`fetch_match_history.py`** — the underlying deadlock-api.com client functions (match history, heroes, ranks, active matches, Steam profile search/resolution)
- **`stats.py`** — pure computation over already-fetched match history (win rate, KDA, per-hero breakdown, both all-time and over the recent window). No network or DB access.
- **`static/index.html`** — a single-page frontend that resolves whatever you type into the input, then polls the endpoints above and displays live status, stats, a recent-matches table, a per-match build timeline, a player-vs-player build + net worth comparison, community-wide hero win rates by rank, and a collapsible patch notes feed that highlights and surfaces changes to whichever heroes you've played most in your recent matches.

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

## Possible next steps

- Charts / visual polish on top of the stats layer (currently numeric tiles + a table).
- Role grading / percentile rankings derived from playstyle stats.
- Optional "connect for full history" bot-friend flow via a `steam://friends/add/<steamid64>` link.
- Track friends/teammates alongside your own account.
