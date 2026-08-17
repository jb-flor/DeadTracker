# DeadTracker

A live game tracker for [Deadlock](https://www.playdeadlock.com/), built on the community-run [deadlock-api.com](https://api.deadlock-api.com/docs) REST API.

## What's here

- **`DeadTracker.py`** — FastAPI backend. Serves the frontend and two JSON endpoints:
  - `GET /players/{account_id}/matches` — recent match history, enriched with hero names and rank labels.
  - `GET /players/{account_id}/live` — whether the player is currently in a match, identifies hero and team.
- **`cache.py`** — SQLite-backed cache (`deadtracker.db`) for heroes, ranks, match history, and live status, each with its own TTL. Also tracks which accounts have been queried, so the background refresh loop knows what to keep active.
- **`fetch_match_history.py`** — the underlying deadlock-api.com client functions (match history, heroes, ranks, active matches, Steam profile search), plus a standalone CLI script for quick lookups without running a server.
- **`static/index.html`** — a single-page frontend that polls the two endpoints above and displays live status + a recent-matches table.

A background task inside the FastAPI app sweeps tracked players/accounts every 10 minutes (`DEADTRACKER_REFRESH_INTERVAL_S` env var to override), so match history stays fresh even with no active viewers.

## Setup

```
pip install -r requirements.txt
uvicorn DeadTracker:app --reload
```

Then open `http://127.0.0.1:8000/` and enter a Steam account_id.

For a quick one-off lookup without the server:

```
python fetch_match_history.py <account_id_or_steam_name>
```

## Possible next steps

- Stats layer: win rate over time, rolling K/D, hero performance, session vs. all-time comparisons.
- Charts / UI polish on top of the stats layer.
- Steam URL entry directly in the frontend (currently requires a numeric account_id).
- Optional "connect for full history" bot-friend flow via a `steam://friends/add/<steamid64>` link.
- Track friends/teammates alongside your own account.
