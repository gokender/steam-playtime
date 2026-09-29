# Steam Playtime Agent

The agent collects Steam play sessions locally. It watches Steam's
`gameprocess_log.txt`, identifies game starts and stops, and writes sessions to
a local SQLite database. It does not send data over the network.

This separation is intentional: a future server can synchronize and reconcile
the locally collected sessions without changing the collection mechanism.

## How it works

Steam writes entries similar to the following in `gameprocess_log.txt`:

```text
[2026-09-26 12:35:21] AppID 2714620 adding PID 16551 as a tracked process "..."
[2026-09-26 13:04:21] Remove 2714620 from running list
```

The first entry creates a `RUNNING` session. The `Remove` entry closes the
running session for the same AppID and records its duration.

The agent records the log inode and byte offset in SQLite. It supports log
rotation and only processes complete lines. Updating an ingestion event and
advancing the offset occur in the same SQLite transaction, preventing duplicate
sessions after an agent crash or restart.

Several AppIDs can be active at once: each `Remove <AppID>` event only closes
the matching AppID. If a new start is found for an AppID that still has an open
session, the previous session is closed at that new start time. This covers a
missing stop event after Steam or the host has stopped unexpectedly.

## Requirements

- Python 3.14 or newer for a local run, or Docker with Docker Compose.
- Read access to the Steam log directory.
- Write access to the chosen agent data directory.

Known native Steam log locations:

| Platform / installation | Log directory |
| --- | --- |
| CachyOS and most Linux desktop installs | `~/.local/share/Steam/logs` |
| Steam Deck | `/home/deck/.local/share/Steam/logs` |
| Steam Flatpak | `~/.var/app/com.valvesoftware.Steam/.local/share/Steam/logs` |

The exact host path is always configurable with `STEAM_LOG_PATH`.

## Run with Docker Compose

Docker mounts the **directory** containing Steam logs, rather than the log file
itself. This is important because Steam can rotate or replace
`gameprocess_log.txt`; the agent must see the directory entry after replacement.

1. Create a local environment file:

   ```bash
   cp .env.example .env
   ```

2. Edit `HOST_STEAM_LOG_DIR` in `.env` to the host Steam logs directory. Set `PUID`
   and `PGID` to the account that owns and can read that directory:

   ```bash
   id -u
   id -g
   ```

3. Start the agent from the repository root:

   ```bash
   docker compose up --build -d
   ```

4. Follow the English agent logs:

   ```bash
   docker compose logs --follow agent
   ```

5. Stop it without losing data:

   ```bash
   docker compose down
   ```

The SQLite database is persisted in `./data/agent.db` by default. Back up this
directory before removing it. The Steam logs volume is read-only.

### Steam Deck note

On Steam Deck, use the Steam Desktop Mode to configure and run Docker. Set:

```dotenv
HOST_STEAM_LOG_DIR=/home/deck/.local/share/Steam/logs
```

The Docker daemon and the selected user must have permission to traverse and
read that host directory. If Docker is installed through a containerized or
rootless setup, its host-file access rules may require additional configuration.

## Local run

From the `agent` directory:

```bash
STEAM_LOG_PATH="$HOME/.local/share/Steam/logs/gameprocess_log.txt" \
AGENT_DATA_DIR=./data \
CHECK_INTERVAL=2 \
python main.py
```

Use `Ctrl+C` to stop it. The same data directory can be reused across restarts.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `HOST_STEAM_LOG_DIR` | Required in Docker | Host directory containing `gameprocess_log.txt`, mounted read-only at `/steam-logs`. |
| `HOST_DATA_DIR` | `./data` in Docker | Host directory mounted at `/data` for the persistent SQLite database. |
| `CHECK_INTERVAL` | `2` | Polling interval in seconds. Must be a positive number. |
| `LOG_LEVEL` | `INFO` | Python logging level, for example `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |
| `TZ` | `Europe/Paris` in Docker | IANA timezone used for agent log timestamps, for example `Europe/Paris` or `America/Montreal`. |

`STEAM_LOG_PATH`, `AGENT_DATA_DIR`, and `AGENT_DB_PATH` remain optional advanced
variables for a local, non-Docker run. Docker sets its internal paths in the
image, so they do not need to appear in `.env` or Compose.

All runtime logs are written in English to standard output, which makes them
available through `docker compose logs` and standard system log collectors. The
default human-readable format uses aligned levels and stable event names:

```text
2026-09-29 11:42:08 CEST | INFO    | session.started           | appid=2714620 start=2026-09-26 12:35:21
2026-09-29 11:42:08 CEST | INFO    | session.completed         | id=1 appid=2714620 duration=1740s
```

## Database

The database contains:

- `sessions`: the AppID, original Steam command, start/end timestamps,
  duration, and collection status (`RUNNING`, `COMPLETED`, or `SYNCED`);
- `ingested_events`: the raw recognised Steam start/stop events, their source
  inode and offset, and the affected session when one exists. This is an audit
  trail for future parser and reconciliation improvements;
- `metadata`: the log inode and offset used for incremental reads.

The agent deliberately stores the launch command now, including commands for
non-Steam shortcuts, emulators, and ROM launchers. Future classification and
cross-device reconciliation need these original local facts. A launch command
can reveal local paths or usernames, so a future synchronisation client should
not upload it unchanged without an explicit privacy policy and normalisation.

`SYNCED` is reserved for the future server synchronisation workflow. The agent
currently only creates `RUNNING` and `COMPLETED` sessions.

### Development schema

The schema is currently recreated during development rather than migrated. If
the schema changes, stop the agent and delete its local `agent.db` (and any
adjacent `agent.db-wal` and `agent.db-shm` files) before starting it again.
Do not do this once the database contains sessions that you need to retain.

## Tests

Install the development dependencies and run the test suite from the repository
root:

```bash
uv sync --directory agent --group dev
uv run --directory agent pytest
```

## Current limitations

- A session is inferred from Steam log events; it measures Steam's notion of a
  game being in its running list, not window focus or controller activity.
- The agent does not resolve AppIDs to display names yet.
- The agent does not upload, reconcile, or delete sessions.
