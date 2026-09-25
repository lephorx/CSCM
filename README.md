# CSCM

CSCM is one web application for creating and managing Minecraft servers. The
Next.js dashboard serves the UI and proxies `/api/*` requests to the Flask API.
Docker Compose starts both processes as one stack; only the dashboard port is
published. The API, database, Docker access, backups, and server files remain
inside the stack or on the configured host paths.

The repository combines the complete histories of `CSCM-Tool` and
`CSCM-Webpage`. Their previously uncommitted changes are included in this
working tree.

## Start with Docker Compose

1. Copy `.env.example` to `.env` and set `SERVERS_DIR_HOST` and
   `BACKUPS_DIR_HOST` to absolute paths on the Docker host. Configure the
   PlayIT and Cloudflare values if you want public addresses. Local-only
   servers do not need those credentials.
2. Start the application:

   ```sh
   docker compose up --build -d
   ```

3. Open `http://localhost:3000` (or the port set by `WEB_PORT`). The first
   visit guides you through creating the local account and TOTP setup.

The dashboard proxies its API requests to `http://api:5000` inside the Compose
network. `GET /health` on the dashboard checks the backend. The SQLite file is
stored at `${DATA_DIR_HOST:-./data}/cscm.db` on the host. The application
needs access to the host Docker socket to manage Minecraft containers.

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

Run the API from `backend/` and the dashboard from `frontend/`:

```sh
cd backend
python -m pip install -r requirements.txt
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
