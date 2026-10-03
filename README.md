# Steam Playtime

Steam Playtime tracks Steam sessions locally and can consolidate them on a
server in a trusted local network. It is local-first: an agent keeps its own
SQLite database while the server is unavailable and synchronizes later.

## Install and run

```bash
uv sync --group dev
uv run steam-playtime --help
```

The first command creates `~/.config/steam-playtime/config.toml` automatically
when configuration is needed. It contains the device identity and shared API
token; it is created with private file permissions.

```bash
uv run steam-playtime all       # local server and collector
uv run steam-playtime server    # central server only
uv run steam-playtime agent     # collector for a remote Steam machine
uv run steam-playtime status
uv run steam-playtime history
uv run steam-playtime stats
uv run steam-playtime stats --daily
uv run steam-playtime stats --game "Hades"
```

`agent` reads the local `gameprocess_log.txt`, stores raw launch commands only
on the device, and sends completed sessions to `server.url`. `server` exposes
an authenticated HTTP API; `all` uses the generated local configuration for
both roles.

Synchronization acknowledgements are tracked per server identity. Changing
`server.url` to a new server sends completed local sessions to that server once,
without resending sessions already acknowledged by a previously used server.
`all` exits before starting the agent if its local server port is unavailable;
use `--port` to override it temporarily.

`history` and `stats` render durations as `HH:MM:SS`. Daily reports use the
configured timezone and split sessions that cross midnight, so each calendar
day receives its correct share of playtime.

## Configuration

```toml
[agent]
device_id = "generated UUID"
device_name = "steamdeck-otter-moon"
check_interval_seconds = 2
timezone = "UTC"

[server]
url = "" # Set this on a remote agent; `all` uses localhost automatically.
host = "127.0.0.1"
port = 8080
api_token = "generated local token"
```

For a remote agent, copy the server URL and token into that machine's config.
Environment variables such as `SERVER_URL`, `API_TOKEN`, `SERVER_HOST`, and
`STEAM_PLAYTIME_DATA_DIR` override TOML values for Docker and systemd.

## Data

- Agent databases are stored in the platform data directory as `agent.db`.
- Server databases are stored there as `server.db`.
- On Linux this is normally `~/.local/share/steam-playtime/`.
- The schema remains disposable during development; remove old databases before
  using this revision.

Installed Steam titles are resolved locally from ACF manifests. Unknown AppIDs
are cached by the server and resolved with Steam's public Store endpoint when
possible; no Steam API key is needed.

## Docker

Docker is optional. Run the server with:

```bash
docker compose up --build server
```

The optional collector profile is for development:

```bash
docker compose --profile agent up --build agent
```

## Manual Linux / Steam Deck package

A reproducible manual PyInstaller build environment is available in
[`packaging/`](packaging/README.md). It builds a Linux x86_64 directory package
using Python 3.13 on Debian Bookworm, suitable for testing on Steam Deck.

```bash
./scripts/package-linux-x86_64.sh
```

## Development

```bash
uv run pytest
```
