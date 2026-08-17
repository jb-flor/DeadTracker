# DeadTracker

A live game tracker for [Deadlock](https://www.playdeadlock.com/), built on top of the community-run [deadlock-api.com](https://api.deadlock-api.com/docs) REST API.

## What's here

- **`DeadTracker.py`** — FastAPI backend. Serves the frontend and two JSON endpoints:
  - `GET /players/{account_id}/matches` — recent match history, enriched with hero names and rank labels.
  - `GET /players/{account_id}/live` — whether the account is currently in a match, and which hero/team if so.
- **`cache.py`** — SQLite-backed cache (`deadtracker.db`, created automatically, no server setup required) for heroes, ranks, match history, and live status, each with its own TTL. Also tracks which accounts have been queried, so the background refresh loop knows what to keep warm.
- **`fetch_match_history.py`** — the underlying deadlock-api.com client functions (match history, heroes, ranks, active matches, Steam profile search), plus a standalone CLI script for quick lookups without running the server.
- **`static/index.html`** — a single-page frontend (no build step) that polls the two endpoints above and displays live status + a recent-matches table.

A background task inside the FastAPI app sweeps every tracked account every 10 minutes (`DEADTRACKER_REFRESH_INTERVAL_S` env var to override), so match history stays fresh even with no active viewers.

## Setup

```
pip install -r requirements.txt
uvicorn DeadTracker:app --reload
```

Then open `http://127.0.0.1:8000/` and enter a Steam account_id (SteamID3 — see below for how to get one).

For a quick one-off lookup without the server:

```
python fetch_match_history.py <account_id_or_steam_name>
```

### Finding your account_id

deadlock-api.com identifies players by `account_id` (SteamID3), not your Steam profile URL directly. Convert your SteamID64 (the number in `steamcommunity.com/profiles/<this>`) with:

```
account_id = steamid64 - 76561197960265728
```

## Design notes

- **No bot-friending required.** Full match-history accuracy on deadlock-api.com technically requires friending one of their Steam bots, but their ClickHouse store already passively captures the vast majority of matches network-wide. We accept the rare gap/delay in favor of zero-friction onboarding.
- **SQLite, not a hosted DB.** Chosen specifically so nobody has to stand up a database server to run this.
- **Live status is polling-based**, not push/WebSocket. deadlock-api.com does have an SSE endpoint (`/v1/matches/demo/live/query`) for live in-match event detail, but it requires querying a raw demo/broadcast schema and has tight rate limits — treated as a future stretch feature, not core to basic live/offline tracking.

## Possible next steps

- Stats layer: win rate over time, rolling K/D, hero performance, session vs. all-time comparisons.
- Charts / UI polish on top of the stats layer.
- Steam URL entry directly in the frontend (currently requires a numeric account_id).
- Optional "connect for full history" bot-friend flow via a `steam://friends/add/<steamid64>` link.
- Track friends/teammates alongside your own account.
