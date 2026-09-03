"""
Fetch and print recent Deadlock match history for a player.

Usage:
    python fetch_match_history.py <account_id_or_steam_name>

If the argument parses as an integer, it's treated as a SteamID3 account_id
and passed straight to the match-history endpoint. Otherwise it's treated as
a Steam persona name and resolved via the steam-search endpoint first.

API docs: https://api.deadlock-api.com/docs
"""

import json
import re
import sys

import requests

BASE_URL = "https://api.deadlock-api.com"

STEAMID64_OFFSET = 76561197960265728


def search_steam_profiles(query: str) -> list[dict]:
    resp = requests.get(
        f"{BASE_URL}/v1/players/steam-search",
        params={"search_query": query, "limit": 25},
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    results = resp.json()

    exact = [r for r in results if (r.get("personaname") or "").lower() == query.strip().lower()]
    return exact if exact else results


def resolve_account_id(query: str) -> int:
    results = search_steam_profiles(query)
    if not results:
        raise SystemExit(f"No Steam profiles found for '{query}'")

    if len(results) > 1:
        print(f"Multiple matches for '{query}':")
        for p in results:
            print(f"  account_id={p['account_id']}  {p.get('personaname')}")
        print("Using the first result. Re-run with an explicit account_id to pick another.\n")

    return results[0]["account_id"]


def parse_account_id_input(raw: str) -> int | None:
    """Best-effort, network-free extraction of an account_id from a raw account_id,
    a SteamID64, or a full steamcommunity.com/profiles/<id> URL. Returns None if
    `raw` doesn't look like any of those (e.g. a name or a vanity URL), meaning a
    name search is needed instead."""
    raw = raw.strip()

    match = re.search(r"steamcommunity\.com/profiles/(\d+)", raw)
    if match:
        return int(match.group(1)) - STEAMID64_OFFSET

    if raw.isdigit():
        value = int(raw)
        return value - STEAMID64_OFFSET if value >= STEAMID64_OFFSET else value

    return None


def extract_vanity_name(raw: str) -> str | None:
    """Pulls the vanity name out of a steamcommunity.com/id/<name> URL, if present."""
    match = re.search(r"steamcommunity\.com/id/([^/\s]+)", raw.strip())
    return match.group(1) if match else None


def fetch_match_history(account_id: int) -> list[dict]:
    resp = requests.get(f"{BASE_URL}/v1/players/{account_id}/match-history")
    resp.raise_for_status()
    return resp.json()


def fetch_heroes() -> dict[int, str]:
    resp = requests.get(f"{BASE_URL}/v1/assets/heroes")
    resp.raise_for_status()
    return {hero["id"]: hero["name"] for hero in resp.json()}


def fetch_released_hero_ids() -> list[int]:
    """Hero IDs that are actually live in the game right now - excludes
    heroes still in development/disabled (e.g. unreleased heroes datamined
    into the API before their official release)."""
    resp = requests.get(f"{BASE_URL}/v1/assets/heroes")
    resp.raise_for_status()
    return [hero["id"] for hero in resp.json() if not hero.get("disabled") and not hero.get("in_development")]


def fetch_ranks() -> dict[int, str]:
    resp = requests.get(f"{BASE_URL}/v1/assets/ranks")
    resp.raise_for_status()
    return {rank["tier"]: rank["name"] for rank in resp.json()}


def fetch_items() -> dict[int, dict]:
    resp = requests.get(f"{BASE_URL}/v1/assets/items")
    resp.raise_for_status()
    return {
        item["id"]: {"name": item["name"], "type": item.get("type"), "image": item.get("shop_image")}
        for item in resp.json()
    }


def fetch_match_metadata(match_id: int) -> dict:
    resp = requests.get(f"{BASE_URL}/v1/matches/{match_id}/metadata")
    resp.raise_for_status()
    return resp.json()


def fetch_patches() -> list[dict]:
    """Deadlock's patch notes, aggregated by deadlock-api.com from Steam's news
    feed for the game (plus their forum). Newest first."""
    resp = requests.get(f"{BASE_URL}/v2/patches")
    resp.raise_for_status()
    return resp.json()


def fetch_hero_rank_stats() -> list[dict]:
    """Community-wide win/loss counts per hero, bucketed by average match badge
    (rank tier). One row per (hero_id, bucket); bucket=0 means unranked, other
    buckets are badge values (tier*10 + subtier, same encoding as ranked_display_badge).
    Uses the API's defaults: last 30 days, normal game mode, ranked+unranked matches."""
    resp = requests.get(
        f"{BASE_URL}/v1/analytics/hero-stats",
        params={"bucket": "avg_badge"},
    )
    resp.raise_for_status()
    return resp.json()


def fetch_hero_trend() -> list[dict]:
    """Community-wide win/loss counts per hero, bucketed by week. One row per
    (hero_id, bucket); bucket is a Unix timestamp for the start of that week."""
    resp = requests.get(
        f"{BASE_URL}/v1/analytics/hero-stats",
        params={"bucket": "start_time_week"},
    )
    resp.raise_for_status()
    return resp.json()


def fetch_hero_counter_stats() -> list[dict]:
    """Community-wide head-to-head win/loss counts for every hero_id vs
    enemy_hero_id pairing (both heroes present in the same match, opposing
    teams)."""
    resp = requests.get(f"{BASE_URL}/v1/analytics/hero-counter-stats")
    resp.raise_for_status()
    return resp.json()


def fetch_badge_distribution() -> list[dict]:
    """Real player counts per rank badge - {badge_level, total_matches, unique_players}
    for every rank tier/subtier. Used to compute a genuine rank percentile
    (deadlock-api's scoreboard `rank` field is not usable for this - see
    project memory for why)."""
    resp = requests.get(f"{BASE_URL}/v1/analytics/badge-distribution")
    resp.raise_for_status()
    return resp.json()


def fetch_performance_curve(account_id: int, hero_id: int) -> list[dict]:
    """Average net worth / K/D/A over relative game-time (0-100%, in buckets of 10),
    aggregated across the account's last 30 days of matches on the given hero.
    NOTE: pass one account_id at a time - deadlock-api averages multiple account_ids
    together into a single combined curve rather than returning one curve per player."""
    resp = requests.get(
        f"{BASE_URL}/v1/analytics/player-performance-curve",
        params={"account_ids": account_id, "hero_ids": hero_id, "resolution": 10},
    )
    resp.raise_for_status()
    return resp.json()


def fetch_active_matches(account_ids: list[int]) -> list[dict]:
    resp = requests.get(
        f"{BASE_URL}/v1/matches/active",
        params={"account_ids": ",".join(str(a) for a in account_ids)},
    )
    resp.raise_for_status()
    return resp.json()


SUBTIER_NUMERALS = {0: "", 1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}

# Order matches deadlock-api's ActiveMatchMode enum (index = raw match_mode int).
MATCH_MODE_LABELS = {
    0: "Invalid",
    1: "Unranked",
    2: "PrivateLobby",
    3: "CoopBot",
    4: "Ranked",
    5: "ServerTest",
    6: "Tutorial",
    7: "HeroLabs",
    8: "NewPlayerPlacement",
}


def format_match_mode(match_mode: int | None) -> str:
    return MATCH_MODE_LABELS.get(match_mode, f"mode {match_mode}")


def format_game_mode(game_mode_parsed: str | None) -> str:
    """deadlock-api's active-match data gives the game mode as an already-parsed
    enum name like 'KECitadelGameModeStreetBrawl' - strip the prefix and space
    out the CamelCase for display (-> 'Street Brawl')."""
    if not game_mode_parsed:
        return "Unknown"
    name = game_mode_parsed.removeprefix("KECitadelGameMode")
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name).strip()


