-- CSCM-Tool local SQLite schema.
-- Holds both app data (servers, tunnels, DNS, backups) and auth data
-- (users, app_config — created separately by auth_manager.initialize_auth_storage()).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS servers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    slug          TEXT NOT NULL UNIQUE,
    type          TEXT NOT NULL,
    version       TEXT NOT NULL,
    loader_version TEXT,
    serverport    INTEGER NOT NULL UNIQUE,
    mem_min_gb    INTEGER NOT NULL DEFAULT 2,
    mem_max_gb    INTEGER NOT NULL DEFAULT 4,
    rcon_password TEXT NOT NULL,
    container_id  TEXT,
    status        TEXT NOT NULL DEFAULT 'provisioning',
    createdat     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playit_tunnels (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id      INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    tunnel_name    TEXT,
    tunnel_address TEXT,
    local_port     INTEGER,
    external_port  INTEGER
);

CREATE TABLE IF NOT EXISTS dns_records (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id            INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    record_type          TEXT,
    name                 TEXT,
    target               TEXT,
    port                 INTEGER,
    cloudflare_record_id TEXT
);

CREATE TABLE IF NOT EXISTS backups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id   INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    size_bytes  INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    kind        TEXT NOT NULL DEFAULT 'manual',
    backup_type TEXT NOT NULL DEFAULT 'zip'
);

CREATE TABLE IF NOT EXISTS backup_schedules (
    server_id   INTEGER PRIMARY KEY REFERENCES servers(id) ON DELETE CASCADE,
    cron        TEXT NOT NULL,
    retention   INTEGER NOT NULL DEFAULT 5,
    enabled     INTEGER NOT NULL DEFAULT 1,
    backup_type TEXT NOT NULL DEFAULT 'zip'
);

-- Bedrock has no per-player stats files (world data lives in LevelDB, not
-- readable JSON/NBT), so whitelist/operator changes made through the API are
-- logged here as an audit trail. Current status is derived by taking the
-- latest event per (server_id, username, whitelist|op) pair.
CREATE TABLE IF NOT EXISTS bedrock_player_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id  INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    username   TEXT NOT NULL,
    xuid       TEXT,
    event_type TEXT NOT NULL, -- whitelist_add | whitelist_remove | op_add | op_remove
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bedrock_player_events_lookup
    ON bedrock_player_events (server_id, username, event_type, id);
