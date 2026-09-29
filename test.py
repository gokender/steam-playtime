import os
import re
from datetime import datetime
from pathlib import Path

LOG_FILE = "content_log2.txt"

# Chemins possibles vers les bibliothèques Steam sous Linux / CachyOS
STEAM_APPAPPS_PATHS = [
    Path.home() / ".local/share/Steam/steamapps",
    Path.home() / ".steam/steam/steamapps",
    Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps",
]


def load_game_names():
    """Parcourt les dossiers steamapps et extrait {appid: name} depuis appmanifest_*.acf"""
    game_names = {}

    # Regex pour lire le format VDF/KeyValues de Valve ("name" "Nom du Jeu")
    name_pattern = re.compile(r'"name"\s+"([^"]+)"', re.IGNORECASE)

    for base_path in STEAM_APPAPPS_PATHS:
        if not base_path.exists():
            continue

        for acf_file in base_path.glob("appmanifest_*.acf"):
            # Extraire l'AppID depuis le nom de fichier (ex: appmanifest_4428890.acf)
            match_id = re.search(r"appmanifest_(\d+)\.acf", acf_file.name)
            if not match_id:
                continue

            appid = match_id.group(1)
            try:
                content = acf_file.read_text(encoding="utf-8", errors="ignore")
                match_name = name_pattern.search(content)
                if match_name:
                    game_names[appid] = match_name.group(1)
            except Exception:
                pass

    return game_names


def parse_sessions(log_file, game_names):
    log_pattern = re.compile(
        r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] AppID (?P<appid>\d+) state changed : (?P<states>.*)$"
    )

    active_sessions = {}
    sessions = []

    if not os.path.exists(log_file):
        print(f"Erreur : Le fichier '{log_file}' n'a pas été trouvé.")
        return []

    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            match = log_pattern.match(line.strip())
            if not match:
                continue

            timestamp_str = match.group("timestamp")
            appid = match.group("appid")
            states = [s.strip() for s in match.group("states").split(",") if s.strip()]

            current_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            is_running = "App Running" in states

            # Début de session
            if is_running and appid not in active_sessions:
                active_sessions[appid] = current_time

            # Fin de session
            elif not is_running and appid in active_sessions:
                start_time = active_sessions.pop(appid)
                duration_sec = (current_time - start_time).total_seconds()

                game_name = game_names.get(appid, f"AppID {appid}")

                sessions.append({
                    "appid": appid,
                    "name": game_name,
                    "start": start_time,
                    "end": current_time,
                    "duration": duration_sec
                })

    return sessions


if __name__ == "__main__":
    game_names = load_game_names()
    sessions = parse_sessions(LOG_FILE, game_names)

    print(f"{'Jeu / Application':<32} | {'Début':<19} | {'Fin':<19} | {'Durée':<12}")
    print("-" * 90)

    for s in sessions:
        start_str = s["start"].strftime("%Y-%m-%d %H:%M:%S")
        end_str = s["end"].strftime("%Y-%m-%d %H:%M:%S")

        hours = int(s["duration"] // 3600)
        minutes = int((s["duration"] % 3600) // 60)
        secs = int(s["duration"] % 60)

        duration_str = f"{hours:02d}h {minutes:02d}m {secs:02d}s"

        # Tronquer le nom si très long pour garder l'alignement
        display_name = s['name'][:30] + ".." if len(s['name']) > 32 else s['name']
        print(f"{display_name:<32} | {start_str} | {end_str} | {duration_str}")