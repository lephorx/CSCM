# CSCM Tool — API Documentation

The current setup and deployment instructions are in the [repository root](../README.md).
This API is reached through the dashboard's `/api/*` proxy in the combined
Docker Compose stack.

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
                     │   containers          │   itzg/minecraft-server (Java) or
                     │   (cscm-mc-<id>)       │   itzg/minecraft-bedrock-server
                     └──────────────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                     ▼
     PlayIT.gg tunnel                     Cloudflare DNS (CNAME, + SRV for Java)
     (Playwright automation)              (public connect address)
```

CSCM itself runs in one container (or directly on a host with Docker installed). It talks
to the Docker daemon to create, start, stop, and inspect **one container per Minecraft
server**. Java edition servers (`paper`/`forge`/`fabric`/`vanilla`/`purpur`) use the
[`itzg/minecraft-server`](https://github.com/itzg/docker-minecraft-server) image, which
handles jar download/installation, EULA acceptance, and memory limits for every supported
flavor; console commands run via `rcon-cli` inside the container, with no exposed RCON
port. Bedrock edition servers use the separate
[`itzg/minecraft-bedrock-server`](https://github.com/itzg/docker-minecraft-bedrock-server)
image — no JVM, no RCON. Console commands there go through the image's `send-command`
script instead, which does not return output, and player/backup features that depend on
RCON output parsing are Java-only for now.

All application data — servers, tunnels, DNS records, backups, backup schedules, users —
lives in a single local SQLite file. There is no external database to provision or manage.

## Features

- **Self-provisioning**: create a fully configured Minecraft server — 5 Java flavors plus
  Bedrock edition — with one API call, no manual jar/binary downloads, no external panel.
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
| `MC_IMAGE`                                                             | `itzg/minecraft-server:java25`        | Docker image used for Java edition server containers. Must bundle a JRE new enough for the Minecraft version being run (e.g. Minecraft 26.1+ requires Java 25+) — see [itzg's tag list](https://hub.docker.com/r/itzg/minecraft-server/tags) if you need an older JRE for an older Minecraft version. |
| `MC_BEDROCK_IMAGE`                                                     | `itzg/minecraft-bedrock-server`       | Docker image used for `bedrock` type server containers.                                                                                                                                       |
| `MC_CONTAINER_DNS`                                                     | `8.8.8.8,1.1.1.1`                     | Comma-separated DNS servers passed to every Minecraft container. Works around a Docker Desktop quirk (mainly macOS/Windows) where its embedded resolver intermittently fails to resolve jar-download hosts, failing server init. Set to empty (`MC_CONTAINER_DNS=`) to use Docker's default resolver instead. |
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

This creates `servers`, `playit_tunnels`, `dns_records`, `backups`, `backup_schedules`,
`bedrock_player_events` (app data) and `users`, `app_config` (auth data, created by
`auth_manager`). `app.py` also calls this automatically on startup, so a manual run is only
needed for local development outside Docker.

`bedrock_player_events` is an audit log of whitelist/op changes made through the API for
`bedrock` servers — see [Bedrock whitelist & op tracking](#bedrock-whitelist--op-tracking).

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
{ "server_types": ["paper", "forge", "fabric", "vanilla", "purpur", "bedrock"] }
```

`paper`, `forge`, `fabric`, `vanilla`, and `purpur` are Java edition (JVM-based, RCON
enabled). `bedrock` is Bedrock edition — a separate, non-JVM image with no RCON and no
SRV-based port discovery. See the caveats under `POST /api/servers` below.

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
      "local_only": false,
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
    "local_only": false,
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

