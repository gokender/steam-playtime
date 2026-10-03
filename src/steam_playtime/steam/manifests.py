"""Offline title resolution using local Steam ACF manifests."""

import re
from pathlib import Path

NAME = re.compile(r'"name"\s+"(?P<name>[^"]+)"', re.IGNORECASE)


def steamapps_directories() -> list[Path]:
    home = Path.home()
    roots = [
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    ]
    directories = [root / "steamapps" for root in roots]
    for directory in list(directories):
        library_file = directory / "libraryfolders.vdf"
        if library_file.exists():
            content = library_file.read_text(encoding="utf-8", errors="ignore")
            directories.extend(Path(path) / "steamapps" for path in re.findall(r'"path"\s+"([^"]+)"', content))
    return list(dict.fromkeys(directories))


def title_for_appid(appid: str) -> str | None:
    for directory in steamapps_directories():
        manifest = directory / f"appmanifest_{appid}.acf"
        if manifest.exists():
            match = NAME.search(manifest.read_text(encoding="utf-8", errors="ignore"))
            if match:
                return match["name"]
    return None
