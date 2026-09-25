#!/bin/sh
# CSCM interactive installer, published at https://lephor.com/cscm/install.sh
# Usage: curl -fsSL https://lephor.com/cscm/install.sh | sh
set -eu
umask 077

REPO_URL=${CSCM_REPO_URL:-https://github.com/lephorx/CSCM.git}
ANSWER=

say() { printf '%s\n' "$*" >&2; }
fail() { say "Error: $*"; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "$1 is required. See https://lephor.com/wiki/cscm/installation"; }

ask() {
  prompt=$1
  default=$2
  [ -r /dev/tty ] || fail "An interactive terminal is required."
  if [ -n "$default" ]; then
    printf '%s [%s]: ' "$prompt" "$default" >/dev/tty
  else
    printf '%s: ' "$prompt" >/dev/tty
  fi
  IFS= read -r ANSWER </dev/tty || fail "Input ended during setup."
  [ -n "$ANSWER" ] || ANSWER=$default
}

ask_yes() {
  ask "$1 (y/n)" "$2"
  case "$ANSWER" in
    y|Y|yes|YES) ANSWER=yes ;;
    n|N|no|NO) ANSWER=no ;;
    *) fail "Please answer y or n." ;;
  esac
}

# Single-quoted dotenv values preserve spaces, # and $ without interpolation.
env_line() {
  key=$1
  value=$2
  case "$value" in *'
'*) fail "$key must be a single line." ;; esac
  escaped=$(printf '%s' "$value" | sed "s/'/\\\\'/g")
  printf "%s='%s'\n" "$key" "$escaped"
}

need git
need docker
need sed
docker compose version >/dev/null 2>&1 || fail "Docker Compose is required. Install Docker Desktop or the Compose plugin."
docker info >/dev/null 2>&1 || fail "Start Docker and grant this user access to the Docker daemon."

case "$(uname -s)" in
  Linux|Darwin) PLATFORM=$(uname -s) ;;
  *) fail "For Windows, use WSL 2 and follow https://lephor.com/wiki/cscm/installation" ;;
esac

say "CSCM setup ($PLATFORM)"
INSTALL_DIR=$HOME/cscm
WEB_PORT=3000
DATA_DIR=$HOME/cscm-data
say "Defaults: install to $INSTALL_DIR, data in $DATA_DIR, dashboard on port $WEB_PORT."
ask_yes "Install with these defaults" y
if [ "$ANSWER" = no ]; then
  ask "Installation directory (must be empty)" "$INSTALL_DIR"
  INSTALL_DIR=$ANSWER
  ask "Dashboard port" "$WEB_PORT"
  WEB_PORT=$ANSWER
  ask "Persistent data directory" "$DATA_DIR"
  DATA_DIR=$ANSWER
fi
case "$INSTALL_DIR" in /*) ;; *) fail "Installation directory must be absolute." ;; esac
if [ -e "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
  fail "$INSTALL_DIR is not empty. Choose another directory to protect existing data."
fi
case "$WEB_PORT" in *[!0-9]*|'') fail "Dashboard port must be numeric." ;; esac
[ "$WEB_PORT" -ge 1 ] && [ "$WEB_PORT" -le 65535 ] || fail "Port must be between 1 and 65535."
case "$DATA_DIR" in /*) ;; *) fail "Data directory must be absolute." ;; esac
SERVER_DIR=$DATA_DIR/servers
BACKUP_DIR=$DATA_DIR/backups
DB_DIR=$DATA_DIR/data

say "Downloading CSCM from $REPO_URL…"
git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" || fail "Could not clone CSCM. Check the repository is public and retry."
mkdir -p "$SERVER_DIR" "$BACKUP_DIR" "$DB_DIR"

{
  printf '%s\n' "# CSCM settings. Playit and Cloudflare are set up in the dashboard after you"
  printf '%s\n' "# create your account, or add them here and run: docker compose restart api"
  env_line WEB_PORT "$WEB_PORT"
  env_line DATA_DIR_HOST "$DB_DIR"
  env_line SERVERS_DIR_HOST "$SERVER_DIR"
  env_line BACKUPS_DIR_HOST "$BACKUP_DIR"
  env_line PLAYIT_HEADLESS true
  env_line JWT_LIFETIME_HOURS 8
  env_line TOTP_ISSUER CSCM
} > "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/.env"

say "Starting CSCM…"
cd "$INSTALL_DIR"
docker compose up --build -d
say "CSCM is ready at http://localhost:$WEB_PORT"
say "Open it, create your account, then set up public access (Playit) right in the dashboard."
say "Installation: $INSTALL_DIR"
say "Usage guide: https://lephor.com/wiki/cscm/usage"
