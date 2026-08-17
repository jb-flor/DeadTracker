"""
FastAPI wrapper around the deadlock-api.com match history fetch, backed by
a local SQLite cache (see cache.py) so repeated requests/refreshes don't
hammer the upstream API.

A background task also sweeps every tracked account (anyone who has hit
/players/{account_id}/matches at least once) on a fixed interval, so match
history stays fresh even when nobody is actively requesting it.

Run with:
    uvicorn DeadTracker:app --reload

Then visit http://127.0.0.1:8000/players/<account_id>/matches
"""

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse

import cache
from fetch_match_history import fetch_active_matches, fetch_heroes, fetch_match_history, fetch_ranks, format_rank

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("deadtracker.refresh")

BACKGROUND_REFRESH_INTERVAL_S = int(os.environ.get("DEADTRACKER_REFRESH_INTERVAL_S", 10 * 60))
STATIC_DIR = Path(__file__).parent / "static"


def get_heroes(conn) -> dict[int, str]:
    heroes = cache.get_cached_heroes(conn)
    if heroes is None:
        heroes = fetch_heroes()
        cache.set_cached_heroes(conn, heroes)
    return heroes


def get_ranks(conn) -> dict[int, str]:
    ranks = cache.get_cached_ranks(conn)
    if ranks is None:
        ranks = fetch_ranks()
        cache.set_cached_ranks(conn, ranks)
    return ranks


def refresh_tracked_accounts() -> None:
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        get_heroes(conn)
        get_ranks(conn)
        account_ids = cache.get_tracked_accounts(conn)
        logger.info("Background sweep starting for %d tracked account(s)", len(account_ids))
        for account_id in account_ids:
            try:
                matches = fetch_match_history(account_id)
                cache.set_cached_match_history(conn, account_id, matches)
                logger.info("Background sweep refreshed account_id=%s (%d matches)", account_id, len(matches))
            except Exception:
                logger.exception("Background refresh failed for account_id=%s", account_id)
    finally:
        conn.close()


async def background_refresh_loop() -> None:
    while True:
        await asyncio.to_thread(refresh_tracked_accounts)
        await asyncio.sleep(BACKGROUND_REFRESH_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(background_refresh_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="DeadTracker API", lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


def get_match_history(conn, account_id: int, refresh: bool) -> list[dict]:
    matches = None if refresh else cache.get_cached_match_history(conn, account_id)
    if matches is None:
        matches = fetch_match_history(account_id)
        cache.set_cached_match_history(conn, account_id, matches)
    return matches


@app.get("/players/{account_id}/matches")
def get_matches(account_id: int, refresh: bool = Query(False, description="Bypass cache and refetch from deadlock-api.com")):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        cache.track_account(conn, account_id)
        heroes = get_heroes(conn)
        ranks = get_ranks(conn)
        matches = get_match_history(conn, account_id, refresh)
    finally:
        conn.close()

    enriched = [
        {
            **m,
            "hero_name": heroes.get(m["hero_id"], f"hero_id {m['hero_id']}"),
            "rank_label": format_rank(m.get("ranked_display_badge"), ranks),
        }
        for m in matches
    ]
    return {"account_id": account_id, "matches_returned": len(enriched), "matches": enriched}


def get_live_status(conn, account_id: int, refresh: bool) -> dict:
    status = None if refresh else cache.get_cached_live_status(conn, account_id)
    if status is not None:
        return status

    heroes = get_heroes(conn)
    active = fetch_active_matches([account_id])
    match = active[0] if active else None
    player = None
    if match is not None:
        player = next((p for p in match.get("players", []) if p.get("account_id") == account_id), None)

    if match is None or player is None:
        status = {"live": False, "match": None}
    else:
        hero_id = player.get("hero_id")
        status = {
            "live": True,
            "match": {
                "match_id": match.get("match_id"),
                "start_time": match.get("start_time"),
                "duration_s": match.get("duration_s"),
                "hero_name": heroes.get(hero_id, f"hero_id {hero_id}") if hero_id is not None else None,
                "team": player.get("team"),
                "spectators": match.get("spectators"),
            },
        }

    cache.set_cached_live_status(conn, account_id, status)
    return status


@app.get("/players/{account_id}/live")
def get_live(account_id: int, refresh: bool = Query(False, description="Bypass cache and refetch from deadlock-api.com")):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        cache.track_account(conn, account_id)
        status = get_live_status(conn, account_id, refresh)
    finally:
        conn.close()

    return {"account_id": account_id, **status}
