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

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

import cache
from fetch_match_history import (
    extract_vanity_name,
    fetch_active_matches,
    fetch_badge_distribution,
    fetch_hero_counter_stats,
    fetch_hero_rank_stats,
    fetch_hero_trend,
    fetch_heroes,
    fetch_items,
    fetch_match_history,
    fetch_match_metadata,
    fetch_patches,
    fetch_performance_curve,
    fetch_ranks,
    fetch_released_hero_ids,
    format_match_mode,
    format_rank,
    parse_account_id_input,
    search_steam_profiles,
)
from stats import compute_stats

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


def get_items(conn) -> dict[int, dict]:
    items = cache.get_cached_items(conn)
    if items is None:
        items = fetch_items()
        cache.set_cached_items(conn, items)
    return items


def get_match_metadata(conn, match_id: int) -> dict:
    data = cache.get_cached_match_metadata(conn, match_id)
    if data is None:
        data = fetch_match_metadata(match_id)
        cache.set_cached_match_metadata(conn, match_id, data)
    return data


def get_performance_curve(conn, account_id: int, hero_id: int) -> list[dict]:
    curve = cache.get_cached_performance_curve(conn, account_id, hero_id)
    if curve is None:
        curve = fetch_performance_curve(account_id, hero_id)
        cache.set_cached_performance_curve(conn, account_id, hero_id, curve)
    return curve


def get_released_hero_ids(conn) -> set[int]:
    hero_ids = cache.get_cached_released_hero_ids(conn)
    if hero_ids is None:
        hero_ids = fetch_released_hero_ids()
        cache.set_cached_released_hero_ids(conn, hero_ids)
    return set(hero_ids)


def get_hero_rank_stats(conn) -> list[dict]:
    stats = cache.get_cached_hero_rank_stats(conn)
    if stats is None:
        stats = fetch_hero_rank_stats()
        cache.set_cached_hero_rank_stats(conn, stats)
    return stats


def get_patches(conn) -> list[dict]:
    patches = cache.get_cached_patches(conn)
    if patches is None:
        patches = fetch_patches()
        cache.set_cached_patches(conn, patches)
    return patches


def get_hero_trend(conn) -> list[dict]:
    trend = cache.get_cached_hero_trend(conn)
    if trend is None:
        trend = fetch_hero_trend()
        cache.set_cached_hero_trend(conn, trend)
    return trend


def get_hero_counter_stats(conn) -> list[dict]:
    stats = cache.get_cached_hero_counter_stats(conn)
    if stats is None:
        stats = fetch_hero_counter_stats()
        cache.set_cached_hero_counter_stats(conn, stats)
    return stats


def get_badge_distribution(conn) -> list[dict]:
    distribution = cache.get_cached_badge_distribution(conn)
    if distribution is None:
        distribution = fetch_badge_distribution()
        cache.set_cached_badge_distribution(conn, distribution)
    return distribution


def refresh_tracked_accounts() -> None:
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        get_heroes(conn)
        get_ranks(conn)
        try:
            get_patches(conn)
        except Exception:
            logger.exception("Background sweep failed to refresh patch notes")
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


@app.get("/resolve")
def resolve_player(query: str = Query(..., min_length=1, description="Steam profile URL, SteamID64, account_id, or persona name")):
    account_id = parse_account_id_input(query)
    if account_id is not None:
        return {"account_id": account_id}

    search_term = extract_vanity_name(query) or query
    results = search_steam_profiles(search_term)
    if not results:
        raise HTTPException(status_code=404, detail=f"No Steam profiles found for '{query}'")
    if len(results) == 1:
        return {"account_id": results[0]["account_id"]}

    return {
        "candidates": [
            {
                "account_id": r["account_id"],
                "personaname": r.get("personaname"),
                "avatar": r.get("avatar"),
            }
            for r in results
        ]
    }


@app.get("/patches")
def list_patches():
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        patches = get_patches(conn)
    finally:
        conn.close()

    return {
        "patches": [
            {
                "title": p.get("title", "").strip(),
                "pub_date": p.get("pub_date"),
                "link": p.get("link"),
                "source": p.get("source"),
                "content": p.get("content"),
            }
            for p in patches
        ]
    }


@app.get("/heroes")
def list_heroes():
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        heroes = get_heroes(conn)
        released = get_released_hero_ids(conn)
    finally:
        conn.close()

    return {
        "heroes": sorted(
            ({"hero_id": hid, "hero_name": name} for hid, name in heroes.items() if hid in released),
            key=lambda h: h["hero_name"],
        )
    }


