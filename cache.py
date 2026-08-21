"""
SQLite-backed cache for deadlock-api.com data.

No server setup required - this is a single local file (deadtracker.db)
created automatically on first use via Python's stdlib sqlite3 module.
"""

import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "deadtracker.db"
DB_PATH.parent.mkdir(exist_ok=True)

HEROES_TTL_S = 24 * 60 * 60
RANKS_TTL_S = 24 * 60 * 60
ITEMS_TTL_S = 24 * 60 * 60
MATCH_HISTORY_TTL_S = 5 * 60
LIVE_STATUS_TTL_S = 30
MATCH_METADATA_TTL_S = 24 * 60 * 60  # finished matches never change; long TTL just to bound cache size


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, updated_at REAL NOT NULL)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS heroes (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS ranks (tier INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS match_history ("
        "account_id INTEGER NOT NULL, match_id INTEGER NOT NULL, data TEXT NOT NULL, "
        "PRIMARY KEY (account_id, match_id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tracked_accounts (account_id INTEGER PRIMARY KEY, last_seen REAL NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS live_status (account_id INTEGER PRIMARY KEY, data TEXT NOT NULL)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS match_metadata (match_id INTEGER PRIMARY KEY, data TEXT NOT NULL)"
    )
    conn.commit()


def _is_fresh(conn: sqlite3.Connection, key: str, ttl_s: float) -> bool:
    row = conn.execute("SELECT updated_at FROM cache_meta WHERE key = ?", (key,)).fetchone()
    return row is not None and (time.time() - row["updated_at"]) < ttl_s


def _touch(conn: sqlite3.Connection, key: str) -> None:
    conn.execute(
        "INSERT INTO cache_meta (key, updated_at) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at",
        (key, time.time()),
    )


def get_cached_heroes(conn: sqlite3.Connection) -> dict[int, str] | None:
    if not _is_fresh(conn, "heroes", HEROES_TTL_S):
        return None
    rows = conn.execute("SELECT id, name FROM heroes").fetchall()
    return {row["id"]: row["name"] for row in rows}


def set_cached_heroes(conn: sqlite3.Connection, heroes: dict[int, str]) -> None:
    conn.execute("DELETE FROM heroes")
    conn.executemany("INSERT INTO heroes (id, name) VALUES (?, ?)", heroes.items())
    _touch(conn, "heroes")
    conn.commit()


def get_cached_ranks(conn: sqlite3.Connection) -> dict[int, str] | None:
    if not _is_fresh(conn, "ranks", RANKS_TTL_S):
        return None
    rows = conn.execute("SELECT tier, name FROM ranks").fetchall()
    return {row["tier"]: row["name"] for row in rows}


def set_cached_ranks(conn: sqlite3.Connection, ranks: dict[int, str]) -> None:
    conn.execute("DELETE FROM ranks")
    conn.executemany("INSERT INTO ranks (tier, name) VALUES (?, ?)", ranks.items())
    _touch(conn, "ranks")
    conn.commit()


def get_cached_match_history(conn: sqlite3.Connection, account_id: int) -> list[dict] | None:
    key = f"match_history:{account_id}"
    if not _is_fresh(conn, key, MATCH_HISTORY_TTL_S):
        return None
    rows = conn.execute(
        "SELECT data FROM match_history WHERE account_id = ? ORDER BY match_id DESC",
        (account_id,),
    ).fetchall()
    return [json.loads(row["data"]) for row in rows]


def set_cached_match_history(conn: sqlite3.Connection, account_id: int, matches: list[dict]) -> None:
    conn.execute("DELETE FROM match_history WHERE account_id = ?", (account_id,))
    conn.executemany(
        "INSERT INTO match_history (account_id, match_id, data) VALUES (?, ?, ?)",
        [(account_id, m["match_id"], json.dumps(m)) for m in matches],
    )
    _touch(conn, f"match_history:{account_id}")
    conn.commit()


def track_account(conn: sqlite3.Connection, account_id: int) -> None:
    conn.execute(
        "INSERT INTO tracked_accounts (account_id, last_seen) VALUES (?, ?) "
        "ON CONFLICT(account_id) DO UPDATE SET last_seen = excluded.last_seen",
        (account_id, time.time()),
    )
    conn.commit()


def get_tracked_accounts(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute("SELECT account_id FROM tracked_accounts").fetchall()
    return [row["account_id"] for row in rows]


def get_cached_live_status(conn: sqlite3.Connection, account_id: int) -> dict | None:
    key = f"live_status:{account_id}"
    if not _is_fresh(conn, key, LIVE_STATUS_TTL_S):
        return None
    row = conn.execute("SELECT data FROM live_status WHERE account_id = ?", (account_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def set_cached_live_status(conn: sqlite3.Connection, account_id: int, status: dict) -> None:
    conn.execute(
        "INSERT INTO live_status (account_id, data) VALUES (?, ?) "
        "ON CONFLICT(account_id) DO UPDATE SET data = excluded.data",
        (account_id, json.dumps(status)),
    )
    _touch(conn, f"live_status:{account_id}")
    conn.commit()


def get_cached_items(conn: sqlite3.Connection) -> dict[int, dict] | None:
    if not _is_fresh(conn, "items", ITEMS_TTL_S):
        return None
    rows = conn.execute("SELECT id, name, type FROM items").fetchall()
    return {row["id"]: {"name": row["name"], "type": row["type"]} for row in rows}


def set_cached_items(conn: sqlite3.Connection, items: dict[int, dict]) -> None:
    conn.execute("DELETE FROM items")
    conn.executemany(
        "INSERT INTO items (id, name, type) VALUES (?, ?, ?)",
        [(item_id, info["name"], info["type"]) for item_id, info in items.items()],
    )
    _touch(conn, "items")
    conn.commit()


def get_cached_match_metadata(conn: sqlite3.Connection, match_id: int) -> dict | None:
    key = f"match_metadata:{match_id}"
    if not _is_fresh(conn, key, MATCH_METADATA_TTL_S):
        return None
    row = conn.execute("SELECT data FROM match_metadata WHERE match_id = ?", (match_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def set_cached_match_metadata(conn: sqlite3.Connection, match_id: int, data: dict) -> None:
    conn.execute(
        "INSERT INTO match_metadata (match_id, data) VALUES (?, ?) "
        "ON CONFLICT(match_id) DO UPDATE SET data = excluded.data",
        (match_id, json.dumps(data)),
    )
    _touch(conn, f"match_metadata:{match_id}")
    conn.commit()
