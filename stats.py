"""
Pure computation over already-enriched match history (see DeadTracker.py's
get_matches route for the enrichment shape). No network/DB access here.
"""

WIN = 1
LOSS = 2


def _summarize(matches: list[dict]) -> dict:
    if not matches:
        return {
            "games": 0,
            "wins": 0,
            "win_rate": None,
            "avg_kills": None,
            "avg_deaths": None,
            "avg_assists": None,
            "avg_kda": None,
        }

    wins = sum(1 for m in matches if m["player_match_outcome"] == WIN)
    avg_kills = sum(m["player_kills"] for m in matches) / len(matches)
    avg_deaths = sum(m["player_deaths"] for m in matches) / len(matches)
    avg_assists = sum(m["player_assists"] for m in matches) / len(matches)

    return {
        "games": len(matches),
        "wins": wins,
        "win_rate": round(wins / len(matches) * 100, 1),
        "avg_kills": round(avg_kills, 1),
        "avg_deaths": round(avg_deaths, 1),
        "avg_assists": round(avg_assists, 1),
        "avg_kda": round((avg_kills + avg_assists) / avg_deaths, 2) if avg_deaths > 0 else None,
    }


def compute_stats(matches: list[dict], recent_n: int = 20) -> dict:
    """`matches` must already be enriched with `hero_name` and sorted newest-first
    (both true of what DeadTracker.py's /players/{account_id}/matches returns)."""
    scored = [m for m in matches if m["player_match_outcome"] in (WIN, LOSS)]
    recent = scored[:recent_n]

    by_hero: dict[str, list[dict]] = {}
    for m in scored:
        by_hero.setdefault(m["hero_name"], []).append(m)

    hero_breakdown = [
        {"hero_name": name, **_summarize(hero_matches)}
        for name, hero_matches in sorted(by_hero.items(), key=lambda kv: len(kv[1]), reverse=True)
    ]

    return {
        "all_time": _summarize(scored),
        "recent": _summarize(recent),
        "recent_n": recent_n,
        "by_hero": hero_breakdown,
    }
