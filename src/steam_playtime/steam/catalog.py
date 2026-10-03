"""Steam Store catalogue fallback with a persistent server-side cache."""

from datetime import UTC, datetime, timedelta

import httpx

from steam_playtime.storage import server as storage


def resolve_app(db_path, appid: int) -> None:
    now = datetime.now(UTC)
    try:
        response = httpx.get("https://store.steampowered.com/api/appdetails", params={"appids": appid}, timeout=10)
        response.raise_for_status()
        result = response.json().get(str(appid), {})
        if result.get("success"):
            data = result["data"]
            _save(db_path, appid, data.get("name"), data.get("type"), "RESOLVED", "STEAM_STORE", now, None)
        else:
            _save(db_path, appid, None, None, "NOT_FOUND", "STEAM_STORE", now, None)
    except (httpx.HTTPError, ValueError):
        _save(db_path, appid, None, None, "RETRY_LATER", None, now, now + timedelta(hours=6))


def _save(db_path, appid, name, app_type, status, source, checked_at, next_lookup) -> None:
    with storage.connection(db_path) as database:
        database.execute(
            "INSERT INTO steam_apps (appid, name, app_type, resolution_status, resolution_source, last_lookup_at, next_lookup_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(appid) DO UPDATE SET name = excluded.name, app_type = excluded.app_type, "
            "resolution_status = excluded.resolution_status, resolution_source = excluded.resolution_source, "
            "last_lookup_at = excluded.last_lookup_at, next_lookup_at = excluded.next_lookup_at",
            (appid, name, app_type, status, source, checked_at.isoformat(), next_lookup.isoformat() if next_lookup else None),
        )
        if status == "RESOLVED":
            database.execute(
                "UPDATE sessions SET game_name_snapshot = ?, launch_kind = 'STEAM_APP', title_source = 'SERVER_CATALOG' "
                "WHERE appid = ? AND launch_kind = 'UNKNOWN'",
                (name, str(appid)),
            )
