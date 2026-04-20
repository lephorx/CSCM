# CSCM-Tool

**Crafty Server Creation Manager** — automated provisioning and deprovisioning of Minecraft game servers.

When a server is created, CSCM-Tool:

1. Creates the game server in **Crafty Controller**
2. Creates a public **PlayIT tunnel** for the server port
3. Resolves the external port via DNS SRV lookup
4. Creates a **Cloudflare CNAME** and **SRV record** so players connect via subdomain

Deprovisioning reverses every step in the correct order and cleans up all resources.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Running the API Server](#running-the-api-server)
- [API Reference](#api-reference)
  - [Authentication](#authentication)
  - [GET /api/server-types](#get-apiserver-types)
  - [GET /api/servers](#get-apiservers)
  - [POST /api/servers](#post-apiservers)
  - [DELETE /api/servers/:id](#delete-apiserversid)
- [CLI Tools](#cli-tools)
  - [main.py — Provision a server](#mainpy--provision-a-server)
  - [delete_server.py — Deprovision a server](#delete_serverpy--deprovision-a-server)
- [Logging](#logging)

---

## Prerequisites

| Requirement           | Notes                                                                         |
| --------------------- | ----------------------------------------------------------------------------- |
| Python 3.12+          | Tested on 3.12 and 3.13                                                       |
| Crafty Controller 4.x | Reachable via HTTPS (self-signed cert is fine)                                |
| PlayIT.gg account     | Email/password login                                                          |
| Cloudflare account    | Zone with API token and write access                                          |
| PostgreSQL database   | [Neon](https://neon.tech) (free tier works) or any Postgres instance with SSL |
| Chromium              | Installed automatically by Playwright                                         |

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-org/CSCM-Tool.git
cd CSCM-Tool

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # macOS / Linux
# .\venv\Scripts\activate         # Windows

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install the Playwright Chromium browser
playwright install chromium --with-deps

# 5. Copy and fill in the environment file
cp .env.example .env              # then edit .env with your values
```

---

## Environment Variables

Create a `.env` file in the project root (or export the variables directly).

```dotenv
# ── Crafty Controller ──────────────────────────────────────────────────────
BASE_URL=https://localhost:8443       # Crafty base URL (no trailing slash)
CRAFTY_USER=admin                     # Crafty admin username
CRAFTY_PASS=changeme                  # Crafty admin password

# ── Neon / PostgreSQL ──────────────────────────────────────────────────────
DB_NAME=cscm
DB_USER=cscmuser
DB_PASSWORD=changeme
DB_HOST=ep-example.us-east-2.aws.neon.tech
DB_PORT=5432

# ── PlayIT.gg ──────────────────────────────────────────────────────────────
PLAYIT_EMAIL=you@example.com
PLAYIT_PASSWORD=changeme
PLAYIT_HEADLESS=true                  # set to false to watch the browser

# ── Cloudflare ─────────────────────────────────────────────────────────────
CLOUDFLARE_API_TOKEN=your_token_here
CLOUDFLARE_ZONE_ID=your_zone_id_here
CLOUDFLARE_BASE_DOMAIN=example.com    # e.g. homeops.services

# ── Flask API ──────────────────────────────────────────────────────────────
API_KEY=your_secret_token             # omit or leave blank to disable auth
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=false

# ── Logging ────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO                        # DEBUG | INFO | WARNING | ERROR
```

> **Cloudflare API token permissions required:** `Zone.DNS:Edit` for the target zone.

---

## Database Setup

Run the migration script against your PostgreSQL database once before first use:

```bash
psql "$DATABASE_URL" -f migration.sql
```

Or connect manually and run the contents of `migration.sql`. The script is idempotent (`IF NOT EXISTS` guards) so it is safe to re-run.

The migration creates:

| Table            | Purpose                                                 |
| ---------------- | ------------------------------------------------------- |
| `servers`        | Core server record; adds `craftyid` column if upgrading |
| `playit_tunnels` | One row per PlayIT tunnel per server                    |
| `dns_records`    | One row per Cloudflare DNS record per server            |

Both child tables cascade-delete when the parent server row is removed.

---

## Running the API Server

```bash
# Activate venv first if not already active
source venv/bin/activate

python app.py
# INFO  api  Flask listening on 0.0.0.0:5000
```

To run in production behind a WSGI server:

```bash
pip install gunicorn
gunicorn --workers 2 --bind 0.0.0.0:5000 "app:app"
```

---

## API Reference

### Authentication

When `API_KEY` is set, every request must include the token in the `Authorization` header:

```
Authorization: Bearer <API_KEY>
```

Requests without a valid token receive `401 Unauthorized`. When `API_KEY` is not configured, authentication is disabled.

---

### GET /api/server-types

Returns the list of supported Minecraft server flavours.

**Response**

```json
{
  "server_types": ["paper", "forge", "fabric", "vanilla", "spigot", "purpur"]
}
```

**Example**

```bash
curl http://localhost:5000/api/server-types \
  -H "Authorization: Bearer $API_KEY"
```

---

### GET /api/servers

Returns all provisioned servers with their linked tunnel and DNS details.

**Response**

```json
{
  "servers": [
    {
      "id": 1,
      "name": "Survival SMP",
      "type": "paper",
      "version": "1.21.4",
      "port": 25565,
      "crafty_id": "abc123",
      "created_at": "2026-04-20T10:00:00",
      "tunnels": [
        {
          "tunnel_name": "survival-smp",
          "tunnel_address": "auto.playit.gg",
          "local_port": 25565,
          "external_port": 30712
        }
      ],
      "dns_records": [
        {
          "type": "CNAME",
          "name": "survival-smp.example.com",
          "target": "auto.playit.gg",
          "port": null,
          "cf_id": "cf_record_id_1"
        },
        {
          "type": "SRV",
          "name": "_minecraft._tcp.survival-smp.example.com",
          "target": "auto.playit.gg",
          "port": 30712,
          "cf_id": "cf_record_id_2"
        }
      ]
    }
  ]
}
```

**Example**

```bash
curl http://localhost:5000/api/servers \
  -H "Authorization: Bearer $API_KEY"
```

---

### POST /api/servers

Provisions a full server stack: Crafty game server, PlayIT tunnel, and Cloudflare DNS records.

**Request body** (JSON)

| Field     | Type    | Required | Default  | Description                                                               |
| --------- | ------- | -------- | -------- | ------------------------------------------------------------------------- |
| `name`    | string  | yes      | —        | Server display name. Used as the subdomain slug.                          |
| `type`    | string  | no       | `paper`  | Server flavour: `paper`, `forge`, `fabric`, `vanilla`, `spigot`, `purpur` |
| `version` | string  | no       | `1.21.4` | Minecraft version                                                         |
| `port`    | integer | no       | `25565`  | Local server port (1024–65535)                                            |
| `mem_min` | integer | no       | `2`      | Minimum JVM heap in GB                                                    |
| `mem_max` | integer | no       | `4`      | Maximum JVM heap in GB                                                    |

**Response** `201 Created`

```json
{
  "success": true,
  "server_id": 1,
  "connect_address": "survival-smp.example.com",
  "external_port": 30712,
  "message": "Server provisioned successfully"
}
```

**Error responses**

| Status | Cause                                                                    |
| ------ | ------------------------------------------------------------------------ |
| `400`  | Missing `name`, invalid `type`, invalid `port`, or invalid memory values |
| `500`  | Crafty, PlayIT, Cloudflare, or database error during provisioning        |

**Example**

```bash
curl -X POST http://localhost:5000/api/servers \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Survival SMP",
    "type": "paper",
    "version": "1.21.4",
    "port": 25565,
    "mem_min": 2,
    "mem_max": 4
  }'
```

---

### DELETE /api/servers/:id

Deprovisions a server by its database ID. Deletes the Crafty server, PlayIT tunnel, all Cloudflare DNS records, and the database entry (cascades to tunnels and DNS rows).

**URL parameter:** `id` — integer database ID from `GET /api/servers`

**Response** `200 OK`

```json
{
  "success": true,
  "message": "Server 'Survival SMP' deleted successfully"
}
```

**Error responses**

| Status | Cause                       |
| ------ | --------------------------- |
| `401`  | Missing or invalid API key  |
| `404`  | No server with that ID      |
| `500`  | Error during deprovisioning |

**Example**

```bash
curl -X DELETE http://localhost:5000/api/servers/1 \
  -H "Authorization: Bearer $API_KEY"
```

---

## CLI Tools

### main.py — Provision a server

```bash
python main.py [options]
```

| Flag        | Default                 | Description           |
| ----------- | ----------------------- | --------------------- |
| `--name`    | `Minecraft test server` | Server display name   |
| `--type`    | `paper`                 | Server flavour        |
| `--version` | `1.21.4`                | Minecraft version     |
| `--port`    | `25565`                 | Local server port     |
| `--mem-min` | `2`                     | Minimum JVM heap (GB) |
| `--mem-max` | `4`                     | Maximum JVM heap (GB) |

**Examples**

```bash
# Provision with defaults
python main.py

# Provision a Forge server on a custom port
python main.py --name "Modded World" --type forge --version 1.20.1 --port 25570 --mem-min 4 --mem-max 8
```

---

### delete_server.py — Deprovision a server

Interactive CLI that shows a summary of all linked resources and asks for confirmation before deleting anything.

```bash
# Pass the database ID as an argument
python delete_server.py 1

# Or run without arguments to be prompted
python delete_server.py
```

Deprovisioning order:

1. Delete Crafty game server
2. Delete PlayIT tunnel (browser automation)
3. Delete Cloudflare DNS records
4. Delete database row (cascades to tunnel and DNS rows)

---

## Logging

Log level is controlled by the `LOG_LEVEL` environment variable:

| Value     | Output                                            |
| --------- | ------------------------------------------------- |
| `DEBUG`   | All internal steps, selectors, and HTTP responses |
| `INFO`    | High-level lifecycle events (default)             |
| `WARNING` | Non-fatal issues that may need attention          |
| `ERROR`   | Failures that stop an operation                   |

Colors are applied automatically when outputting to a terminal. To watch browser automation in real time, set `PLAYIT_HEADLESS=false`.
