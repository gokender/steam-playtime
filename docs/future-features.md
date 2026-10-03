# Future features

## Historical Steam log import

Import a complete historical `gameprocess_log.txt` into the local server
database, including logs copied from a former Windows PC.

Planned command:

```bash
steam-playtime import-log FILE \
  --device-name "former-windows-pc" \
  --timezone "Europe/Paris" \
  --dry-run
```

The import will reconstruct completed sessions, create or reuse the named
device, and queue unknown AppIDs for server-side Steam catalogue resolution.
Imported session UUIDs will be deterministic, so the same file can be imported
again without duplicates. Raw launch commands will not be stored on the server.

## Simple statistics web page

Serve a lightweight local-network page from FastAPI with consolidated totals,
daily playtime, game history, and device/date filters. The first version should
use server-rendered HTML and CSS; richer charts can be added later.
