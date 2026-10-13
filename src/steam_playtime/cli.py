"""Human-friendly command line interface."""

import logging
import socket
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
import uvicorn
import httpx

from steam_playtime import __version__
from steam_playtime.agent.collector import collect_once
from steam_playtime.agent.sync import sync_once
from steam_playtime.config import Settings, config_path, load_settings
from steam_playtime.reporting import daily_game_device_totals, daily_totals, format_duration, write_daily_game_device_csv
from steam_playtime.server.app import create_app
from steam_playtime.storage import agent as agent_storage
from steam_playtime.storage import server as server_storage

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=True,
    help="Local-first Steam playtime tracking.",
)
sync_app = typer.Typer(help="Manage agent synchronization.")
app.add_typer(sync_app, name="sync")


@app.callback()
def root(
    version: bool = typer.Option(False, "--version", help="Show the installed version and exit."),
) -> None:
    """Steam Playtime command line interface."""
    if version:
        typer.echo(f"steam-playtime {__version__}")
        raise typer.Exit()


def settings() -> Settings:
    path = config_path()
    created = not path.exists()
    configuration = load_settings()
    configuration.data_dir.mkdir(parents=True, exist_ok=True)
    if created:
        typer.echo(f"Created configuration at {configuration.config_file}")
    return configuration


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def run_agent(configuration: Settings, log_path: Path | None = None) -> None:
    configure_logging()
    typer.echo(f"agent | started | device={configuration.device_name} | press Ctrl+C to stop")
    try:
        while True:
            agent_storage.record_agent_heartbeat(configuration.agent_db, datetime.now(UTC), configuration.server_url)
            collect_once(configuration, log_path)
            synced = sync_once(configuration)
            if synced:
                typer.echo(f"Synchronized {synced} session(s).")
            time.sleep(configuration.check_interval_seconds)
    except KeyboardInterrupt:
        typer.echo("Agent stopped.")


