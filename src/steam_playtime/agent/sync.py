"""Best-effort, per-server synchronization of completed local sessions."""

import logging
from datetime import UTC, datetime

import httpx

from steam_playtime.config import Settings
from steam_playtime.storage import agent as storage

logger = logging.getLogger(__name__)


def sync_once(settings: Settings, now: datetime | None = None) -> int:
    """Send sessions not yet acknowledged by the configured server."""
    if not settings.server_url:
        return 0

    current_time = now or datetime.now(UTC)
    if not storage.server_is_ready(settings.agent_db, settings.server_url, current_time):
        return 0

    try:
        with httpx.Client(timeout=10) as client:
            headers = {"Authorization": f"Bearer {settings.api_token}"}
            info = client.get(f"{settings.server_url}/api/v1/info", headers=headers)
            info.raise_for_status()
            configured_server_id = info.json()["server_id"]
            storage.register_server(settings.agent_db, settings.server_url, configured_server_id)

            sessions = storage.pending_sessions(settings.agent_db, configured_server_id)
            if not sessions:
                return 0

            response = client.post(
                f"{settings.server_url}/api/v1/sessions",
                json={
                    "device_id": settings.device_id,
                    "device_name": settings.device_name,
                    "sessions": sessions,
                },
                headers=headers,
            )
            response.raise_for_status()
            if response.json().get("processed") != len(sessions):
                raise ValueError("Server did not acknowledge every session.")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        storage.record_server_failure(settings.agent_db, settings.server_url, str(error), current_time)
        logger.warning("agent | synchronization_deferred | error=%s", error)
        return 0

    storage.mark_synced(settings.agent_db, configured_server_id, [session["session_uuid"] for session in sessions], current_time)
    logger.info("agent | synchronized | server_id=%s sessions=%s", configured_server_id, len(sessions))
    return len(sessions)
