"""FastAPI application for local-network session synchronization."""

import base64
import binascii
import logging
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from steam_playtime import __version__
from steam_playtime.config import Settings
from steam_playtime.reporting import daily_game_device_totals, daily_totals
from steam_playtime.steam.catalog import resolve_app
from steam_playtime.storage import server as storage

logger = logging.getLogger(__name__)


class SessionPayload(BaseModel):
    session_uuid: str
    appid: str = Field(pattern=r"^\d+$")
    game_name: str
    launch_kind: Literal["STEAM_APP", "NON_STEAM_SHORTCUT", "UNKNOWN"]
    title_source: Literal["LOCAL_MANIFEST", "FALLBACK"]
    launch_target: str | None = None
    start_time: str
    end_time: str
    duration_seconds: float = Field(ge=0)


class SyncPayload(BaseModel):
    device_id: str
    device_name: str = Field(min_length=1, max_length=100)
    sessions: list[SessionPayload]


def _encode_cursor(start_time: str, session_uuid: str) -> str:
    return base64.urlsafe_b64encode(f"{start_time}\n{session_uuid}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        start_time, session_uuid = base64.urlsafe_b64decode(cursor.encode()).decode().split("\n", maxsplit=1)
        if not session_uuid:
            raise ValueError
        return start_time, session_uuid
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid history cursor.") from error


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Steam Playtime", version=__version__)

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if authorization != f"Bearer {settings.api_token}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token.")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/info", dependencies=[Depends(require_token)])
    def info() -> dict[str, str]:
        return {"server_id": storage.server_id(settings.server_db), "version": __version__}

    @app.post("/api/v1/sessions", dependencies=[Depends(require_token)])
    def ingest(payload: SyncPayload, background_tasks: BackgroundTasks) -> dict[str, int | str]:
        sessions = [session.model_dump() for session in payload.sessions]
        try:
            storage.save_sessions(settings.server_db, payload.device_id, payload.device_name, sessions)
        except ValueError as error:
            logger.warning("server | sessions_rejected | reason=device_name_already_in_use")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        logger.info("server | sessions_ingested | device=%s | processed=%s", payload.device_name, len(sessions))
        for appid in storage.pending_appids(settings.server_db):
            background_tasks.add_task(resolve_app, settings.server_db, appid)
        return {"status": "success", "processed": len(sessions)}

    @app.get("/api/v1/history", dependencies=[Depends(require_token)])
    def history(limit: int = 20, cursor: str | None = None) -> dict:
        if not 1 <= limit <= 1000:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="limit must be between 1 and 1000.")
        rows = storage.history_page(settings.server_db, limit, _decode_cursor(cursor) if cursor else None)
        sessions = [dict(row) for row in rows]
        for session in sessions:
            session.pop("session_uuid")
        next_cursor = _encode_cursor(rows[-1]["start_time"], rows[-1]["session_uuid"]) if len(rows) == limit else None
        return {"sessions": sessions, "next_cursor": next_cursor}

    @app.get("/api/v1/stats", dependencies=[Depends(require_token)])
    def stats() -> dict:
        return {"rows": [dict(row) for row in storage.statistics(settings.server_db)]}

    @app.get("/api/v1/stats/daily", dependencies=[Depends(require_token)])
    def daily_stats(timezone: str, game: str | None = None) -> dict:
        totals = daily_totals(storage.sessions_for_reporting(settings.server_db), timezone, game)
        return {"totals": [{"day": day, **totals[day]} for day in sorted(totals, reverse=True)]}

    @app.get("/api/v1/stats/csv", dependencies=[Depends(require_token)])
    def csv_stats(timezone: str, game: str | None = None) -> dict:
        totals = daily_game_device_totals(storage.sessions_for_reporting(settings.server_db), timezone, game)
        return {"totals": totals}

    return app