def bind_server_socket(configuration: Settings) -> socket.socket:
    """Reserve the listening port before the agent is allowed to start."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((configuration.server_host, configuration.server_port))
    listener.listen(socket.SOMAXCONN)
    listener.setblocking(False)
    return listener


def run_server(configuration: Settings, listener: socket.socket | None = None) -> None:
    typer.echo(f"server | started | http://{configuration.server_host}:{configuration.server_port}")
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(configuration),
            host=configuration.server_host,
            port=configuration.server_port,
            access_log=False,
            log_level="warning",
        )
    )
    server.run(sockets=[listener] if listener else None)


@app.command()
def agent(log_path: Path | None = typer.Option(None, help="Override the Steam gameprocess_log.txt path.")) -> None:
    """Collect local Steam sessions and synchronize them."""
    run_agent(settings(), log_path)


@app.command()
def server(port: int | None = typer.Option(None, "--port", min=1, max=65535, help="Override the configured HTTP port.")) -> None:
    """Start the central local-network API server."""
    configuration = settings()
    if port is not None:
        configuration = replace(configuration, server_port=port)
    try:
        listener = bind_server_socket(configuration)
    except OSError as error:
        typer.echo(f"server | failed | port={configuration.server_port} | error={error}", err=True)
        raise typer.Exit(1) from error
    run_server(configuration, listener)


@app.command()
def all(
    log_path: Path | None = typer.Option(None, help="Override the Steam gameprocess_log.txt path."),
    port: int | None = typer.Option(None, "--port", min=1, max=65535, help="Override the local server HTTP port."),
) -> None:
    """Run the local server and collector together."""
    configuration = settings()
    if port is not None:
        configuration = replace(configuration, server_port=port)
    local_url = f"http://127.0.0.1:{configuration.server_port}"
    configuration = replace(configuration, server_url=local_url)
    try:
        listener = bind_server_socket(configuration)
    except OSError as error:
        typer.echo(f"server | failed | port={configuration.server_port} | error={error}", err=True)
        raise typer.Exit(1) from error
    thread = threading.Thread(target=run_server, args=(configuration, listener), daemon=True)
    thread.start()
    run_agent(configuration, log_path)


@app.command()
def status() -> None:
    """Show local collection and synchronization state."""
    configuration = settings()
    with agent_storage.connection(configuration.agent_db) as database:
        session = database.execute(
            "SELECT game_name, start_time FROM sessions WHERE status = 'RUNNING' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if session is None:
        typer.echo("Current game: none")
    else:
        typer.echo(f"Current game: {session['game_name']} — started {session['start_time']}")
    show_agent_status(configuration)
    server_url = synchronization_target_url(configuration)
    show_pending_sessions(configuration, server_url)
    show_sync_status(configuration, server_url)


def synchronization_target_url(configuration: Settings) -> str:
    """Use the configured remote URL, or the target most recently used by the agent."""
    return configuration.server_url or agent_storage.active_server_url(configuration.agent_db)


def show_agent_status(configuration: Settings) -> None:
    heartbeat = agent_storage.agent_heartbeat(configuration.agent_db)
    if heartbeat is None:
        typer.echo("Agent: never started")
        return
    heartbeat_at = datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
    stale_after = timedelta(seconds=configuration.check_interval_seconds * 2)
    state = "running" if heartbeat_at + stale_after >= datetime.now(UTC) else "unhealthy"
    typer.echo(f"Agent: {state} | last heartbeat={heartbeat}")


def show_pending_sessions(configuration: Settings, server_url: str) -> None:
    if not server_url:
        typer.echo("Pending sessions: not available (synchronization not configured)")
        return
    configured_server_id = agent_storage.server_id(configuration.agent_db, server_url)
    pending = agent_storage.pending_session_count(configuration.agent_db, configured_server_id)
    typer.echo(f"Pending sessions: {pending}")


def show_sync_status(configuration: Settings, server_url: str) -> None:
    if not server_url:
        typer.echo("Synchronization: not configured.")
        typer.echo("Last synchronization: not available (synchronization not configured)")
        return
    state = agent_storage.server_sync_status(configuration.agent_db, server_url)
    if state["suspended"]:
        typer.echo(
            f"Synchronization: suspended | failures={state['failure_count']} | error={state['last_error']} | "
            "run 'steam-playtime sync reset' after correcting the configuration or server."
        )
    elif state["next_attempt_at"]:
        typer.echo(
            f"Synchronization: retry at {state['next_attempt_at']} | failures={state['failure_count']} | "
            f"error={state['last_error']}"
        )
    else:
        typer.echo(f"Synchronization: ready | failures={state['failure_count']}")
    result = agent_storage.last_sync_result(configuration.agent_db, server_url)
    if result is None:
        typer.echo("Last synchronization: never")
    elif result["result"] == "SUCCESS":
        typer.echo(f"Last synchronization: success at {result['attempted_at']} | sessions={result['session_count']}")
    else:
        typer.echo(f"Last synchronization: failed at {result['attempted_at']} | error={result['error']}")


@sync_app.command("reset")
def reset_sync() -> None:
    """Resume synchronization after an HTTP error."""
    configuration = settings()
    server_url = synchronization_target_url(configuration)
    if not server_url:
        typer.echo("Synchronization is not configured.", err=True)
        raise typer.Exit(1)
    agent_storage.reset_server_sync(configuration.agent_db, server_url)
    typer.echo(f"Synchronization reset for {server_url}.")


def server_request(configuration: Settings, path: str, params: dict | None = None) -> dict:
    """Fetch a report from the configured central server or fail explicitly."""
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"{configuration.server_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {configuration.api_token}"},
            )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as error:
        typer.echo(f"Failed to retrieve server data: {error}", err=True)
        raise typer.Exit(1) from error


def remote_history(configuration: Settings, limit: int) -> list[dict]:
    rows: list[dict] = []
    cursor: str | None = None
    while len(rows) < limit:
        page_size = min(1000, limit - len(rows))
        params: dict[str, int | str] = {"limit": page_size}
        if cursor is not None:
            params["cursor"] = cursor
        payload = server_request(configuration, "/api/v1/history", params)
        rows.extend(payload["sessions"])
        cursor = payload["next_cursor"]
        if cursor is None:
            break
    return rows


@app.command()
def history(
    limit: int = typer.Option(20, min=1, help="Maximum number of sessions to show."),
    local: bool = typer.Option(False, "--local", help="Show only completed sessions stored on this agent."),
) -> None:
    """Show centralized history, or local completed sessions with --local."""
    configuration = settings()
    if local:
        rows = agent_storage.local_history(configuration.agent_db, configuration.device_name, limit)
    elif configuration.server_url:
        rows = remote_history(configuration, limit)
    else:
        rows = server_storage.history(configuration.server_db, limit)
    if not rows:
        typer.echo("No matching sessions yet.")
    for row in rows:
        typer.echo(
            f"{row['start_time']} | {row['game_name']} | {row['device_name']} | "
            f"{format_duration(row['duration_seconds'])}"
        )


@app.command()
def stats(
    local: bool = typer.Option(False, "--local", help="Use only completed sessions stored on this agent."),
    daily: bool = typer.Option(False, "--daily", help="Group playtime by local calendar day."),
    game: str | None = typer.Option(None, "--game", help="Show daily sessions for one game."),
    csv: Path | None = typer.Option(None, "--csv", help="Export daily game and device totals to a CSV file."),
) -> None:
    """Show centralized playtime totals, or local totals with --local."""
    configuration = settings()
    if local:
        reporting_rows = agent_storage.local_sessions_for_reporting(configuration.agent_db, configuration.device_name)
        statistics_rows = agent_storage.local_statistics(configuration.agent_db)
    elif configuration.server_url:
        if csv is not None:
            totals = server_request(
                configuration, "/api/v1/stats/csv", {"timezone": configuration.timezone, "game": game}
            )["totals"]
            write_daily_game_device_csv(csv, totals)
            typer.echo(f"Exported {len(totals)} row(s) to {csv}.")
            return
        if daily or game:
            totals = server_request(
                configuration, "/api/v1/stats/daily", {"timezone": configuration.timezone, "game": game}
            )["totals"]
            if not totals:
                typer.echo("No matching server sessions yet.")
                return
            for report in totals:
                typer.echo(f"{report['day']} | {format_duration(report['duration'])} | {len(report['sessions'])} session(s)")
                if game:
                    for session in report["sessions"]:
                        typer.echo(
                            f"  {session['start']} → {session['end']} | {session['game_name']} | "
                            f"{format_duration(session['duration'])}"
                        )
            return
        rows = server_request(configuration, "/api/v1/stats")["rows"]
        if not rows:
            typer.echo("No server sessions yet.")
        for row in rows:
            typer.echo(f"{row['game_name']} | {format_duration(row['duration'])}")
        return
    else:
        reporting_rows = server_storage.sessions_for_reporting(configuration.server_db)
        statistics_rows = server_storage.statistics(configuration.server_db)
    if csv is not None:
        totals = daily_game_device_totals(reporting_rows, configuration.timezone, game)
        write_daily_game_device_csv(csv, totals)
        typer.echo(f"Exported {len(totals)} row(s) to {csv}.")
        return
    if daily or game:
        totals = daily_totals(reporting_rows, configuration.timezone, game)
        if not totals:
            typer.echo("No matching server sessions yet.")
            return
        for day in sorted(totals, reverse=True):
            report = totals[day]
            typer.echo(f"{day} | {format_duration(report['duration'])} | {len(report['sessions'])} session(s)")
            if game:
                for session in report["sessions"]:
                    typer.echo(
                        f"  {session['start']} → {session['end']} | {session['game_name']} | "
                        f"{format_duration(session['duration'])}"
                    )
        return

    if not statistics_rows:
        typer.echo("No matching sessions yet." if local else "No server sessions yet.")
    for row in statistics_rows:
        typer.echo(f"{row['game_name']} | {format_duration(row['duration'])}")


def main() -> None:
    app()