def format_rank(badge: int | None, ranks_by_tier: dict[int, str]) -> str:
    if badge is None:
        return "-"
    tier, subtier = divmod(badge, 10)
    name = ranks_by_tier.get(tier, f"tier {tier}")
    numeral = SUBTIER_NUMERALS.get(subtier)
    if numeral is None:
        return f"{name} (subtier {subtier})"
    return f"{name} {numeral}".rstrip()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: python {sys.argv[0]} <account_id_or_steam_name>")

    arg = sys.argv[1]
    account_id = int(arg) if arg.isdigit() else resolve_account_id(arg)

    matches = fetch_match_history(account_id)
    print(f"account_id={account_id}  matches_returned={len(matches)}\n")

    if not matches:
        return

    print("--- Raw shape of most recent match ---")
    print(json.dumps(matches[0], indent=2))

    print("\n--- Recent matches ---")
    heroes = fetch_heroes()
    ranks_by_tier = fetch_ranks()

    outcome_labels = {0: "invalid", 1: "win", 2: "loss", 3: "penalized", 4: "penalized_party", 5: "not_scored"}
    for m in matches[:20]:
        outcome = outcome_labels.get(m["player_match_outcome"], "?")
        duration_min = m["match_duration_s"] // 60
        hero_name = heroes.get(m["hero_id"], f"hero_id {m['hero_id']}")
        rank_label = format_rank(m.get("ranked_display_badge"), ranks_by_tier)
        print(
            f"match_id={m['match_id']}  hero={hero_name:<12}  "
            f"kda={m['player_kills']}/{m['player_deaths']}/{m['player_assists']}  "
            f"{outcome:<8}  {duration_min:>2}m  rank={rank_label}"
        )


if __name__ == "__main__":
    main()
