"""Best-effort, idempotent synchronization of local pending sessions."""

import logging

import httpx

from steam_playtime.config import Settings
from steam_playtime.storage import agent as storage

logger = logging.getLogger(__name__)


def sync_once(settings: Settings) -> int:
    if not settings.server_url:
        return 0
    sessions = storage.pending_sessions(settings.agent_db)
    if not sessions:
        return 0
    payload = {"device_id": settings.device_id, "device_name": settings.device_name, "sessions": sessions}
    try:
        response = httpx.post(
            f"{settings.server_url}/api/v1/sessions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.api_token}"},
            timeout=10,
        )
        response.raise_for_status()
        if response.json().get("processed") != len(sessions):
            raise ValueError("Server did not acknowledge every session.")
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("Synchronization deferred: %s", error)
        return 0
    storage.mark_synced(settings.agent_db, [session["session_uuid"] for session in sessions])
    logger.info("agent | synchronized | sessions=%s", len(sessions))
    return len(sessions)