@app.get("/heroes/{hero_id}/winrate")
def get_hero_winrate(hero_id: int):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        heroes = get_heroes(conn)
        ranks = get_ranks(conn)
        stats = get_hero_rank_stats(conn)
    finally:
        conn.close()

    rows = [row for row in stats if row["hero_id"] == hero_id]
    unranked_row = next((row for row in rows if row["bucket"] == 0), None)
    ranked_rows = [row for row in rows if row["bucket"] != 0 and row["matches"] > 0]

    def summarize(matches: int, wins: int) -> dict:
        return {
            "matches": matches,
            "wins": wins,
            "win_rate": round(wins / matches * 100, 1) if matches else None,
        }

    overall_matches = sum(row["matches"] for row in ranked_rows)
    overall_wins = sum(row["wins"] for row in ranked_rows)

    # Group each tier's 6 subtiers into two halves (I-III, IV-VI) rather than
    # showing all 6 individually - weighted by actual match counts, not a
    # simple average of the per-subtier win rates.
    half_groups: dict[tuple[int, int], dict] = {}
    for row in ranked_rows:
        tier, subtier = divmod(row["bucket"], 10)
        half = 0 if subtier <= 3 else 1
        group = half_groups.setdefault((tier, half), {"matches": 0, "wins": 0})
        group["matches"] += row["matches"]
        group["wins"] += row["wins"]

    def half_label(tier: int, half: int) -> str:
        name = ranks.get(tier, f"tier {tier}")
        return f"{name} I-III" if half == 0 else f"{name} IV-VI"

    by_rank = sorted(
        (
            {"tier": tier, "half": half, "rank_label": half_label(tier, half), **summarize(g["matches"], g["wins"])}
            for (tier, half), g in half_groups.items()
        ),
        key=lambda r: (r["tier"], r["half"]),
    )

    return {
        "hero_id": hero_id,
        "hero_name": heroes.get(hero_id, f"hero_id {hero_id}"),
        "overall": summarize(overall_matches, overall_wins),
        "unranked": summarize(unranked_row["matches"], unranked_row["wins"]) if unranked_row else None,
        "by_rank": by_rank,
    }


@app.get("/heroes/{hero_id}/trend")
def get_hero_trend_route(hero_id: int):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        heroes = get_heroes(conn)
        trend = get_hero_trend(conn)
    finally:
        conn.close()

    rows = sorted((r for r in trend if r["hero_id"] == hero_id and r["matches"] > 0), key=lambda r: r["bucket"])
    weekly = [
        {
            "week_start_unix": row["bucket"],
            "matches": row["matches"],
            "win_rate": round(row["wins"] / row["matches"] * 100, 1) if row["matches"] else None,
        }
        for row in rows
    ]
    return {"hero_id": hero_id, "hero_name": heroes.get(hero_id, f"hero_id {hero_id}"), "weekly": weekly}


MIN_MATCHUP_MATCHES = 200


@app.get("/heroes/{hero_id}/matchups")
def get_hero_matchups(hero_id: int, limit: int = Query(5, ge=1, le=20)):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        heroes = get_heroes(conn)
        stats = get_hero_counter_stats(conn)
    finally:
        conn.close()

    rows = [
        {
            "enemy_hero_id": r["enemy_hero_id"],
            "enemy_hero_name": heroes.get(r["enemy_hero_id"], f"hero_id {r['enemy_hero_id']}"),
            "matches": r["matches_played"],
            "win_rate": round(r["wins"] / r["matches_played"] * 100, 1) if r["matches_played"] else None,
        }
        for r in stats
        if r["hero_id"] == hero_id and r["matches_played"] >= MIN_MATCHUP_MATCHES
    ]

    return {
        "hero_id": hero_id,
        "hero_name": heroes.get(hero_id, f"hero_id {hero_id}"),
        "best_matchups": sorted(rows, key=lambda r: r["win_rate"], reverse=True)[:limit],
        "worst_matchups": sorted(rows, key=lambda r: r["win_rate"])[:limit],
    }


