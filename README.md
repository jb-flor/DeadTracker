# DeadTracker

A live game tracker for [Deadlock](https://www.playdeadlock.com/), built on the community-run [deadlock-api.com](https://api.deadlock-api.com/docs) REST API.

## What's here

- **`DeadTracker.py`** — FastAPI backend. Serves the frontend and these JSON endpoints:
  - `GET /resolve` — resolves a Steam profile URL, SteamID64, raw account_id, or persona name to an `account_id` (or a list of candidates if the name is ambiguous).
  - `GET /players/{account_id}/matches` — recent match history, enriched with hero names and rank labels.
  - `GET /players/{account_id}/live` — whether the player is currently in a match, identifies hero and team.
  - `GET /players/{account_id}/stats` — win rate, KDA, and per-hero breakdown, both all-time and over the most recent N games.
- **`cache.py`** — SQLite-backed cache (`deadtracker.db`) for heroes, ranks, match history, and live status, each with its own TTL. Also tracks which accounts have been queried, so the background refresh loop knows what to keep active.
- **`fetch_match_history.py`** — the underlying deadlock-api.com client functions (match history, heroes, ranks, active matches, Steam profile search/resolution), plus a standalone CLI script for quick lookups without running a server.
- **`stats.py`** — pure computation over already-fetched match history (win rate, KDA, per-hero breakdown). No network or DB access.
- **`static/index.html`** — a single-page frontend that resolves whatever you type into the input, then polls the endpoints above and displays live status, stats, and a recent-matches table.

A background task inside the FastAPI app sweeps tracked players/accounts every 10 minutes (`DEADTRACKER_REFRESH_INTERVAL_S` env var to override), so match history stays fresh even with no active viewers.

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
- Optional "connect for full history" bot-friend flow via a `steam://friends/add/<steamid64>` link.
- Track friends/teammates alongside your own account.