| Field            | Type   | Required | Default                             | Notes                                                     |
| ---------------- | ------ | -------- | ------------------------------------ | --------------------------------------------------------- |
| `name`           | string | yes      | —                                     | Display name; slugified for the subdomain and DNS name.   |
| `type`           | string | no       | `paper`                               | One of `paper`\|`forge`\|`fabric`\|`vanilla`\|`purpur`\|`bedrock`. |
| `version`        | string | no       | `1.21.4` (`LATEST` for `bedrock`)     | Minecraft version string.                                 |
| `loader_version` | string | no       | image default                        | Loader/software version. See table below. Ignored for `bedrock`. |
| `port`           | int    | no       | `25565` (`19132` for `bedrock`)      | Host port (1024–65535), must be unique across servers.    |
| `mem_min`        | int    | no       | `2`                                   | Minimum JVM heap, GB. Ignored for `bedrock` (no JVM).     |
| `mem_max`        | int    | no       | `4`                                   | Maximum JVM heap, GB. For `bedrock`, used as a container memory cap instead. |
| `subscription`   | string | no       | env default                          | `premium` or `free` (PlayIT). Ignored if `local_only` is true. |
| `agent`          | string | no       | env default                          | PlayIT agent name. Ignored if `local_only` is true.        |
| `local_only`     | bool   | no       | `false`                              | If true, skip the PlayIT tunnel and Cloudflare DNS steps entirely. See below. |
| `properties`     | object | no       | defaults                             | Initial `server.properties` values to apply during setup. |

`loader_version` values by server type:

| Type     | Valid values                                                      |
| -------- | ----------------------------------------------------------------- |
| `forge`  | `"RECOMMENDED"` (default) · `"LATEST"` · specific e.g. `"47.3.0"` |
| `fabric` | specific e.g. `"0.15.11"` · omit / `null` for latest              |
| `quilt`  | specific version · omit / `null` for latest                       |
| others   | not used — ignored if provided                                    |

**`local_only: true`** — for a server that's only meant to be reachable on your own network
(same LAN, or anyone who can already reach this host), not the public internet. Skips the
PlayIT tunnel and Cloudflare DNS steps entirely — provisioning goes straight from "create
the Docker container" to done, no browser automation, no dependency on `PLAYIT_*`/
`CLOUDFLARE_*` being configured. The container's port is still published on the host exactly
as normal (`docker port <container>`/`-p host:container`), so anything that can already
reach this machine — e.g. another device on the same LAN — connects directly via
`<this-host's-LAN-IP>:<port>`. CSCM doesn't attempt to detect or return that IP itself (it
can't reliably know which of a host's network interfaces/addresses a LAN peer should use);
you'll need to know your own host's address.

The provisioning result includes `"local_only": true` and no `connect_address`/
`tunnel_address`/`external_port` fields, since none of those exist for a local-only server.
`local_only` is also reflected per-server in `GET /api/servers` / `GET /api/servers/<id>`.
You can add a public tunnel later without recreating anything — call
`POST /api/servers/<id>/tunnel`, which also flips `local_only` back to `false` once it
succeeds.