@app.get("/players/{account_id}/percentile")
def get_player_percentile(account_id: int):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        matches = get_match_history(conn, account_id, refresh=False)
        ranks = get_ranks(conn)
        distribution = get_badge_distribution(conn)
    finally:
        conn.close()

    current_badge = next((m.get("ranked_display_badge") for m in matches if m.get("ranked_display_badge")), None)
    if current_badge is None:
        raise HTTPException(status_code=404, detail="No ranked matches found for this account")

    total_players = sum(row["unique_players"] for row in distribution)
    players_below = sum(row["unique_players"] for row in distribution if row["badge_level"] < current_badge)
    percentile_better_than = round(players_below / total_players * 100, 1) if total_players else None

    tier_totals: dict[int, int] = {}
    for row in distribution:
        tier = row["badge_level"] // 10
        tier_totals[tier] = tier_totals.get(tier, 0) + row["unique_players"]

    by_tier = sorted(
        (
            {"tier": tier, "rank_name": ranks.get(tier, f"tier {tier}"), "unique_players": count}
            for tier, count in tier_totals.items()
        ),
        key=lambda r: r["tier"],
    )

    return {
        "account_id": account_id,
        "current_badge": current_badge,
        "rank_label": format_rank(current_badge, ranks),
        "player_tier": current_badge // 10,
        "percentile_better_than": percentile_better_than,
        "by_tier": by_tier,
    }


def get_match_history(conn, account_id: int, refresh: bool) -> list[dict]:
    matches = None if refresh else cache.get_cached_match_history(conn, account_id)
    if matches is None:
        matches = fetch_match_history(account_id)
        cache.set_cached_match_history(conn, account_id, matches)
    return matches


def get_enriched_matches(conn, account_id: int, refresh: bool) -> list[dict]:
    heroes = get_heroes(conn)
    ranks = get_ranks(conn)
    matches = get_match_history(conn, account_id, refresh)
    return [
        {
            **m,
            "hero_name": heroes.get(m["hero_id"], f"hero_id {m['hero_id']}"),
            "rank_label": format_rank(m.get("ranked_display_badge"), ranks),
            "match_mode_label": format_match_mode(m.get("match_mode")),
            "is_ranked": m.get("match_mode") == 4,
        }
        for m in matches
    ]


@app.get("/players/{account_id}/matches")
def get_matches(account_id: int, refresh: bool = Query(False, description="Bypass cache and refetch from deadlock-api.com")):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        cache.track_account(conn, account_id)
        enriched = get_enriched_matches(conn, account_id, refresh)
    finally:
        conn.close()

    return {"account_id": account_id, "matches_returned": len(enriched), "matches": enriched}


@app.get("/players/{account_id}/stats")
def get_stats(
    account_id: int,
    refresh: bool = Query(False, description="Bypass cache and refetch from deadlock-api.com"),
    recent_n: int = Query(20, ge=1, le=100, description="Number of most recent games considered 'recent'"),
):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        cache.track_account(conn, account_id)
        enriched = get_enriched_matches(conn, account_id, refresh)
    finally:
        conn.close()

    ranked = [m for m in enriched if m["is_ranked"]]
    standard = [m for m in enriched if not m["is_ranked"]]
    return {
        "account_id": account_id,
        "ranked": compute_stats(ranked, recent_n=recent_n),
        "standard": compute_stats(standard, recent_n=recent_n),
    }


def get_live_status_batch(conn, account_ids: list[int], refresh: bool) -> dict[int, dict]:
    heroes = get_heroes(conn)
    results: dict[int, dict] = {}
    needs_fetch = []
    for account_id in account_ids:
        status = None if refresh else cache.get_cached_live_status(conn, account_id)
        if status is not None:
            results[account_id] = status
        else:
            needs_fetch.append(account_id)

    if needs_fetch:
        active = fetch_active_matches(needs_fetch)
        for account_id in needs_fetch:
            match = next(
                (m for m in active if any(p.get("account_id") == account_id for p in m.get("players", []))), None
            )
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
            results[account_id] = status

    return results


def get_live_status(conn, account_id: int, refresh: bool) -> dict:
    return get_live_status_batch(conn, [account_id], refresh)[account_id]


