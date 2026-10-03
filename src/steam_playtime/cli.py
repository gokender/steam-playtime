"""Human-friendly command line interface."""

import logging
import threading
import time
from dataclasses import replace
from pathlib import Path

import typer
import uvicorn

from steam_playtime.agent.collector import collect_once
from steam_playtime.agent.sync import sync_once
from steam_playtime.config import Settings, config_path, load_settings
from steam_playtime.reporting import daily_totals, format_duration
from steam_playtime.server.app import create_app
from steam_playtime.storage import agent as agent_storage
from steam_playtime.storage import server as server_storage

app = typer.Typer(no_args_is_help=True, help="Local-first Steam playtime tracking.")


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


def run_agent(configuration: Settings, log_path: Path | None = None) -> None:
    configure_logging()
    typer.echo(f"agent | started | device={configuration.device_name} | press Ctrl+C to stop")
    try:
        while True:
            collect_once(configuration, log_path)
            synced = sync_once(configuration)
            if synced:
                typer.echo(f"Synchronized {synced} session(s).")
            time.sleep(configuration.check_interval_seconds)
    except KeyboardInterrupt:
        typer.echo("Agent stopped.")


def run_server(configuration: Settings) -> None:
    typer.echo(f"server | started | http://{configuration.server_host}:{configuration.server_port}")
    uvicorn.run(
        create_app(configuration),
        host=configuration.server_host,
        port=configuration.server_port,
        access_log=False,
        log_level="warning",
    )


@app.command()
def agent(log_path: Path | None = typer.Option(None, help="Override the Steam gameprocess_log.txt path.")) -> None:
    """Collect local Steam sessions and synchronize them."""
    run_agent(settings(), log_path)


@app.command()
def server() -> None:
    """Start the central local-network API server."""
    run_server(settings())


@app.command()
def all(log_path: Path | None = typer.Option(None, help="Override the Steam gameprocess_log.txt path.")) -> None:
    """Run the local server and collector together."""
    configuration = settings()
    local_url = configuration.server_url or f"http://127.0.0.1:{configuration.server_port}"
    configuration = replace(configuration, server_url=local_url)
    thread = threading.Thread(target=run_server, args=(configuration,), daemon=True)
    thread.start()
    run_agent(configuration, log_path)


@app.command()
def status() -> None:
    """Show the active local session."""
    configuration = settings()
    with agent_storage.connection(configuration.agent_db) as database:
        session = database.execute(
            "SELECT game_name, start_time FROM sessions WHERE status = 'RUNNING' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if session is None:
        typer.echo("No active local session.")
    else:
        typer.echo(f"{session['game_name']} — started {session['start_time']}")


@app.command()
def history(limit: int = typer.Option(20, min=1, help="Maximum number of sessions to show.")) -> None:
    """Show consolidated history from the local server database."""
    rows = server_storage.history(settings().server_db, limit)
    if not rows:
        typer.echo("No server sessions yet.")
    for row in rows:
        typer.echo(
            f"{row['start_time']} | {row['game_name']} | {row['device_name']} | "
            f"{format_duration(row['duration_seconds'])}"
        )


@app.command()
def stats(
    daily: bool = typer.Option(False, "--daily", help="Group playtime by local calendar day."),
    game: str | None = typer.Option(None, "--game", help="Show daily sessions for one game."),
) -> None:
    """Show consolidated playtime totals from the local server database."""
    configuration = settings()
    if daily or game:
        totals = daily_totals(server_storage.sessions_for_reporting(configuration.server_db), configuration.timezone, game)
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

    rows = server_storage.statistics(configuration.server_db)
    if not rows:
        typer.echo("No server sessions yet.")
    for row in rows:
        typer.echo(f"{row['game_name']} | {format_duration(row['duration'])}")


def main() -> None:
    app()