**Bedrock caveats** — `type: "bedrock"` provisions an
[`itzg/minecraft-bedrock-server`](https://github.com/itzg/docker-minecraft-bedrock-server)
container instead of the Java image, with a few differences from every other type:

- The host port is published as **UDP**, not TCP (default `19132`).
- `mem_min` is ignored (no JVM heap to size), and the usual `mem_max >= mem_min`
  validation is **not** enforced for `bedrock` — any positive `mem_max` is accepted.
- There is no RCON, so `POST /api/servers/<id>/command` falls back to the image's
  `send-command` script — commands are sent but no output is returned.
- `GET /api/servers/<id>/stats` reports online players differently: `players_online` /
  `player_count` (log-derived) instead of Java's RCON-sourced `players_raw`. See the
  endpoint docs below for the log-scan caveat.
- `GET /api/servers/<id>/players/<username>/statistics` reports something different for
  Bedrock — whitelist/operator status instead of Java's gameplay counters (blocks mined,
  playtime, etc., which don't exist for Bedrock). See the endpoint docs below.
- Minecraft clients discover a Java server's port automatically via a Cloudflare SRV
  record; Bedrock has no equivalent DNS mechanism, so **no SRV record is created**.
  Players must enter the connect address *and* port manually in the Bedrock client. The
  provisioning result includes a `note` field calling this out, and the assigned port is
  always returned as `external_port`.
- Whitelisting and op/deop work for Bedrock, but differently — see
  [Bedrock whitelist & op tracking](#bedrock-whitelist--op-tracking) below. All other
  player-management endpoints under `/api/servers/<id>/players/...` (bans, kicks, gamemode,
  NBT/inventory edits, etc.), and the RCON-based parts of backups (world save flush before
  a backup), are Java-only; they no-op or fail gracefully against a Bedrock server rather
  than crashing.
- `server.properties` has its own dedicated, validated endpoint pair —
  `GET`/`PATCH /api/servers/<id>/bedrock/properties` — since Bedrock's property keys are
  almost entirely different from Java's. `PATCH /api/servers/<id>/bedrock/cheats` is a
  convenience wrapper for the `allow-cheats` property that also restarts the container,
  since that property only takes effect on startup.

Response `202` (provisioning starts in background):

```json
{
  "success": true,
  "message": "Server provisioning started",
  "server_id": 1
}
```

After receiving the `202`, poll `GET /api/servers/<id>/progress` until `percent` reaches
`100` and `status` is `"completed"`. The full server data (tunnel address, DNS records, etc.)
is then available via `GET /api/servers/<id>` — except for a `local_only` server, which has
no tunnel/DNS data since none was created (see `local_only` above).

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

Returns `202` immediately and runs the teardown in the background. Poll
`GET /api/servers/<id>/progress` until `status` is `"completed"`. The server record
disappears from `GET /api/servers` when deletion finishes.

```json
{ "success": true, "message": "Server deletion started", "server_id": 1 }
```

---

### Server Progress

#### `GET /api/servers/<id>/progress`

Returns live progress for the current (or most recent) provisioning or deletion operation.
Poll this endpoint after receiving a `202` from `POST /api/servers` or
`DELETE /api/servers/<id>`.

Example response (during provisioning):

```json
{
  "server_id": 1,
  "action": "provision",
  "status": "in_progress",
  "percent": 35,
  "step": "Creating PlayIT tunnel",
  "message": null,
  "updated_at": "2026-07-05T10:00:00+00:00"
}
```

`status` values:

| Value         | Meaning                                           |
| ------------- | ------------------------------------------------- |
| `idle`        | No operation in progress or recorded              |
| `in_progress` | Operation is running                              |
| `completed`   | Operation finished successfully (`percent` = 100) |
| `failed`      | Operation failed (`message` contains the error)   |

Provisioning steps and approximate percentages:

| %   | Step                                        |
| --- | ------------------------------------------- |
| 5   | Database record created                     |
| 15  | Creating Docker container                   |
| 35  | Creating PlayIT tunnel                      |
| 65  | PlayIT tunnel active — creating DNS records |
| 82  | Creating Cloudflare SRV record              |
| 100 | Server provisioned successfully             |

Deletion steps:

| %   | Step                      |
| --- | ------------------------- |
| 10  | Stopping container        |
| 30  | Removing server data      |
| 50  | Deleting PlayIT tunnel(s) |
| 75  | Removing DNS records      |
| 92  | Cleaning up database      |
| 100 | Server deleted            |

---

### Server Lifecycle

| Method | Path                        | Notes                                                              |
| ------ | --------------------------- | ------------------------------------------------------------------ |
| `POST` | `/api/servers/<id>/start`   | Starts the container.                                              |
| `POST` | `/api/servers/<id>/stop`    | Sends RCON `stop`, then `docker stop` as a fallback (60s timeout). |
| `POST` | `/api/servers/<id>/restart` | `docker restart` (60s timeout).                                    |
| `POST` | `/api/servers/<id>/kill`    | `docker kill` — immediate, ungraceful.                             |
| `POST` | `/api/servers/<id>/recreate` | Stops, removes, and recreates the container from the server's current DB config — no settings change, just rebuilds it against current code. World data is untouched (bind-mounted, not stored in the container). Use this on a server whose container predates a label/behavior change (e.g. it doesn't have the `cscm.type` label a newer version of CSCM relies on) instead of faking an unrelated RAM/version change to force a recreate. |

All return `{"success": true/false, "message": "..."}`.

---

### Console & Stats

#### `POST /api/servers/<id>/command`

Body: `{"command": "say Hello, world!"}`. Runs the command via `rcon-cli` inside the
container and returns its output.

```json
{ "success": true, "message": "Command sent", "output": "" }
```

For `bedrock` servers, this uses the image's `send-command` script instead of RCON, since
Bedrock has no RCON support. The command is sent, but `output` will just confirm delivery
rather than echo the console's response.

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

CPU/memory come straight from the Docker Engine API, so they work the same for every
server type. Player info differs by edition since Bedrock has no RCON:

- Java: `players_raw` — the raw text of RCON's `list` command.
- Bedrock: `players_online` (array of names) and `player_count` (int) instead, since
  there's no RCON response to parse. These are reconstructed by scanning the last 5000
  lines of container logs for the image's `Player connected: <name>, xuid: ...` /
  `Player disconnected: ...` lines and replaying them in order — a player who joined
  further back than that window, without a disconnect line inside it, won't show up.
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
new `INIT_MEMORY`/`MAX_MEMORY` values (`mem_max` becomes a plain container memory cap for
`bedrock` servers instead, since there's no JVM). `mem_max >= mem_min` is only enforced for
Java servers — `mem_min` is ignored for `bedrock`, so any positive value is accepted there.

#### `PATCH /api/servers/<id>/version`

Changes the Minecraft version and/or loader version, then **recreates the container**.
World data is preserved on the bind-mounted volume.

Body fields (at least one required):

| Field | Type | Notes |
| ---------------- | -------------- | --------------------------------------------------git--------- |
| `version` | string | New Minecraft version, e.g. `"1.21.4"`. |
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

#### `PATCH /api/servers/<id>/bedrock/cheats`

**Bedrock-only** (`400` for any other type). Sets `allow-cheats` in `server.properties`
and restarts the container so it takes effect — `allow-cheats` is only read at server
startup; there's no live console toggle for it (unlike `allow-list`).

Body:

```json
{ "enabled": true }
```

Response:

```json
{ "success": true, "message": "Cheats enabled, server restarted", "enabled": true }
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

This endpoint works against any server type (it's a generic key=value file editor), but
Java and Bedrock `server.properties` have almost entirely different key sets — Bedrock has
`allow-cheats`, `level-type`, `server-authoritative-movement`, etc., none of which exist on
Java, and Java's `motd`/`pvp`/`spawn-protection`/etc. don't exist on Bedrock either. This
endpoint doesn't validate keys against either edition, so a typo or a Java-only key sent to
a Bedrock server (or vice versa) is written to the file and silently ignored by the server.
For Bedrock, prefer the dedicated, validated endpoint below instead.

#### `GET /api/servers/<id>/bedrock/properties`

**Bedrock-only** (`400` for any other type). Same response shape as
`GET /api/servers/<id>/properties` above — a separate endpoint mainly so `PATCH` (below)
can validate against Bedrock's actual key set.

#### `PATCH /api/servers/<id>/bedrock/properties`

**Bedrock-only** (`400` for any other type). Like `PATCH /api/servers/<id>/properties`,
but every key is checked against Bedrock's real property list — 60 keys, sourced from
[itzg/docker-minecraft-bedrock-server's `property-definitions.json`](https://github.com/itzg/docker-minecraft-bedrock-server/blob/master/property-definitions.json)
— and keys with a fixed set of allowed values (e.g. `gamemode`, `difficulty`,
`allow-cheats`, `level-type`) are checked against those too. Anything else (unknown key,
or a value not in its allowed set) is rejected instead of being written to the file.

Body: `{"properties": {"allow-cheats": "true", "difficulty": "hard"}}`.

```json
{
  "success": true,
  "changed": ["allow-cheats", "difficulty"],
  "rejected": [],
  "restart_required": true
}
```

If every key in the request is invalid, `changed` is empty and the response also includes
`"error": "No valid Bedrock properties in request"`. Some notable Bedrock-only keys:

| Key | Allowed values | Notes |
| --- | --- | --- |
| `allow-cheats` | `true` \| `false` | Prefer `PATCH /api/servers/<id>/bedrock/cheats` instead — it also restarts the container for you. |
| `gamemode` | `survival` \| `creative` \| `adventure` | |
| `difficulty` | `peaceful` \| `easy` \| `normal` \| `hard` | |
| `level-type` | `DEFAULT` \| `FLAT` \| `LEGACY` | |
| `default-player-permission-level` | `visitor` \| `member` \| `operator` | |
| `allow-list` | `true` \| `false` | Prefer the whitelist endpoints instead (see [Bedrock whitelist & op tracking](#bedrock-whitelist--op-tracking)) — they also keep `allowlist.json` in sync. |

As with the generic endpoint, restart the server to apply changes — except for
`allow-cheats`, which the dedicated `/bedrock/cheats` endpoint already does for you.

---

### Players

#### Player list & roster management

| Method   | Path                          | Body                                     | Notes                                                                           |
| -------- | ----------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------- |
| `GET`    | `/api/servers/<id>/players`   | —                                        | `{online, whitelist, ops, banned}`. `online` requires the server to be running. `whitelist` reads live `allowlist.json` for `bedrock` (`whitelist.json` for Java); `ops` for `bedrock` is derived from tracked events, not a file (see below). |
| `POST`   | `/api/servers/<id>/whitelist` | `{"username": "Steve"}`                  | Legacy endpoint. Requires running server for Java. See [Bedrock whitelist & op tracking](#bedrock-whitelist--op-tracking) for `bedrock` behavior. |
| `DELETE` | `/api/servers/<id>/whitelist` | `{"username": "Steve"}`                  | Legacy endpoint. Requires running server for Java. See [Bedrock whitelist & op tracking](#bedrock-whitelist--op-tracking) for `bedrock` behavior. |
| `POST`   | `/api/servers/<id>/ops`       | `{"username": "Steve"}`                  | Legacy endpoint. Requires running server. See [Bedrock whitelist & op tracking](#bedrock-whitelist--op-tracking) for `bedrock` behavior. |
| `DELETE` | `/api/servers/<id>/ops`       | `{"username": "Steve"}`                  | Legacy endpoint. Requires running server. See [Bedrock whitelist & op tracking](#bedrock-whitelist--op-tracking) for `bedrock` behavior. |
| `POST`   | `/api/servers/<id>/kick`      | `{"username": "Steve", "reason": "AFK"}` | Requires running server. Java-only — Bedrock's console kick isn't wired up yet. |

#### Per-player action endpoints

These are direct per-player actions under `/players/<username>/...`.

| Method   | Path                                                    | Body                                                 | Notes                                                                                                            |
| -------- | ------------------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `POST`   | `/api/servers/<id>/players/<username>/gamemode`         | `{"game_mode": "creative"}` or `{"game_mode": 1}`    | Accepts `0-3` or `survival/creative/adventure/spectator`. Uses RCON when running, edits player NBT when stopped. |
| `POST`   | `/api/servers/<id>/players/<username>/kill`             | `{"message": "Rest in peace"}` (optional)             | Runs `/kill <username>`. Requires running server. If `message` is given, it's broadcast to all players in red via `tellraw` immediately after. |
| `POST`   | `/api/servers/<id>/players/<username>/heal`             | —                                                    | Sets health + food to full. Uses live entity merge when running; NBT edit when stopped.                          |
| `POST`   | `/api/servers/<id>/players/<username>/starve`           | —                                                    | Sets food/saturation to zero. Uses live entity merge when running; NBT edit when stopped.                        |
| `POST`   | `/api/servers/<id>/players/<username>/feed`             | —                                                    | Sets food/saturation to full. Uses live entity merge when running; NBT edit when stopped.                        |
| `POST`   | `/api/servers/<id>/players/<username>/effects`          | `{"effect": "speed", "seconds": 60, "amplifier": 1}` | Adds a status effect to the player. Requires the server to be running.                                           |
| `DELETE` | `/api/servers/<id>/players/<username>/effects`          | —                                                    | Removes all active effects from the player. Requires the server to be running.                                   |
| `DELETE` | `/api/servers/<id>/players/<username>/effects/<effect>` | —                                                    | Removes one specific effect, e.g. `speed` or `minecraft:speed`. Requires the server to be running.               |
| `GET`    | `/api/servers/<id>/players/<username>/position`         | —                                                    | Returns `{x,y,z}`. Uses live RCON entity data when possible, falls back to playerdata file.                      |
| `POST`   | `/api/servers/<id>/players/<username>/teleport`         | `{"x": 100.5, "y": 70, "z": -20}`                    | Teleports immediately via RCON when running; updates saved `Pos` in playerdata when stopped.                     |
| `POST`   | `/api/servers/<id>/players/<username>/whitelist`        | —                                                    | Convenience wrapper for adding to whitelist. Requires running server for Java. For `bedrock` see [Bedrock whitelist & op tracking](#bedrock-whitelist--op-tracking). |
| `POST`   | `/api/servers/<id>/players/<username>/ban`              | `{"reason": "griefing"}`                             | Convenience wrapper for ban command. Requires running server.                                                    |
| `DELETE` | `/api/servers/<id>/players/<username>/ban`              | —                                                    | Unban. Uses RCON when running, file edit when stopped.                                                           |
| `POST`   | `/api/servers/<id>/players/<username>/op`               | —                                                    | Convenience wrapper for op command. Requires running server. For `bedrock` see [Bedrock whitelist & op tracking](#bedrock-whitelist--op-tracking). |

The optional kill `message` is sent via `tellraw @a`, best-effort (a failure to send it
doesn't fail the kill itself). The JSON payload differs by edition, since Bedrock has no
top-level `"color"` key at all:

- Java: `{"text": "<message>", "color": "red"}`
- Bedrock: `{"rawtext": [{"text": "§c<message>"}]}` — `§c` is the built-in red format code,
  embedded directly in the text, since Bedrock's `tellraw` doesn't support a separate
  `color` field the way Java's does.

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

#### Bedrock whitelist & op tracking

Bedrock has neither RCON nor Java's whitelist/ops file formats, so whitelist and op
management for `bedrock` servers work differently from Java under the hood, even though
they use the same endpoints (`/whitelist`, `/ops`, and their `/players/<username>/...`
equivalents above):

- **Whitelist add/remove** (the actual console commands, confirmed against Microsoft's
  Bedrock docs — Bedrock renamed "whitelist" to "allowlist" in 1.18.10):
  - Add: `allowlist add "<name>"` — remove: `allowlist remove "<name>"`.
  - If the server is running, these are sent as real console commands via the image's
    `send-command` script. Since that script returns no output, the result is verified by
    re-reading `allowlist.json` immediately afterward; if the name isn't there (add) or is
    still there (remove), the request reports failure instead of a false success.
  - If the server is **stopped**, there's no console to talk to, so `allowlist.json` is
    edited directly instead — whitelisting still works offline.
  - The first time a name is added, `allow-list=true` is persisted to `server.properties`
    (survives container recreation) and, best-effort, `allowlist on` is sent live if the
    server is running — otherwise the allow-list would silently not be enforced at all.
- **Op/deop**: `op "<name>"` / `deop "<name>"`, requires the server to be running.
  Bedrock's `permissions.json` (the ops-equivalent) is keyed by **XUID only — no
  username field at all**, and the server can only resolve a username to XUID for a
  player it has already seen. So:
  - A player must have **connected to the server at least once** before they can be
    op'd — you'll get a clear error otherwise, rather than a command that silently no-ops.
  - The XUID is resolved from (in order): a live scan of recent connect log lines,
    `allowlist.json` (if it already has an xuid filled in), then CSCM's own tracked
    history. Once resolved, op/deop is verified by re-reading `permissions.json` for a
    matching `{"xuid": ..., "permission": "operator"}` entry (or its absence, for deop).
- **Tracking**: every confirmed whitelist/op change for a `bedrock` server is logged to a
  local `bedrock_player_events` table (server_id, username, xuid, event_type, timestamp).
  This is what powers:
  - `ops` in `GET /api/servers/<id>/players` — Bedrock's `permissions.json` has no names to
    list directly, so this is derived from each username's most recent `op_add`/`op_remove`
    event instead.
  - The `history` array in `GET /api/servers/<id>/players/<username>/statistics` (below).
  - Note this event log only reflects changes made **through this API** — an admin editing
    `allowlist.json`/`permissions.json` directly, or running console commands manually, won't
    appear in it (though `whitelist` in `GET /api/servers/<id>/players` and the `whitelisted`
    field in `/statistics` are always read live from `allowlist.json`, so those two stay
    accurate regardless).

#### Statistics endpoint

#### `GET /api/servers/<id>/players/<username>/statistics`

For Java servers, returns aggregated player statistics sourced from `world/stats/<uuid>.json`:

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

**For `bedrock` servers**, gameplay counters (blocks mined, playtime, kills, etc.) aren't
available — Bedrock stores its whole world, including player data, in LevelDB, a different
storage engine with an undocumented internal key schema, so there's no file to read them
from. Instead this returns whitelist/operator status, sourced from live `allowlist.json` /
`permissions.json` reads plus the tracked event history (see
[Bedrock whitelist & op tracking](#bedrock-whitelist--op-tracking)):

```json
{
  "success": true,
  "username": "Steve",
  "xuid": "2535409695687979",
  "statistics": {
    "whitelisted": true,
    "operator": false
  },
  "history": [
    { "event": "whitelist_add", "xuid": null, "at": "2026-07-05 10:00:00" },
    { "event": "op_remove", "xuid": "2535409695687979", "at": "2026-07-04 22:14:00" },
    { "event": "op_add", "xuid": "2535409695687979", "at": "2026-07-04 21:50:00" }
  ],
  "note": "Gameplay statistics ... aren't available for Bedrock ..."
}
```

`xuid` and `operator` are `null` if the player has never connected — Bedrock resolves
operator status by XUID, which isn't known until a player joins at least once.

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
after a port change). For `bedrock` servers, only the CNAME is created (no SRV — see the
Bedrock caveats under `POST /api/servers`), and the tunnel's assigned port must be shared
with players directly.

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

**Java server crash-loops with "requires running the server with Java N or above".**
`MC_IMAGE`'s bundled JRE is older than what the requested Minecraft version needs (e.g.
Minecraft 26.1+ needs Java 25+, but `MC_IMAGE` is still pinned to a `java21` tag). Check
`GET /api/servers/<id>/logs` for this exact message. Fix: set `MC_IMAGE` to a tag with a
new enough JRE (see [itzg's tag list](https://hub.docker.com/r/itzg/minecraft-server/tags)),
then `POST /api/servers/<id>/recreate` to rebuild the container against it — world data is
untouched.