def build_player_match_timeline(conn, match_id: int, account_id: int) -> dict:
    heroes = get_heroes(conn)
    items = get_items(conn)
    metadata = get_match_metadata(conn, match_id)

    player = next(
        (p for p in metadata.get("match_info", {}).get("players", []) if p.get("account_id") == account_id),
        None,
    )
    if player is None:
        raise HTTPException(status_code=404, detail=f"account_id {account_id} not found in match {match_id}")

    entries = player.get("items", [])

    purchases = [
        {
            "game_time_s": entry["game_time_s"],
            "item_id": entry["item_id"],
            "item_name": items.get(entry["item_id"], {}).get("name", f"item_id {entry['item_id']}"),
            "item_image": items.get(entry["item_id"], {}).get("image"),
            "sold_time_s": entry["sold_time_s"] or None,
        }
        for entry in entries
        if items.get(entry["item_id"], {}).get("type") == "upgrade"
    ]
    purchases.sort(key=lambda p: p["game_time_s"])

    ability_entries = sorted(
        (e for e in entries if items.get(e["item_id"], {}).get("type") == "ability"),
        key=lambda e: e["game_time_s"],
    )
    level_counts: dict[int, int] = {}
    ability_upgrades = []
    for entry in ability_entries:
        ability_id = entry["item_id"]
        level_counts[ability_id] = level_counts.get(ability_id, 0) + 1
        ability_upgrades.append(
            {
                "game_time_s": entry["game_time_s"],
                "ability_id": ability_id,
                "ability_name": items.get(ability_id, {}).get("name", f"item_id {ability_id}"),
                "level": level_counts[ability_id],
            }
        )

    stats_series = [
        {
            "time_s": s["time_stamp_s"],
            "net_worth": s["net_worth"],
            "kills": s["kills"],
            "deaths": s["deaths"],
            "assists": s["assists"],
        }
        for s in sorted(player.get("stats", []), key=lambda s: s["time_stamp_s"])
    ]

    all_players = metadata.get("match_info", {}).get("players", [])
    player_team = player.get("team")
    timestamps = sorted({s["time_stamp_s"] for p in all_players for s in p.get("stats", [])})
    team_net_worth = []
    for t in timestamps:
        team_sum = 0
        enemy_sum = 0
        for p in all_players:
            sample = next((s for s in p.get("stats", []) if s["time_stamp_s"] == t), None)
            if sample is None:
                continue
            if p.get("team") == player_team:
                team_sum += sample.get("net_worth", 0)
            else:
                enemy_sum += sample.get("net_worth", 0)
        team_net_worth.append({"time_s": t, "team_net_worth": team_sum, "enemy_net_worth": enemy_sum})

    hero_id = player.get("hero_id")
    return {
        "match_id": match_id,
        "account_id": account_id,
        "hero_id": hero_id,
        "hero_name": heroes.get(hero_id, f"hero_id {hero_id}"),
        "match_duration_s": metadata.get("match_info", {}).get("duration_s"),
        "stats": stats_series,
        "team_net_worth": team_net_worth,
        "purchases": purchases,
        "ability_upgrades": ability_upgrades,
    }


@app.get("/matches/{match_id}/players/{account_id}/items")
def get_match_items(match_id: int, account_id: int):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        return build_player_match_timeline(conn, match_id, account_id)
    finally:
        conn.close()


@app.get("/compare/build")
def compare_build(
    a_match_id: int,
    a_account_id: int,
    b_match_id: int,
    b_account_id: int,
):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        return {
            "a": build_player_match_timeline(conn, a_match_id, a_account_id),
            "b": build_player_match_timeline(conn, b_match_id, b_account_id),
        }
    finally:
        conn.close()


@app.get("/compare/performance")
def compare_performance(a_account_id: int, a_hero_id: int, b_account_id: int, b_hero_id: int):
    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        heroes = get_heroes(conn)
        a_curve = get_performance_curve(conn, a_account_id, a_hero_id)
        b_curve = get_performance_curve(conn, b_account_id, b_hero_id)
    finally:
        conn.close()

    return {
        "a": {"account_id": a_account_id, "hero_id": a_hero_id, "hero_name": heroes.get(a_hero_id, f"hero_id {a_hero_id}"), "curve": a_curve},
        "b": {"account_id": b_account_id, "hero_id": b_hero_id, "hero_name": heroes.get(b_hero_id, f"hero_id {b_hero_id}"), "curve": b_curve},
    }


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


@app.get("/players/live-batch")
def get_live_batch(
    account_ids: str = Query(..., description="Comma-separated account_ids"),
    refresh: bool = Query(False, description="Bypass cache and refetch from deadlock-api.com"),
):
    try:
        ids = [int(part) for part in account_ids.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="account_ids must be a comma-separated list of integers")
    if not ids:
        raise HTTPException(status_code=400, detail="No account_ids provided")

    conn = cache.get_conn()
    cache.init_db(conn)
    try:
        statuses = get_live_status_batch(conn, ids, refresh)
    finally:
        conn.close()

    return {"results": [{"account_id": account_id, **statuses[account_id]} for account_id in ids]}
