# CSCM API Documentation

**CSCM (Crafty Server Creation Manager)** is a REST API that provisions and manages Minecraft game servers end-to-end: it creates servers in Crafty Controller, sets up PlayIT tunnels for external access, and configures Cloudflare DNS records automatically.

---

## Table of Contents

- [Base URL](#base-url)
- [Authentication](#authentication)
- [Error Format](#error-format)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Native (no Docker)](#native-no-docker)
  - [Docker](#docker)
  - [Environment Variables](#environment-variables)
- [Endpoints](#endpoints)
  - [Health](#health)
  - [Server Types](#server-types)
  - [Servers — CRUD](#servers--crud)
  - [Server Control](#server-control)
  - [Server Modification](#server-modification)
  - [Server Networking](#server-networking)
  - [File Management](#file-management)
- [Schemas](#schemas)
- [Frontend Integration Guide](#frontend-integration-guide)

---

## Base URL

```
http://<host>:5000
```

All API endpoints are prefixed with `/api`.

---

## Authentication

The application now uses a local authentication database, JWT bearer tokens, and TOTP multi-factor authentication.

### First run

Open `/` in a browser. If no local user exists yet, CSCM shows a setup page that requires you to create the first administrator username and password. After setup, the page returns:

- A QR code for authenticator apps such as 1Password, Authy, Google Authenticator, or Microsoft Authenticator
- A manual TOTP secret you can enter if QR scanning is unavailable

### Sign in

After the first user is created, sign in with:

- Username
- Password
- Current 6-digit TOTP code

Successful login returns a JWT. Use it for all protected API endpoints:

```
Authorization: Bearer <jwt_token>
```

If no user exists yet, protected endpoints return:

```json
HTTP 403
{
  "error": "Setup required",
  "setup_required": true
}
```

If the token is missing or invalid, protected endpoints return:

```json
HTTP 401
{
  "error": "Unauthorized"
}
```

---

## Error Format

All errors return JSON with a consistent shape:

```json
{
  "success": false,
  "message": "Human-readable error description"
}
```

Or for validation errors:

```json
{
  "error": "'name' is required"
}
```

---

## Installation

### Prerequisites

| Requirement             | Version              |
| ----------------------- | -------------------- |
| Python                  | 3.12+                |
| PostgreSQL (Neon)       | Any                  |
| Crafty Controller       | 4.x (native install) |
| PlayIT account          | playit.gg            |
| Cloudflare account      | With a managed zone  |
| Docker + Docker Compose | Optional             |

---

### Native (no Docker)

**Step 1: Clone the repository**

```bash
git clone https://github.com/your-org/CSCM-Tool.git
cd CSCM-Tool
```

**Step 2: Create and activate a virtual environment**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Step 3: Install Python dependencies**

```bash
pip install -r requirements.txt
```

**Step 4: Install Playwright browser (required for PlayIT automation)**

```bash
playwright install chromium --with-deps
```

> If this fails on Linux, you may need system dependencies. See [Playwright docs](https://playwright.dev/python/docs/intro).

**Step 5: Configure environment variables**

```bash
cp .env.example .env
# Edit .env with your Crafty, Neon, PlayIT, and Cloudflare credentials
nano .env
```

Key things to check:

- `BASE_URL`: Set to `https://localhost:8443` (or your Crafty Controller address)
- `CRAFTY_SERVERS_DIR`: Must match your Crafty installation directory
- `PLAYIT_EMAIL` / `PLAYIT_PASSWORD`: Your PlayIT account credentials
- `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`, `CLOUDFLARE_BASE_DOMAIN`: Cloudflare setup

**Step 6: Test the database connection**

```bash
python3 -c "from server_manager import _get_db; conn = _get_db(); print('Database connected'); conn.close()"
```

If this fails, check your `DB_*` environment variables in `.env`.

**Step 7: Start the API**

```bash
python app.py
```

The server will start on `http://0.0.0.0:5000` by default. Test it:

```bash
curl http://localhost:5000/health
```

You should see:

```json
{ "status": "ok", "message": "CSCM API is healthy" }
```

---

### Docker

**Step 1: Clone the repository**

```bash
git clone https://github.com/your-org/CSCM-Tool.git
cd CSCM-Tool
```

**Step 2: Configure environment variables**

```bash
cp .env.example .env
nano .env
```

**Important for Docker:** If Crafty Controller is running on the host machine, set:

```env
BASE_URL=https://host.docker.internal:8443
```

This allows the container to reach the host's localhost.

**Step 3: Build and start**

```bash
# Build and start in background
docker compose up -d --build

# View logs
docker compose logs -f

# Stop
docker compose down
```

**Step 4: Test the API**

```bash
curl http://localhost:5000/health
```

**Troubleshooting Docker:**

- **"Cannot reach Crafty"**: Make sure `BASE_URL=https://host.docker.internal:8443` in `.env`
- **"Permission denied" on file uploads**: The Crafty servers directory is mounted read-only (`:ro`). To enable uploads, edit `docker-compose.yml` and change `:ro` to `:rw`:

  ```yaml
  volumes:
    - /var/opt/minecraft/crafty/crafty-4/servers:/crafty/servers:rw
  ```

- **"Playwright not found"**: The Docker image pre-installs Playwright. If you see this, rebuild: `docker compose up --build`

---

### Environment Variables

Create a `.env` file in the project root with the following variables. Copy from `.env.example` for a template:

```bash
cp .env.example .env
# Then edit with your values
```

**CSCM API Configuration:**

```env
FLASK_HOST=0.0.0.0                        # Bind address (0.0.0.0 for all interfaces)
FLASK_PORT=5000                           # Listen port
FLASK_DEBUG=false                         # Enable debug mode (true/false)
AUTH_DB_PATH=auth.db                      # Local SQLite database for usernames, hashes, and TOTP secrets
JWT_LIFETIME_HOURS=8                      # JWT expiry window
TOTP_ISSUER=CSCM Tool                     # Label shown in authenticator apps
LOG_LEVEL=INFO                            # DEBUG | INFO | WARNING | ERROR
```

**Crafty Controller Configuration:**

```env
BASE_URL=https://localhost:8443           # Crafty API base URL
                                          # For Docker, use: https://host.docker.internal:8443
CRAFTY_USER=admin                         # Crafty admin username
CRAFTY_PASS=your_password                 # Crafty admin password
CRAFTY_SERVERS_DIR=/var/opt/minecraft/crafty/crafty-4/servers
                                          # Path to Crafty servers directory on host
```

**PostgreSQL / Neon Database:**

```env
DB_NAME=your_database_name
DB_USER=your_db_username
DB_PASSWORD=your_db_password
DB_HOST=your_host.neon.tech              # For Neon: xxx.neon.tech
DB_PORT=5432
```

**PlayIT Configuration:**

```env
PLAYIT_EMAIL=your_email@example.com
PLAYIT_PASSWORD=your_playit_password
PLAYIT_HEADLESS=true                     # Set to false to watch browser during automation
PLAYIT_SUBSCRIPTION=premium               # premium | free
PLAYIT_REGION=Germany                    # Region for tunnel (premium only)
                                         # Options: Seattle, Los Angeles, Denver, Dallas,
                                         # Chicago, New York, Miami, Germany, United Kingdom,
                                         # Sweden, Poland, Spain, Singapore, Japan,
                                         # Australia, Sao Paulo, Chile, India
PLAYIT_AGENT=                            # Optional: agent name (leave empty for first available)
```

**Cloudflare Configuration:**

```env
CLOUDFLARE_API_TOKEN=your_cf_api_token
CLOUDFLARE_ZONE_ID=your_zone_id
CLOUDFLARE_BASE_DOMAIN=example.com       # Root domain (e.g., homeops.services)
```

---

## Endpoints

---

### Health

#### `GET /`

#### `GET /health`

Simple health check. No authentication required.

**Response `200`:**

```json
{
  "status": "ok",
  "message": "CSCM API is running"
}
```

---

### Server Types

#### `GET /api/server-types`

Returns all supported Minecraft server flavours.

**Response `200`:**

```json
{
  "server_types": ["paper", "forge", "fabric", "vanilla", "purpur"]
}
```

---

### Servers — CRUD

#### `GET /api/servers`

Returns all servers provisioned through CSCM, including their PlayIT tunnels and Cloudflare DNS records.

**Response `200`:**

```json
{
  "servers": [
    {
      "id": 44,
      "name": "Paper Server",
      "type": "paper",
      "version": "1.18.2",
      "port": 25581,
      "crafty_id": "80734f9e-5d32-4b9c-a8a6-061887231cc6",
      "created_at": "2026-04-21T08:55:23.123456",
      "tunnels": [
        {
          "address": "single-washstand.deu.mcjoin.link",
          "local_port": 25581,
          "external_port": 5474
        }
      ],
      "dns_records": [
        {
          "type": "CNAME",
          "name": "paper-server.homeops.services",
          "target": "single-washstand.deu.mcjoin.link",
          "port": null
        },
        {
          "type": "SRV",
          "name": "_minecraft._tcp.paper-server.homeops.services",
          "target": "single-washstand.deu.mcjoin.link",
          "port": 5474
        }
      ]
    }
  ]
}
```

---

#### `POST /api/servers`

Provisions a complete Minecraft server stack:

1. Creates the server in Crafty Controller
2. Starts the server and accepts the EULA
3. Creates a PlayIT tunnel
4. Creates Cloudflare CNAME + SRV DNS records

> ⚠️ This operation takes **30–90 seconds** depending on jar download speed. For Forge servers, the first start runs the installer — it will take several minutes.

**Request body (JSON):**

| Field     | Type    | Required | Default  | Description                                                  |
| --------- | ------- | -------- | -------- | ------------------------------------------------------------ |
| `name`    | string  | ✅       | —        | Display name for the server                                  |
| `type`    | string  | ❌       | `paper`  | Server type: `paper`, `forge`, `fabric`, `vanilla`, `purpur` |
| `version` | string  | ❌       | `1.21.4` | Minecraft version string                                     |
| `port`    | integer | ❌       | `25565`  | Local TCP port (1024–65535)                                  |
| `mem_min` | integer | ❌       | `2`      | Minimum JVM heap in GB                                       |
| `mem_max` | integer | ❌       | `4`      | Maximum JVM heap in GB                                       |

**Example request:**

```json
{
  "name": "Paper Server",
  "type": "paper",
  "version": "1.18.2",
  "port": 25565,
  "mem_min": 2,
  "mem_max": 4
}
```

**Response `201`:**

```json
{
  "success": true,
  "message": "Server provisioned successfully",
  "server_id": 44,
  "crafty_id": "80734f9e-5d32-4b9c-a8a6-061887231cc6",
  "connect_address": "paper-server.homeops.services",
  "tunnel_address": "single-washstand.deu.mcjoin.link",
  "external_port": 5474
}
```

**Response `400` — Validation error:**

```json
{
  "error": "'port' must be an integer between 1024 and 65535"
}
```

**Response `500` — Provisioning error:**

```json
{
  "success": false,
  "message": "Crafty server creation failed: ..."
}
```

---

#### `DELETE /api/servers/<id>`

Deprovisions a server and **all associated resources**:

- Deletes the Crafty server
- Deletes the PlayIT tunnel (browser automation)
- Deletes all Cloudflare DNS records
- Removes the database row

**URL parameter:** `id` — The database `server_id` (integer) from `GET /api/servers`.

**Response `200`:**

```json
{
  "success": true,
  "message": "Server 'Paper Server' deleted successfully"
}
```

**Response `404`:**

```json
{
  "success": false,
  "message": "No server found with ID 44"
}
```

---

### Server Control

All control endpoints use the database `server_id` (integer), not the Crafty UUID.

#### `POST /api/servers/<id>/start`

Starts the server.

**Response `200`:**

```json
{ "success": true, "message": "Start command sent" }
```

---

#### `POST /api/servers/<id>/stop`

Gracefully stops the server (sends the `stop` command).

**Response `200`:**

```json
{ "success": true, "message": "Stop command sent" }
```

---

#### `POST /api/servers/<id>/restart`

Restarts the server.

**Response `200`:**

```json
{ "success": true, "message": "Restart command sent" }
```

---

#### `POST /api/servers/<id>/kill`

Force-kills the server process immediately (no graceful shutdown).

**Response `200`:**

```json
{ "success": true, "message": "Kill command sent" }
```

---

#### `POST /api/servers/<id>/command`

Sends a console command to a running server's stdin.

**Request body (JSON):**

| Field     | Type   | Required | Description                           |
| --------- | ------ | -------- | ------------------------------------- |
| `command` | string | ✅       | The Minecraft console command to send |

**Example request:**

```json
{ "command": "say Hello from the API!" }
```

**Example requests:**

```json
{ "command": "op PlayerName" }
{ "command": "whitelist add PlayerName" }
{ "command": "time set day" }
{ "command": "stop" }
```

**Response `200`:**

```json
{ "success": true, "message": "Command sent" }
```

---

#### `GET /api/servers/<id>/stats`

Returns live stats for the server fetched from Crafty.

**Response `200`:**

```json
{
  "success": true,
  "data": {
    "running": true,
    "online": 3,
    "max": 20,
    "players": ["Player1", "Player2", "Player3"],
    "cpu": 12.4,
    "mem": 1024.0,
    "desc": "A Minecraft Server",
    "version": "1.18.2"
  }
}
```

> The exact fields returned depend on the Crafty version. Check Crafty's API docs for the full schema.

---

#### `GET /api/servers/<id>/logs`

Returns the server's console log output.

**Response `200`:**

```json
{
  "success": true,
  "data": [
    "[08:55:23] [Server thread/INFO]: Starting minecraft server version 1.18.2",
    "[08:55:25] [Server thread/INFO]: Done (2.341s)! For help, type \"help\""
  ]
}
```

---

### Server Modification

These endpoints modify server configuration. Use the database `server_id` (integer).

#### `PATCH /api/servers/<id>/name`

Renames a server in both Crafty Controller and the database.

**Request body (JSON):**

| Field  | Type   | Required | Description     |
| ------ | ------ | -------- | --------------- |
| `name` | string | ✅       | New server name |

**Example request:**

```json
{ "name": "My New Server Name" }
```

**Response `200`:**

```json
{
  "success": true,
  "message": "Server renamed to 'My New Server Name'"
}
```

**Response `404`:**

```json
{ "success": false, "message": "Server not found" }
```

---

#### `PATCH /api/servers/<id>/port`

Changes the server's listening port in Crafty and the database.

**Request body (JSON):**

| Field  | Type    | Required | Description           |
| ------ | ------- | -------- | --------------------- |
| `port` | integer | ✅       | New port (1024–65535) |

**Example request:**

```json
{ "port": 25566 }
```

**Response `200`:**

```json
{
  "success": true,
  "message": "Port updated to 25566"
}
```

**Response `400` — Invalid port:**

```json
{
  "success": false,
  "message": "'port' must be an integer between 1024 and 65535"
}
```

---

#### `PATCH /api/servers/<id>/ram`

Modifies the JVM heap allocation (minimum and maximum memory).

**Request body (JSON):**

| Field     | Type    | Required | Description            |
| --------- | ------- | -------- | ---------------------- |
| `mem_min` | integer | ✅       | Minimum JVM heap in GB |
| `mem_max` | integer | ✅       | Maximum JVM heap in GB |

**Example request:**

```json
{ "mem_min": 4, "mem_max": 8 }
```

**Response `200`:**

```json
{
  "success": true,
  "message": "RAM updated: 4GB min, 8GB max",
  "execution_command": "java -Xms4000M -Xmx8000M ..."
}
```

**Response `400` — Invalid configuration:**

```json
{
  "success": false,
  "message": "No -Xms/-Xmx flags found in execution command. For Forge servers, edit user_jvm_args.txt directly.",
  "execution_command": "..."
}
```

---

### Server Networking

#### `POST /api/servers/<id>/tunnel`

Creates (or recreates) a PlayIT tunnel and Cloudflare DNS records for a server. This enables external players to connect to your server.

**Request body (JSON, optional):**

| Field          | Type   | Required | Default                       | Description                                |
| -------------- | ------ | -------- | ----------------------------- | ------------------------------------------ |
| `region`       | string | ❌       | `PLAYIT_REGION` env var       | Tunnel region (premium subscriptions only) |
| `subscription` | string | ❌       | `PLAYIT_SUBSCRIPTION` env var | `premium` or `free`                        |
| `agent`        | string | ❌       | First available agent         | PlayIT agent name                          |

**Example request (minimal):**

```json
{}
```

**Example request (premium with region):**

```json
{
  "region": "Germany",
  "subscription": "premium",
  "agent": "EU-Central"
}
```

**Response `201`:**

```json
{
  "success": true,
  "connect_address": "paper-server.homeops.services",
  "tunnel_address": "single-washstand.deu.mcjoin.link",
  "external_port": 5474
}
```

**Response `404`:**

```json
{ "success": false, "message": "No server found with ID 44" }
```

---

#### `PATCH /api/servers/<id>/subdomain`

Renames the Cloudflare DNS subdomain for a server (changes the `<subdomain>` part of `<subdomain>.example.com`).

**Request body (JSON):**

| Field       | Type   | Required | Description               |
| ----------- | ------ | -------- | ------------------------- |
| `subdomain` | string | ✅       | New subdomain (lowercase) |

**Example request:**

```json
{ "subdomain": "awesome-server" }
```

**Response `200`:**

```json
{
  "success": true,
  "message": "Subdomain updated to 'awesome-server.example.com'"
}
```

**Response `400` — Empty subdomain:**

```json
{
  "success": false,
  "message": "'subdomain' is required"
}
```

**Response `404`:**

```json
{ "success": false, "message": "No server found with ID 44" }
```

---

### File Management

All file endpoints operate within the server's Crafty directory:

```
/var/opt/minecraft/crafty/crafty-4/servers/<crafty_uuid>/
```

Path traversal attacks are blocked — any `..` paths return `400`.

---

#### `GET /api/servers/<id>/files`

Lists files and directories inside the server's folder.

**Query parameters:**

| Parameter | Type   | Required | Default   | Description          |
| --------- | ------ | -------- | --------- | -------------------- |
| `path`    | string | ❌       | `` (root) | Subdirectory to list |

**Response `200`:**

```json
{
  "success": true,
  "path": "/",
  "entries": [
    { "name": "mods", "type": "directory", "size": null },
    { "name": "world", "type": "directory", "size": null },
    { "name": "server.properties", "type": "file", "size": 1155 },
    { "name": "paper.jar", "type": "file", "size": 34829667 }
  ]
}
```

---

#### `GET /api/servers/<id>/files/download`

Downloads a file from the server's folder.

**Query parameters:**

| Parameter | Type   | Required | Description                                          |
| --------- | ------ | -------- | ---------------------------------------------------- |
| `path`    | string | ✅       | Relative path to the file (e.g. `server.properties`) |

**Response `200`:** Binary file download with `Content-Disposition: attachment`.

**Example:**

```
GET /api/servers/44/files/download?path=server.properties
```

---

#### `POST /api/servers/<id>/files/upload`

Uploads a file into the server's folder. Accepts `multipart/form-data`.

**Query parameters:**

| Parameter | Type   | Required | Default   | Description                       |
| --------- | ------ | -------- | --------- | --------------------------------- |
| `path`    | string | ❌       | `` (root) | Target subdirectory (e.g. `mods`) |

**Form fields:**

| Field  | Type | Required | Description        |
| ------ | ---- | -------- | ------------------ |
| `file` | file | ✅       | The file to upload |

**Response `201`:**

```json
{
  "success": true,
  "message": "Uploaded mymod.jar",
  "path": "/crafty/servers/80734f9e-.../mods/mymod.jar"
}
```

---

#### `DELETE /api/servers/<id>/files/delete`

Deletes a file from the server's folder.

**Query parameters:**

| Parameter | Type   | Required | Description               |
| --------- | ------ | -------- | ------------------------- |
| `path`    | string | ✅       | Relative path to the file |

**Response `200`:**

```json
{
  "success": true,
  "message": "Deleted banned-players.json"
}
```

---

## Schemas

### Server Object

```ts
interface Server {
  id: number; // Database primary key
  name: string; // Display name
  type: string; // "paper" | "forge" | "fabric" | "vanilla" | "purpur"
  version: string; // Minecraft version e.g. "1.18.2"
  port: number; // Local server port
  crafty_id: string; // Crafty Controller UUID
  created_at: string; // ISO 8601 datetime
  tunnels: Tunnel[];
  dns_records: DnsRecord[];
}

interface Tunnel {
  address: string; // PlayIT tunnel hostname
  local_port: number; // Local port the tunnel forwards to
  external_port: number; // Public port players connect to
}

interface DnsRecord {
  type: "CNAME" | "SRV";
  name: string; // Full DNS name
  target: string; // Tunnel hostname
  port: number | null; // Only present on SRV records
}
```

### File Entry Object

```ts
interface FileEntry {
  name: string;
  type: "file" | "directory";
  size: number | null; // Bytes, null for directories
}
```

### Provision Request

```ts
interface ProvisionRequest {
  name: string; // Required
  type?: "paper" | "forge" | "fabric" | "vanilla" | "purpur"; // Default: "paper"
  version?: string; // Default: "1.21.4"
  port?: number; // Default: 25565, range: 1024–65535
  mem_min?: number; // Default: 2 (GB)
  mem_max?: number; // Default: 4 (GB)
}
```

### Provision Response

```ts
interface ProvisionResponse {
  success: boolean;
  message: string;
  server_id: number; // Database ID
  crafty_id: string; // Crafty UUID
  connect_address: string; // e.g. "paper-server.homeops.services"
  tunnel_address: string; // e.g. "single-washstand.deu.mcjoin.link"
  external_port: number; // Public port
}
```

---

## Frontend Integration Guide

### Recommended Approach

Use the database `id` field (integer) from `GET /api/servers` as the primary key for all subsequent operations — not the `crafty_id`.

### Example: Fetch all servers

```js
const res = await fetch("http://localhost:5000/api/servers", {
  headers: { Authorization: "Bearer iNn6XZBucG6PoZb98qz3A9W9G" },
});
const { servers } = await res.json();
```

### Example: Create a server

```js
const res = await fetch("http://localhost:5000/api/servers", {
  method: "POST",
  headers: {
    Authorization: "Bearer iNn6XZBucG6PoZb98qz3A9W9G",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    name: "My Server",
    type: "paper",
    version: "1.21.4",
    port: 25565,
  }),
});
const result = await res.json();
// result.server_id  ← use this for all control endpoints
```

> ⚠️ Server creation takes 30–90+ seconds. Show a loading state and poll `GET /api/servers/<id>/stats` until `running` is `true`.

### Example: Start / Stop / Restart / Kill

```js
const action = "start"; // or 'stop', 'restart', 'kill'
await fetch(`http://localhost:5000/api/servers/${serverId}/${action}`, {
  method: "POST",
  headers: { Authorization: "Bearer iNn6XZBucG6PoZb98qz3A9W9G" },
});
```

### Example: Send a console command

```js
await fetch(`http://localhost:5000/api/servers/${serverId}/command`, {
  method: "POST",
  headers: {
    Authorization: "Bearer iNn6XZBucG6PoZb98qz3A9W9G",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ command: "say Hello!" }),
});
```

### Example: Poll live stats

```js
async function pollStats(serverId, intervalMs = 3000) {
  const res = await fetch(
    `http://localhost:5000/api/servers/${serverId}/stats`,
    {
      headers: { Authorization: "Bearer iNn6XZBucG6PoZb98qz3A9W9G" },
    },
  );
  const { data } = await res.json();
  // data.running  → boolean
  // data.online   → current player count
  // data.cpu      → CPU usage %
  // data.mem      → RAM usage MB
  return data;
}
```

### Example: Upload a mod file

```js
const formData = new FormData();
formData.append("file", fileInput.files[0]);

await fetch(
  `http://localhost:5000/api/servers/${serverId}/files/upload?path=mods`,
  {
    method: "POST",
    headers: { Authorization: "Bearer iNn6XZBucG6PoZb98qz3A9W9G" },
    body: formData,
  },
);
```

### Example: Browse and download files

```js
// List root
const res = await fetch(`http://localhost:5000/api/servers/${serverId}/files`, {
  headers: { Authorization: "Bearer iNn6XZBucG6PoZb98qz3A9W9G" },
});
const { entries } = await res.json();

// Download a file
window.location.href = `http://localhost:5000/api/servers/${serverId}/files/download?path=server.properties`;
```

### CORS

If your frontend runs on a different origin, add Flask-CORS:

```bash
pip install flask-cors
```

```python
# In app.py
from flask_cors import CORS
CORS(app)
```

Or restrict to specific origins:

```python
CORS(app, origins=["http://localhost:3000", "https://your-frontend.com"])
```
