"""FastAPI application for local-network session synchronization."""

from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from steam_playtime import __version__
from steam_playtime.config import Settings
from steam_playtime.steam.catalog import resolve_app
from steam_playtime.storage import server as storage


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


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Steam Playtime", version=__version__)

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if authorization != f"Bearer {settings.api_token}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token.")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/sessions", dependencies=[Depends(require_token)])
    def ingest(payload: SyncPayload, background_tasks: BackgroundTasks) -> dict[str, int | str]:
        sessions = [session.model_dump() for session in payload.sessions]
        try:
            storage.save_sessions(settings.server_db, payload.device_id, payload.device_name, sessions)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        for appid in storage.pending_appids(settings.server_db):
            background_tasks.add_task(resolve_app, settings.server_db, appid)
        return {"status": "success", "processed": len(sessions)}

    return app
