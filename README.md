# CSCM

CSCM is one web application for creating and managing Minecraft servers. The
Next.js dashboard serves the UI and proxies `/api/*` requests to the Flask API.
Docker Compose starts both processes as one stack; only the dashboard port is
published. The API, database, Docker access, backups, and server files remain
inside the stack or on the configured host paths.

The repository combines the development histories of `CSCM-Tool` and
`CSCM-Webpage`. Old runtime configuration, database and certificate files were
removed from the public history.

## Guided installation

On macOS or Linux, install Docker (with Compose) and Git, then run:

```sh
curl -fsSL https://lephor.com/cscm/install.sh | sh
```

The installer asks a single question (install with the defaults, or pick the
folders and port) and starts the application. For Windows, run it from WSL 2
with Docker Desktop integration enabled.

Everything else is set up in the dashboard right after you create your account:
local-only or public servers, your Playit account, a Playit agent that CSCM runs
for you (paste its `SECRET_KEY`) or one you already run, and optional Cloudflare
custom DNS. Progress is saved as you go, and the values are written to `.env`.
Change them later from the settings button in the top bar, or edit `.env` and run
`docker compose restart api`. On macOS and Windows, enable Docker Desktop host
networking before letting CSCM run the Playit agent.

See the [installation guide](https://lephor.com/wiki/cscm/installation) for
platform instructions and the [usage guide](https://lephor.com/wiki/cscm/usage)
for creating and managing servers.

## Start with Docker Compose

1. Copy `.env.example` to `.env` and set `SERVERS_DIR_HOST` and
   `BACKUPS_DIR_HOST` to absolute paths on the Docker host. Configure the
   PlayIT values if you want public addresses. Add the optional
   `CLOUDFLARE_*` credentials to use a custom DNS name by default. Without
   them, players connect through the PlayIT address. Local-only servers
   do not need either service.
2. Start the application:

   ```sh
   docker compose up --build -d
   ```

3. Open `http://localhost:3000` (or the port set by `WEB_PORT`). The first
   visit guides you through creating the local account. Scan the authenticator
   QR code and enter one current six-digit code to finish registration; the
   dashboard signs you in automatically.

The dashboard proxies its API requests to `http://api:5000` inside the Compose
network. `GET /health` on the dashboard checks the backend. The SQLite file is
stored at `${DATA_DIR_HOST:-./data}/cscm.db` on the host. The application
needs access to the host Docker socket to manage Minecraft containers.

## Updates

The dashboard checks `backend/VERSION` on the `main` branch about once an hour.
When it's newer than the running version, a banner offers a one-click update:
a short-lived helper container runs `git pull --ff-only` and
`docker compose up --build -d` for this installation. `.env` and all data stay
untouched. To publish an update, bump `backend/VERSION` on `main`. Manual
update and troubleshooting: https://lephor.com/wiki/cscm/help

## Move an existing installation

For an existing `CSCM-Tool` deployment, copy its `.env` to this repository
root. Keep `SERVERS_DIR_HOST` and `BACKUPS_DIR_HOST` set to the original
server and backup directories so existing Minecraft containers retain their
data. Copy the active `cscm.db` to `data/cscm.db` before starting the stack.
The database and `.env` are ignored by Git.

In this workspace, the existing local `.env` and active SQLite database have
already been copied. The original server and backup directories remain in
place and are still referenced by the local `.env`.

## Development

For a host-run API, copy `backend/.env.example` to `backend/.env`. Set
`SERVERS_DIR`, `BACKUPS_DIR`, `SERVERS_DIR_HOST`, and `BACKUPS_DIR_HOST` to
writable absolute host paths; each inside/host pair should point to the same
directory. Set `DB_PATH` and `AUTH_DB_PATH` to the same SQLite file, such as
the absolute path of `data/cscm.db`. Then run the API from `backend/` and the
dashboard from `frontend/`:

```sh
cd backend
python -m pip install -r requirements.txt
playwright install chromium
python app.py
```

```sh
cd frontend
pnpm install
CSCM_API_URL=http://localhost:5000 pnpm dev
```

The frontend listens on port 3000 and forwards requests to the API on port
5000. The backend's detailed API documentation is in `backend/README.md` and
`backend/openapi.yaml`.
