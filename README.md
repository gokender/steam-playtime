# Steam Playtime

Steam Playtime is being developed as two independent parts:

- `agent/`: a local, Docker-ready collector that reads Steam game-process logs
  and stores play sessions in SQLite;
- a future server: responsible for receiving sessions from multiple devices and
  reconciling them.

The server is not implemented yet. See [the agent documentation](agent/README.md)
for Docker, CachyOS, Steam Deck, configuration, persistence, and troubleshooting
details.
