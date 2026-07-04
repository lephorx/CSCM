# CSCM Tool — API Documentation

CSCM (Craft Server & Container Manager) is a self-contained REST API for provisioning and
managing Minecraft servers. It has no external dependency on Crafty Controller or any
managed database — every server it creates runs as its own Docker container on the host
running CSCM, and all application state lives in a local SQLite database.

## Table of Contents

1. [Architecture](#architecture)
2. [Features](#features)
3. [Requirements](#requirements)
4. [Quick Start](#quick-start)
5. [Configuration](#configuration)
6. [Database](#database)
7. [Authentication](#authentication)
8. [Error Format](#error-format)
9. [API Reference](#api-reference)
   - [Auth](#auth-endpoints)
   - [Server Types](#server-types)
   - [Servers — CRUD](#servers--crud)
   - [Server Lifecycle](#server-lifecycle)
   - [Console & Stats](#console--stats)
   - [Server Modification](#server-modification)
   - [server.properties](#serverproperties)
   - [Players](#players)
   - [Backups](#backups)
   - [Files](#files)
   - [Networking](#networking)
10. [CLI Scripts](#cli-scripts)
11. [OpenAPI Spec](#openapi-spec)
12. [Security Notes](#security-notes)
13. [Troubleshooting](#troubleshooting)

---

## Architecture

```
                     ┌──────────────────────┐
   HTTP clients ───▶ │   CSCM Flask API      │
                     │  (JWT + TOTP auth)    │
                     └──────────┬───────────┘
                                │  Docker Engine API (via /var/run/docker.sock)
                                ▼
                     ┌──────────────────────┐
                     │   Minecraft server    │   one container per server,
                     │   containers          │   itzg/minecraft-server image
                     │   (cscm-mc-<id>)       │
                     └──────────────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                     ▼
     PlayIT.gg tunnel                     Cloudflare DNS (CNAME + SRV)
     (Playwright automation)              (public connect address)
```

CSCM itself runs in one container (or directly on a host with Docker installed). It talks
to the Docker daemon to create, start, stop, and inspect **one container per Minecraft
server**, using the [`itzg/minecraft-server`](https://github.com/itzg/docker-minecraft-server)
image, which handles jar download/installation, EULA acceptance, and memory limits for
every supported server flavor. Console commands run via `rcon-cli` inside each container;
there is no exposed RCON port.

All application data — servers, tunnels, DNS records, backups, backup schedules, users —
lives in a single local SQLite file. There is no external database to provision or manage.

## Features

- **Self-provisioning**: create a fully configured Minecraft server (any of 5 flavors) with
  one API call — no manual jar downloads, no external panel.
- **Full lifecycle control**: start/stop/restart/kill, live console commands via RCON,
  log tailing, and a live console stream over Server-Sent Events (SSE).
- **Resource management**: change name, port, or RAM allocation (recreates the container;
  world data is preserved on a bind-mounted volume).
- **server.properties editor**: read and patch arbitrary properties with a
  restart-required flag.
- **Player management**: whitelist, ops, bans, and kicks — backed by RCON when the server
  is running, readable from disk when it's stopped.
- **Backups**: on-demand and cron-scheduled zip backups with retention pruning, plus
  one-call restore.
- **Networking**: PlayIT.gg tunnel automation and Cloudflare DNS (CNAME + SRV) so players
  connect via a friendly subdomain instead of an IP:port.
- **File management**: browse, upload, download, and delete files inside a server's data
  directory directly through the API.
- **Local auth**: single-admin JWT + TOTP (2FA) authentication, no external identity
  provider required.

## Requirements

- **Docker Engine** on the host (CSCM talks to it via the Docker socket).
- **Python 3.12+** (only if running outside Docker).
- A **PlayIT.gg** account (for tunnels) and a **Cloudflare** zone (for DNS) — both optional
  if you only need local/LAN access and handle networking yourself, but the tunnel/DNS
  endpoints require them.
- No external database — SQLite ships with Python.

## Quick Start

```bash
git clone <this-repo>
cd CSCM-Tool
cp .env.example .env
# Edit .env: set PLAYIT_*, CLOUDFLARE_*, SERVERS_DIR_HOST, BACKUPS_DIR_HOST, DATA_DIR_HOST

docker compose up --build
```

Then:

```bash
# 1. First-run setup (creates the single admin account + TOTP secret)
curl -X POST http://localhost:5000/api/auth/setup \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "a-very-long-password"}'
# Scan the returned qr_code_data_uri with an authenticator app, or use totp_secret directly.

# 2. Log in
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "a-very-long-password", "otp": "123456"}'
# -> { "token": "...", ... }

# 3. Create a server
curl -X POST http://localhost:5000/api/servers \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"name": "Survival SMP", "type": "paper", "version": "1.21.4", "port": 25565}'
```

Running without Docker Compose (e.g. directly on a host with Docker installed)? Set
`SERVERS_DIR`/`SERVERS_DIR_HOST` and `BACKUPS_DIR`/`BACKUPS_DIR_HOST` to the **same** paths,
then `pip install -r requirements.txt && python app.py`.

## Configuration

All configuration is via environment variables (see `.env.example`).

| Variable                                                               | Default                               | Description                                                                                                                                                                                   |
| ---------------------------------------------------------------------- | ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DB_PATH`                                                              | `cscm.db`                             | Path to the SQLite database file (app data).                                                                                                                                                  |
| `AUTH_DB_PATH`                                                         | `cscm.db`                             | Path to the SQLite database file (auth data). Point at the same file as `DB_PATH`.                                                                                                            |
| `MC_IMAGE`                                                             | `itzg/minecraft-server:java21`        | Docker image used for every Minecraft server container.                                                                                                                                       |
| `SERVERS_DIR`                                                          | `/data/servers`                       | Path to server data directories **as seen by the CSCM process**. Must be an absolute path — Docker rejects relative paths for bind mounts.                                                    |
| `SERVERS_DIR_HOST`                                                     | `/opt/cscm/servers`                   | Path to the **same** directory **as seen by the Docker daemon** — used for bind-mounting into Minecraft containers. Only differs from `SERVERS_DIR` when CSCM itself runs inside a container. |
| `BACKUPS_DIR` / `BACKUPS_DIR_HOST`                                     | `/data/backups` / `/opt/cscm/backups` | Same host/container-path split, for backup archives.                                                                                                                                          |
| `PLAYIT_EMAIL`, `PLAYIT_PASSWORD`                                      | —                                     | PlayIT.gg account credentials (Playwright login).                                                                                                                                             |
| `PLAYIT_HEADLESS`                                                      | `false`                               | Run the Playwright browser headless.                                                                                                                                                          |
| `PLAYIT_SUBSCRIPTION`                                                  | `premium`                             | `premium` or `free`.                                                                                                                                                                          |
| `PLAYIT_REGION`                                                        | `Germany`                             | Tunnel region (premium only).                                                                                                                                                                 |
| `PLAYIT_AGENT`                                                         | —                                     | Specific PlayIT agent name; first available if unset.                                                                                                                                         |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`, `CLOUDFLARE_BASE_DOMAIN` | —                                     | Cloudflare DNS credentials/zone.                                                                                                                                                              |
| `FLASK_HOST` / `FLASK_PORT`                                            | `0.0.0.0` / `5000`                    | Bind address for the API.                                                                                                                                                                     |
| `FLASK_DEBUG`                                                          | `false`                               | Flask debug mode (dev only).                                                                                                                                                                  |
| `JWT_LIFETIME_HOURS`                                                   | `8`                                   | Login session length.                                                                                                                                                                         |
| `TOTP_ISSUER`                                                          | `CSCM Tool`                           | Issuer name shown in authenticator apps.                                                                                                                                                      |
| `LOG_LEVEL`                                                            | `INFO`                                | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR`.                                                                                                                                                          |

> **Important — the `SERVERS_DIR` / `SERVERS_DIR_HOST` split.** CSCM runs in its own
> container and talks to the Docker daemon over a mounted socket. When it asks the daemon
> to bind-mount a server's data directory into a new Minecraft container, that path is
> resolved **on the host**, not inside CSCM's own container. `SERVERS_DIR_HOST` (and
> `BACKUPS_DIR_HOST`) must point at the same physical directory as `SERVERS_DIR` — just
> expressed as the host sees it. Getting this wrong is the most common setup mistake; the
> app validates writability of `SERVERS_DIR`/`BACKUPS_DIR` at startup and fails fast, but it
> cannot detect a host-path mismatch — verify with `docker exec cscm_api ls /data/servers`
> vs. `ls $SERVERS_DIR_HOST` after creating a server.

## Database

CSCM uses a single local SQLite file (`schema.sql`) for both application data and
authentication data. Initialize it with:

```bash
python scripts/init_db.py
```

This creates `servers`, `playit_tunnels`, `dns_records`, `backups`, `backup_schedules`
(app data) and `users`, `app_config` (auth data, created by `auth_manager`). `app.py` also
calls this automatically on startup, so a manual run is only needed for local development
outside Docker.

## Authentication

CSCM uses **local, single-admin authentication**: username + password + TOTP (2FA), issuing
short-lived JWTs. There is no user management beyond the first account — `POST
/api/auth/setup` can only be called once.

1. `POST /api/auth/setup` — create the one admin account. Returns a TOTP secret, URI, and
   QR code (as an SVG data URI) to scan into an authenticator app (Google Authenticator,
   Authy, 1Password, etc.).
2. `POST /api/auth/login` — exchange username + password + current TOTP code for a JWT.
3. Include the JWT on every subsequent request: `Authorization: Bearer <token>`.
4. Tokens expire after `JWT_LIFETIME_HOURS` (default 8) — log in again to get a new one.

If `GET /api/auth/status` reports `setup_required: true`, no account exists yet and every
protected endpoint will return `403`.

## Error Format

Most endpoints return a JSON body with at least:

```json
{ "success": false, "message": "Human-readable description of what went wrong" }
```

A handful of validation errors (mostly on request body/query parsing) use `"error"`
instead of `"message"` — check for either key defensively. Common status codes:

| Status | Meaning                                                                   |
| ------ | ------------------------------------------------------------------------- |
| `400`  | Malformed or invalid request body/parameters.                             |
| `401`  | Missing or invalid JWT.                                                   |
| `403`  | Initial setup not completed yet.                                          |
| `404`  | Server, backup, or file not found.                                        |
| `409`  | Conflict — e.g. port already in use, or action requires a running server. |
| `500`  | Unexpected server-side error (Docker/PlayIT/Cloudflare failure, etc.).    |

---

## API Reference

All endpoints below (except `/health` and `/api/auth/*`) require `Authorization: Bearer
<token>`.

### Auth Endpoints

#### `GET /api/auth/status`

No auth required. Returns whether setup is needed and whether the caller is authenticated.

```json
{
  "setup_required": false,
  "authenticated": true,
  "user": { "id": 1, "username": "admin" }
}
```

#### `POST /api/auth/setup`

No auth required (fails with `409` if already set up). Body:

```json
{ "username": "admin", "password": "at-least-12-characters" }
```

Response `201`:

```json
{
  "success": true,
  "message": "Initial account created. Scan the QR code and then sign in with your one-time password.",
  "totp_secret": "BASE32SECRET",
  "totp_uri": "otpauth://totp/CSCM%20Tool:admin?secret=...",
  "qr_code_data_uri": "data:image/svg+xml;base64,..."
}
```

#### `POST /api/auth/login`

No auth required. Body:

```json
{ "username": "admin", "password": "...", "otp": "123456" }
```

Response `200`:

```json
{
  "success": true,
  "token": "eyJ...",
  "token_type": "Bearer",
  "expires_at": 1735689600,
  "user": { "id": 1, "username": "admin" }
}
```

#### `GET /api/auth/me`

Returns the authenticated user for the supplied token.

---

### Server Types

#### `GET /api/server-types`

```json
{ "server_types": ["paper", "forge", "fabric", "vanilla", "purpur"] }
```

---

### Servers — CRUD

#### `GET /api/servers`

Lists every server with its tunnels, DNS records, and live `runtime_status`.

```json
{
  "servers": [
    {
      "id": 1,
      "name": "Survival SMP",
      "slug": "survival-smp",
      "type": "paper",
      "version": "1.21.4",
      "loader_version": null,
      "port": 25565,
      "mem_min": 2,
      "mem_max": 4,
      "status": "created",
      "runtime_status": "healthy",
      "created_at": "2026-07-01 12:00:00",
      "tunnels": [
        {
          "address": "abc123.mcjoin.link",
          "local_port": 25565,
          "external_port": 34567
        }
      ],
      "dns_records": [
        {
          "type": "CNAME",
          "name": "survival-smp.example.com",
          "target": "abc123.mcjoin.link",
          "port": null
        }
      ]
    }
  ]
}
```

`runtime_status` is one of: `not_created`, `stopped`, `starting`, `healthy`, `unhealthy`,
`running` (running but the image reports no health check yet).

#### `GET /api/servers/<id>`

Full detail for one server, including `runtime_status`, `port`, `mem_min`, `mem_max`,
and `loader_version` (excludes the RCON password).

Example response:

```json
{
  "success": true,
  "server": {
    "id": 3,
    "name": "servertestdev123",
    "slug": "servertestdev123",
    "type": "vanilla",
    "version": "1.21.4",
    "loader_version": null,
    "port": 25567,
    "mem_min": 4,
    "mem_max": 16,
    "status": "created",
    "runtime_status": "healthy",
    "created_at": "2026-07-04 00:36:32"
  }
}
```

#### `POST /api/servers`

Provisions a full stack: SQLite record → Docker container → PlayIT tunnel → Cloudflare
CNAME + SRV. This is synchronous but fast — `docker run` returns in seconds; jar
download/world generation happen inside the container afterward. Poll
`GET /api/servers/<id>` and watch `runtime_status` go `starting` → `healthy`.

Request body:

| Field            | Type   | Required | Default       | Notes                                                     |
| ---------------- | ------ | -------- | ------------- | --------------------------------------------------------- |
| `name`           | string | yes      | —             | Display name; slugified for the subdomain and DNS name.   |
| `type`           | string | no       | `paper`       | One of `paper`\|`forge`\|`fabric`\|`vanilla`\|`purpur`.   |
| `version`        | string | no       | `1.21.4`      | Minecraft version string.                                 |
| `loader_version` | string | no       | image default | Loader/software version. See table below.                 |
| `port`           | int    | no       | `25565`       | Host port (1024–65535), must be unique across servers.    |
| `mem_min`        | int    | no       | `2`           | Minimum JVM heap, GB.                                     |
| `mem_max`        | int    | no       | `4`           | Maximum JVM heap, GB.                                     |
| `subscription`   | string | no       | env default   | `premium` or `free` (PlayIT).                             |
| `agent`          | string | no       | env default   | PlayIT agent name.                                        |
| `properties`     | object | no       | defaults      | Initial `server.properties` values to apply during setup. |

`loader_version` values by server type:

| Type     | Valid values                                                      |
| -------- | ----------------------------------------------------------------- |
| `forge`  | `"RECOMMENDED"` (default) · `"LATEST"` · specific e.g. `"47.3.0"` |
| `fabric` | specific e.g. `"0.15.11"` · omit / `null` for latest              |
| `quilt`  | specific version · omit / `null` for latest                       |
| others   | not used — ignored if provided                                    |

Response `201`:

```json
{
  "success": true,
  "message": "Server provisioned successfully",
  "server_id": 1,
  "connect_address": "survival-smp.example.com",
  "tunnel_address": "abc123.mcjoin.link",
  "external_port": 34567
}
```

You can apply `server.properties` during setup by including a `properties` object:

```json
{
  "name": "Survival SMP",
  "type": "paper",
  "port": 25565,
  "properties": {
    "motd": "Welcome to the server",
    "difficulty": "hard",
    "max-players": "20"
  }
}
```

If default server properties are configured, they are merged first and request-level
`properties` override them key-by-key.

#### `DELETE /api/servers/<id>`

Stops and removes the container, deletes the data directory and all backups, tears down
the PlayIT tunnel and Cloudflare records, and deletes the database row.

---

### Server Lifecycle

| Method | Path                        | Notes                                                              |
| ------ | --------------------------- | ------------------------------------------------------------------ |
| `POST` | `/api/servers/<id>/start`   | Starts the container.                                              |
| `POST` | `/api/servers/<id>/stop`    | Sends RCON `stop`, then `docker stop` as a fallback (60s timeout). |
| `POST` | `/api/servers/<id>/restart` | `docker restart` (60s timeout).                                    |
| `POST` | `/api/servers/<id>/kill`    | `docker kill` — immediate, ungraceful.                             |

All return `{"success": true/false, "message": "..."}`.

---

### Console & Stats

#### `POST /api/servers/<id>/command`

Body: `{"command": "say Hello, world!"}`. Runs the command via `rcon-cli` inside the
container and returns its output.

```json
{ "success": true, "message": "Command sent", "output": "" }
```

#### `GET /api/servers/<id>/logs?tail=200`

Returns the last `tail` lines (default 200) of container log output.

```json
{
  "success": true,
  "data": ["[12:00:00] [Server thread/INFO]: Done (1.234s)!", "..."]
}
```

#### `GET /api/servers/<id>/console/stream?token=<jwt>`

Server-Sent Events stream of live console output (`docker logs --follow`). Because
`EventSource` cannot set request headers, the JWT is passed as a **query parameter**
instead of an `Authorization` header — use a short-lived token and HTTPS in production.

```js
const es = new EventSource(`/api/servers/1/console/stream?token=${token}`);
es.addEventListener("log", (e) => console.log(e.data));
```

#### `GET /api/servers/<id>/stats`

```json
{
  "success": true,
  "data": {
    "running": true,
    "status": "running",
    "health": "healthy",
    "cpu_percent": 12.4,
    "memory_usage_bytes": 2147483648,
    "memory_limit_bytes": 4294967296,
    "players_raw": "There are 2 of a max of 20 players online: Steve, Alex"
  }
}
```

---

### Server Modification

#### `PATCH /api/servers/<id>/name`

Body: `{"name": "New Name"}`. Database-only rename (does not affect the container or DNS).

#### `PATCH /api/servers/<id>/port`

Body: `{"port": 25566}`. Updates the DB then **recreates the container** (stop → remove →
run) with the new port mapping; world data persists on the bind-mounted volume. Returns a
warning that any existing PlayIT tunnel still points at the old port — call
`POST /api/servers/<id>/tunnel` again if you need the public address updated.

#### `PATCH /api/servers/<id>/ram`

Body: `{"mem_min": 2, "mem_max": 4}` (GB). Updates the DB then recreates the container with
new `INIT_MEMORY`/`MAX_MEMORY` values.

#### `PATCH /api/servers/<id>/version`

Changes the Minecraft version and/or loader version, then **recreates the container**.
World data is preserved on the bind-mounted volume.

Body fields (at least one required):

| Field            | Type           | Notes                                                       |
| ---------------- | -------------- | --------------------------------------------------git--------- |
| `version`        | string         | New Minecraft version, e.g. `"1.21.4"`.                     |
| `loader_version` | string \| null | New loader version. `null` clears it (image picks default). |

Examples:

```json
{ "version": "1.21.4" }
{ "loader_version": "47.3.0" }
{ "version": "1.21.1", "loader_version": "RECOMMENDED" }
{ "loader_version": null }
```

Response:

```json
{
  "success": true,
  "message": "Version updated, container recreated. Allow a few minutes for download.",
  "version": "1.21.1",
  "loader_version": "RECOMMENDED"
}
```

---

### server.properties

#### Default server properties

These endpoints manage the default `server.properties` values automatically applied to
new servers during provisioning.

##### `GET /api/defaults/properties`

Returns the currently configured default server properties.

##### `PUT /api/defaults/properties`

Replace the full default properties set.

Body:

```json
{
  "properties": {
    "motd": "Welcome!",
    "difficulty": "normal",
    "max-players": "20"
  }
}
```

##### `PATCH /api/defaults/properties`

Merge/update selected default properties.

##### `DELETE /api/defaults/properties`

Clears all default properties, or only selected keys.

Body to delete selected keys:

```json
{ "keys": ["motd", "difficulty"] }
```

Blacklisted keys such as `server-port`, `enable-rcon`, `rcon.port`, and
`rcon.password` are rejected here too.

#### `GET /api/servers/<id>/properties`

```json
{
  "success": true,
  "properties": {
    "motd": "A Minecraft Server",
    "difficulty": "easy",
    "max-players": "20"
  }
}
```

#### `PATCH /api/servers/<id>/properties`

Body: `{"properties": {"motd": "Welcome!", "difficulty": "hard"}}`.

```json
{
  "success": true,
  "changed": ["motd", "difficulty"],
  "rejected": [],
  "restart_required": true
}
```

Keys pinned by the container's environment variables (`server-port`, `enable-rcon`,
`rcon.port`, `rcon.password`) are rejected — they'd be silently overwritten by the image on
the next container start anyway. Restart the server (`POST /<id>/restart`) to apply changes.

---

### Players

#### Player list & roster management

| Method   | Path                          | Body                                     | Notes                                                                           |
| -------- | ----------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------- |
| `GET`    | `/api/servers/<id>/players`   | —                                        | `{online, whitelist, ops, banned}`. `online` requires the server to be running. |
| `POST`   | `/api/servers/<id>/whitelist` | `{"username": "Steve"}`                  | Legacy endpoint. Requires running server.                                       |
| `DELETE` | `/api/servers/<id>/whitelist` | `{"username": "Steve"}`                  | Legacy endpoint. Requires running server.                                       |
| `POST`   | `/api/servers/<id>/ops`       | `{"username": "Steve"}`                  | Legacy endpoint. Requires running server.                                       |
| `DELETE` | `/api/servers/<id>/ops`       | `{"username": "Steve"}`                  | Legacy endpoint. Requires running server.                                       |
| `POST`   | `/api/servers/<id>/kick`      | `{"username": "Steve", "reason": "AFK"}` | Requires running server.                                                        |

#### Per-player action endpoints

These are direct per-player actions under `/players/<username>/...`.

| Method   | Path                                                    | Body                                                 | Notes                                                                                                            |
| -------- | ------------------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `POST`   | `/api/servers/<id>/players/<username>/gamemode`         | `{"game_mode": "creative"}` or `{"game_mode": 1}`    | Accepts `0-3` or `survival/creative/adventure/spectator`. Uses RCON when running, edits player NBT when stopped. |
| `POST`   | `/api/servers/<id>/players/<username>/kill`             | —                                                    | Runs `/kill <username>`. Requires running server.                                                                |
| `POST`   | `/api/servers/<id>/players/<username>/heal`             | —                                                    | Sets health + food to full. Uses live entity merge when running; NBT edit when stopped.                          |
| `POST`   | `/api/servers/<id>/players/<username>/starve`           | —                                                    | Sets food/saturation to zero. Uses live entity merge when running; NBT edit when stopped.                        |
| `POST`   | `/api/servers/<id>/players/<username>/feed`             | —                                                    | Sets food/saturation to full. Uses live entity merge when running; NBT edit when stopped.                        |
| `POST`   | `/api/servers/<id>/players/<username>/effects`          | `{"effect": "speed", "seconds": 60, "amplifier": 1}` | Adds a status effect to the player. Requires the server to be running.                                           |
| `DELETE` | `/api/servers/<id>/players/<username>/effects`          | —                                                    | Removes all active effects from the player. Requires the server to be running.                                   |
| `DELETE` | `/api/servers/<id>/players/<username>/effects/<effect>` | —                                                    | Removes one specific effect, e.g. `speed` or `minecraft:speed`. Requires the server to be running.               |
| `GET`    | `/api/servers/<id>/players/<username>/position`         | —                                                    | Returns `{x,y,z}`. Uses live RCON entity data when possible, falls back to playerdata file.                      |
| `POST`   | `/api/servers/<id>/players/<username>/teleport`         | `{"x": 100.5, "y": 70, "z": -20}`                    | Teleports immediately via RCON when running; updates saved `Pos` in playerdata when stopped.                     |
| `POST`   | `/api/servers/<id>/players/<username>/whitelist`        | —                                                    | Convenience wrapper for adding to whitelist. Requires running server.                                            |
| `POST`   | `/api/servers/<id>/players/<username>/ban`              | `{"reason": "griefing"}`                             | Convenience wrapper for ban command. Requires running server.                                                    |
| `DELETE` | `/api/servers/<id>/players/<username>/ban`              | —                                                    | Unban. Uses RCON when running, file edit when stopped.                                                           |
| `POST`   | `/api/servers/<id>/players/<username>/op`               | —                                                    | Convenience wrapper for op command. Requires running server.                                                     |

#### Effect endpoints

Effects are live-player operations and require the server to be running.

##### `POST /api/servers/<id>/players/<username>/effects`

Body:

```json
{
  "effect": "speed",
  "seconds": 60,
  "amplifier": 1,
  "hide_particles": true
}
```

Notes:

- `effect` accepts either `speed` or `minecraft:speed` style IDs.
- `seconds` defaults to `30`.
- `amplifier` defaults to `0` and is zero-based, so `1` means Speed II.
- `hide_particles` defaults to `true`.

Example response:

```json
{
  "success": true,
  "message": "Applied effect Speed to PegasusHafen404",
  "effect": "minecraft:speed",
  "seconds": 60,
  "amplifier": 1,
  "hide_particles": true
}
```

##### `DELETE /api/servers/<id>/players/<username>/effects/<effect>`

Removes a single effect from the player.

Example:

```http
DELETE /api/servers/3/players/PegasusHafen404/effects/speed
```

##### `DELETE /api/servers/<id>/players/<username>/effects`

Removes all active effects from the player.

#### Bans (full list)

| Method   | Path                                | Body                                          | Notes                                                                                   |
| -------- | ----------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------- |
| `GET`    | `/api/servers/<id>/bans`            | —                                             | Returns full ban records (uuid, name, reason, created, expires, source). Works offline. |
| `POST`   | `/api/servers/<id>/bans`            | `{"username": "Steve", "reason": "griefing"}` | Requires running server.                                                                |
| `DELETE` | `/api/servers/<id>/bans/<username>` | —                                             | Unban. Uses RCON when running, edits `banned-players.json` directly when stopped.       |

`GET /api/servers/<id>/bans` response:

```json
{
  "success": true,
  "bans": [
    {
      "uuid": "069a79f4-44e9-4726-a5be-fca90e38aaf5",
      "name": "Notch",
      "created": "2024-01-01 12:00:00 +0000",
      "source": "Server",
      "expires": "forever",
      "reason": "griefing"
    }
  ]
}
```

#### Player history

#### `GET /api/servers/<id>/players/history`

Returns every player who has ever joined the server, sourced from `usercache.json`.

```json
{
  "success": true,
  "players": [
    { "name": "Steve", "uuid": "...", "last_seen": "2026-07-04 00:00:00 +0000" }
  ]
}
```

#### Per-player NBT data

Player health, food, inventory, ender chest, and saved position are stored in
`world/playerdata/<uuid>.dat`.

> **Note on live servers**: if a player is currently connected, the server keeps state in
> memory and writes it to disk on disconnect. NBT-based edits can be overwritten in that
> case. Responses include a `"warning"` field when relevant.

##### `GET /api/servers/<id>/players/<username>/data`

Returns health, food, XP level, game mode, full inventory, and ender chest contents.

```json
{
  "success": true,
  "uuid": "069a79f4-...",
  "username": "Steve",
  "health": 20.0,
  "food_level": 20,
  "food_saturation": 5.0,
  "xp_level": 3,
  "game_mode": 0,
  "inventory": [
    { "slot": 0, "id": "minecraft:diamond_sword", "count": 1 },
    { "slot": 9, "id": "minecraft:bread", "count": 32 }
  ],
  "enderchest": [{ "slot": 0, "id": "minecraft:elytra", "count": 1 }]
}
```

Game mode values: `0` Survival, `1` Creative, `2` Adventure, `3` Spectator.

Inventory slot ranges: `0-8` hotbar, `9-35` main inventory, `100-103` armor (feet→head), `-106` offhand.

#### Inventory endpoints

| Method   | Path                                                    | Body                                            | Notes                                                                                                                        |
| -------- | ------------------------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `DELETE` | `/api/servers/<id>/players/<username>/inventory`        | —                                               | Clear the entire inventory. Uses RCON `/clear` when running, NBT edit when stopped.                                          |
| `DELETE` | `/api/servers/<id>/players/<username>/inventory/<slot>` | —                                               | Remove the item at a specific slot. NBT edit (works offline).                                                                |
| `POST`   | `/api/servers/<id>/players/<username>/inventory`        | `{"item_id": "minecraft:diamond", "count": 64}` | Add an item. Uses RCON `/give` when running, NBT edit when stopped. `slot` is optional — first free slot is used if omitted. |

`POST /inventory` body fields:

| Field     | Type   | Required | Default | Notes                                                          |
| --------- | ------ | -------- | ------- | -------------------------------------------------------------- |
| `item_id` | string | yes      | —       | Namespaced item ID, e.g. `minecraft:diamond_sword`.            |
| `count`   | int    | no       | `1`     | Stack size.                                                    |
| `slot`    | int    | no       | auto    | Target inventory slot. Existing item at that slot is replaced. |

#### Ender chest endpoints

| Method   | Path                                                     | Body                                          | Notes                                                                                        |
| -------- | -------------------------------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `DELETE` | `/api/servers/<id>/players/<username>/enderchest`        | —                                             | Clear the entire ender chest. NBT edit (works offline).                                      |
| `DELETE` | `/api/servers/<id>/players/<username>/enderchest/<slot>` | —                                             | Remove the item at the given slot (0-26). NBT edit.                                          |
| `POST`   | `/api/servers/<id>/players/<username>/enderchest`        | `{"item_id": "minecraft:elytra", "count": 1}` | Add an item to the ender chest. `slot` (0-26) is optional — first free slot used if omitted. |

#### Statistics endpoint

#### `GET /api/servers/<id>/players/<username>/statistics`

Returns aggregated player statistics sourced from `world/stats/<uuid>.json`.

```json
{
  "success": true,
  "username": "Steve",
  "uuid": "069a79f4-...",
  "statistics": {
    "playtime_ticks": 123456,
    "playtime_seconds": 6172,
    "playtime_hours": 1.71,
    "deaths": 2,
    "player_kills": 5,
    "kd": 2.5,
    "distance_traveled_blocks": 8421.32,
    "blocks_removed": 913,
    "blocks_added": 401,
    "items_used": 2021,
    "entities_killed": 87
  }
}
```

#### Selective player reset/delete endpoint

#### `DELETE /api/servers/<id>/players/<username>/data`

Selective data reset/deletion. Accepts either a `target` string or a `targets` array.

Valid targets:

- `xp`
- `inventory`
- `enderchest`
- `playerdata`
- `statistics`
- `advancements`
- `everything`

Examples:

```json
{ "target": "everything" }
```

```json
{ "targets": ["xp", "inventory", "statistics"] }
```

Response:

```json
{
  "success": true,
  "message": "Applied player data reset for Steve",
  "deleted": ["inventory", "statistics", "xp"],
  "not_found": []
}
```

For running servers, responses may include a warning because online players can overwrite
disk-based edits on disconnect.

---

### Backups

Three backup types are supported. Specify `{"type": "..."}` in the request body.

| Type   | Description                                                                          | Speed   | Disk use  | Download                   |
| ------ | ------------------------------------------------------------------------------------ | ------- | --------- | -------------------------- |
| `zip`  | Compressed archive stored in `BACKUPS_DIR`. Default.                                 | Slow    | Low       | ✓                          |
| `copy` | Plain directory copy in `BACKUPS_DIR`. No compression.                               | Fast    | High      | ✓ (zipped on-the-fly)      |
| `zfs`  | Instant ZFS snapshot of the server’s dataset. Requires `ZFS_DATASET_BASE` to be set. | Instant | Near-zero | ✘ (use `zfs send` on host) |

#### ZFS requirements

1. Set `ZFS_DATASET_BASE=tank/cscm/servers` in `.env` — each server must have its own child dataset (e.g. `tank/cscm/servers/3`).
2. Mount the host `zfs` binary into the container (`-v /sbin/zfs:/usr/local/bin/zfs:ro`) and expose `/dev/zfs`.
3. The container needs the `SYS_ADMIN` capability or equivalent ZFS privilege.

Restore rolls back via `zfs rollback -r <snapshot>` (destroys newer snapshots). Back up your snapshot list before restoring.

| Method   | Path                                             | Body                                                                     | Notes                                                                      |
| -------- | ------------------------------------------------ | ------------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| `GET`    | `/api/servers/<id>/backups`                      | —                                                                        | List backups, newest first. Each entry includes `backup_type`.             |
| `POST`   | `/api/servers/<id>/backups`                      | `{"type": "zip"}` (optional)                                             | Create a manual backup. Defaults to `zip`.                                 |
| `GET`    | `/api/servers/<id>/backups/<backup_id>/download` | —                                                                        | Download as `.zip`. Copy backups are zipped on-the-fly. ZFS returns `400`. |
| `DELETE` | `/api/servers/<id>/backups/<backup_id>`          | —                                                                        | Delete record and archive/snapshot.                                        |
| `POST`   | `/api/servers/<id>/backups/<backup_id>/restore`  | —                                                                        | Stop server, restore data, restart.                                        |
| `GET`    | `/api/servers/<id>/backups/schedule`             | —                                                                        | Returns `{cron, retention, enabled, backup_type}` or `{"schedule": null}`. |
| `PUT`    | `/api/servers/<id>/backups/schedule`             | `{"cron": "0 4 * * *", "retention": 5, "enabled": true, "type": "copy"}` | Create/update a scheduled backup. `type` defaults to `zip`.                |
| `DELETE` | `/api/servers/<id>/backups/schedule`             | —                                                                        | Remove the schedule.                                                       |

Scheduled backups are pruned to `retention` most-recent copies after each run (manual
backups are never auto-pruned).

---

### Files

Operate directly on a server's data directory (`SERVERS_DIR/<id>/`). All paths are
relative and guarded against traversal outside the server's directory.

| Method   | Path                                             | Notes                                            |
| -------- | ------------------------------------------------ | ------------------------------------------------ |
| `GET`    | `/api/servers/<id>/files?path=subdir`            | List directory entries (`name`, `type`, `size`). |
| `GET`    | `/api/servers/<id>/files/download?path=file.txt` | Download a file.                                 |
| `POST`   | `/api/servers/<id>/files/upload?path=subdir`     | multipart/form-data, field `file`.               |
| `DELETE` | `/api/servers/<id>/files/delete?path=file.txt`   | Delete a single file.                            |

Upload behavior:

- Any non-existing `path` is treated as a directory path and will be created automatically if needed.
- Nested directories like `path=mods/plugins/custom` are supported.
- Directory names containing dots are also supported, e.g. `path=configs/v1.0`.
- The uploaded file keeps its original filename by default.
- Optionally provide `filename=plugin.jar` to rename the uploaded file inside the target directory.

Examples:

```http
POST /api/servers/3/files/upload?path=mods/plugins/custom
```

```http
POST /api/servers/3/files/upload?path=mods/plugins/custom&filename=my-plugin.jar
```

---

### Networking

#### `POST /api/servers/<id>/tunnel`

Body (all optional): `{"region": "Germany", "subscription": "premium", "agent": "EU-Central"}`.
Creates a PlayIT tunnel and Cloudflare CNAME + SRV records for an existing server (e.g.
after a port change).

#### `PATCH /api/servers/<id>/subdomain`

Body: `{"subdomain": "new-name"}`. Deletes old Cloudflare DNS records and creates new ones
under the given subdomain, pointing at the existing tunnel.

---

## CLI Scripts

For quick testing without running the full API:

```bash
python scripts/init_db.py                          # initialize the local database
python main.py --name "Test SMP" --type paper --version 1.21.4 --port 25565
python delete_server.py <db_server_id>              # interactive confirm + full teardown
```

## OpenAPI Spec

A static OpenAPI 3.0 document describing every endpoint lives at `openapi.yaml` in the
repo root. Import it into Postman, Insomnia, or any OpenAPI-compatible tool for
interactive exploration.

## Security Notes

- **The Docker socket is root-equivalent.** CSCM mounts `/var/run/docker.sock` to manage
  server containers — anyone who can reach the CSCM API with a valid JWT can, transitively,
  do anything on the host that root can do via Docker. Keep the API behind a firewall/VPN,
  use a strong admin password, and don't expose it directly to the internet.
- Every container CSCM touches is filtered by the `cscm.managed=true` and
  `cscm.server_id=<id>` labels — it never operates on containers it didn't create.
- RCON has no exposed port; commands run via `docker exec rcon-cli` inside the container.
- The console SSE endpoint accepts the JWT as a query parameter (`?token=`) because
  `EventSource` cannot set custom headers — use HTTPS in production so the token isn't
  visible in transit or in server access logs.
- File endpoints resolve and validate every path against the server's own data directory
  to prevent path traversal.

## Troubleshooting

**Server stuck in `starting` forever.** Large modpacks (Forge) or first-time Paper/Purpur
downloads can take minutes. Check `GET /api/servers/<id>/logs` for download progress or
errors. If health checks never pass, check `docker logs cscm-mc-<id>` on the host for the
full picture.

**`SERVERS_DIR_HOST` / `SERVERS_DIR` mismatch.** Symptoms: a server's container starts but
`server.properties`/files never appear, or file endpoints see an empty directory. Confirm
both paths resolve to the same physical location — see [Configuration](#configuration).

**Port already in use.** `POST /api/servers` and `PATCH /<id>/port` return `409` if the
requested port collides with another CSCM-managed server (DB-level uniqueness) or the
Docker daemon rejects it because something else on the host is already bound to it.

**PlayIT tunnel creation fails.** The PlayIT automation drives a real browser session via
Playwright — confirm `PLAYIT_EMAIL`/`PLAYIT_PASSWORD` are correct and, if running headless,
that Chromium's dependencies are installed (the provided `Dockerfile` handles this).
