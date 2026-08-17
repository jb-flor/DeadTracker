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
import sys

import requests

BASE_URL = "https://api.deadlock-api.com"


def resolve_account_id(query: str) -> int:
    resp = requests.get(
        f"{BASE_URL}/v1/players/steam-search",
        params={"search_query": query, "limit": 5},
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise SystemExit(f"No Steam profiles found for '{query}'")

    if len(results) > 1:
        print(f"Multiple matches for '{query}':")
        for p in results:
            print(f"  account_id={p['account_id']}  {p.get('personaname')}")
        print("Using the first result. Re-run with an explicit account_id to pick another.\n")

    return results[0]["account_id"]


def fetch_match_history(account_id: int) -> list[dict]:
    resp = requests.get(f"{BASE_URL}/v1/players/{account_id}/match-history")
    resp.raise_for_status()
    return resp.json()


def fetch_heroes() -> dict[int, str]:
    resp = requests.get(f"{BASE_URL}/v1/assets/heroes")
    resp.raise_for_status()
    return {hero["id"]: hero["name"] for hero in resp.json()}


def fetch_ranks() -> dict[int, str]:
    resp = requests.get(f"{BASE_URL}/v1/assets/ranks")
    resp.raise_for_status()
    return {rank["tier"]: rank["name"] for rank in resp.json()}


def fetch_active_matches(account_ids: list[int]) -> list[dict]:
    resp = requests.get(
        f"{BASE_URL}/v1/matches/active",
        params={"account_ids": ",".join(str(a) for a in account_ids)},
    )
    resp.raise_for_status()
    return resp.json()


SUBTIER_NUMERALS = {0: "", 1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}


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
