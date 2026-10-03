"""SQLite schema definitions, kept out of application logic."""

import sqlite3


def create_agent_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            session_uuid TEXT UNIQUE,
            device_id TEXT NOT NULL,
            appid TEXT NOT NULL,
            launch_command TEXT NOT NULL,
            launch_target TEXT,
            game_name TEXT NOT NULL,
            launch_kind TEXT NOT NULL CHECK (launch_kind IN ('STEAM_APP', 'NON_STEAM_SHORTCUT', 'UNKNOWN')),
            title_source TEXT NOT NULL CHECK (title_source IN ('LOCAL_MANIFEST', 'FALLBACK')),
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration_seconds REAL,
            status TEXT NOT NULL CHECK (status IN ('RUNNING', 'PENDING', 'SYNCED'))
        );
        CREATE TABLE IF NOT EXISTS ingested_events (
            id INTEGER PRIMARY KEY,
            source_inode TEXT NOT NULL,
            source_offset INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            raw_line TEXT NOT NULL,
            session_id INTEGER REFERENCES sessions(id),
            UNIQUE(source_inode, source_offset)
        );
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_servers (
            url TEXT PRIMARY KEY,
            server_id TEXT,
            failure_count INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT,
            last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS session_sync (
            session_uuid TEXT NOT NULL REFERENCES sessions(session_uuid),
            server_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('PENDING', 'SYNCED')),
            last_attempt_at TEXT,
            synced_at TEXT,
            PRIMARY KEY (session_uuid, server_id)
        );
    """)


def create_server_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            device_name TEXT NOT NULL UNIQUE,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS steam_apps (
            appid INTEGER PRIMARY KEY,
            name TEXT,
            app_type TEXT,
            resolution_status TEXT NOT NULL,
            resolution_source TEXT,
            last_lookup_at TEXT,
            next_lookup_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_uuid TEXT PRIMARY KEY,
            device_id TEXT NOT NULL REFERENCES devices(device_id),
            appid TEXT NOT NULL,
            game_name_snapshot TEXT NOT NULL,
            launch_kind TEXT NOT NULL,
            title_source TEXT NOT NULL,
            launch_target TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            duration_seconds REAL NOT NULL,
            received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS sessions_start_time ON sessions(start_time DESC);
        CREATE TABLE IF NOT EXISTS external_game_ids (
            provider TEXT NOT NULL,
            external_id TEXT NOT NULL,
            appid INTEGER NOT NULL REFERENCES steam_apps(appid),
            resolved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (provider, external_id),
            UNIQUE (provider, appid)
        );
    """)
