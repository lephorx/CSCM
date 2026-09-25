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

ask_secret() {
  [ -r /dev/tty ] || fail "An interactive terminal is required."
  printf '%s: ' "$1" >/dev/tty
  stty -echo </dev/tty
  IFS= read -r ANSWER </dev/tty || { stty echo </dev/tty; fail "Input ended during setup."; }
  stty echo </dev/tty
  printf '\n' >/dev/tty
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
ask "Installation directory (must be empty)" "$HOME/cscm"
INSTALL_DIR=$ANSWER
case "$INSTALL_DIR" in /*) ;; *) fail "Installation directory must be absolute." ;; esac
if [ -e "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
  fail "$INSTALL_DIR is not empty. Choose another directory to protect existing data."
fi

ask "Dashboard port" "3000"
WEB_PORT=$ANSWER
case "$WEB_PORT" in *[!0-9]*|'') fail "Dashboard port must be numeric." ;; esac
[ "$WEB_PORT" -ge 1 ] && [ "$WEB_PORT" -le 65535 ] || fail "Port must be between 1 and 65535."

ask "Persistent data directory" "$HOME/cscm-data"
DATA_DIR=$ANSWER
case "$DATA_DIR" in /*) ;; *) fail "Data directory must be absolute." ;; esac
SERVER_DIR=$DATA_DIR/servers
BACKUP_DIR=$DATA_DIR/backups
DB_DIR=$DATA_DIR/data

ask_yes "Make Minecraft servers publicly reachable through Playit" y
PUBLIC_ACCESS=$ANSWER
PLAYIT_EMAIL=
PLAYIT_PASSWORD=
PLAYIT_AGENT=
PLAYIT_SUBSCRIPTION=free
PLAYIT_REGION=Germany
PLAYIT_SECRET_KEY=
MANAGED_AGENT=no
CF_ENABLED=false
CF_TOKEN=
CF_ZONE=
CF_DOMAIN=

if [ "$PUBLIC_ACCESS" = yes ]; then
  ask "Playit account email" ""
  PLAYIT_EMAIL=$ANSWER
  [ -n "$PLAYIT_EMAIL" ] || fail "Playit email is required for public servers."
  ask_secret "Playit account password"
  PLAYIT_PASSWORD=$ANSWER
  [ -n "$PLAYIT_PASSWORD" ] || fail "Playit password is required for public servers."
  ask "Playit subscription (free/premium)" free
  PLAYIT_SUBSCRIPTION=$ANSWER
  case "$PLAYIT_SUBSCRIPTION" in free|premium) ;; *) fail "Subscription must be free or premium." ;; esac
  if [ "$PLAYIT_SUBSCRIPTION" = premium ]; then
    ask "Playit region" Germany
    PLAYIT_REGION=$ANSWER
  fi
  ask "Playit agent name (blank selects the first available)" ""
  PLAYIT_AGENT=$ANSWER
  ask_yes "Install a managed Playit agent on this device" y
  MANAGED_AGENT=$ANSWER
  if [ "$MANAGED_AGENT" = yes ]; then
    if [ "$PLATFORM" = Darwin ] || grep -qi microsoft /proc/version 2>/dev/null; then
      say "Docker Desktop 4.34+ requires Settings > Resources > Network > Enable host networking."
      ask_yes "Is Docker Desktop host networking enabled" n
      [ "$ANSWER" = yes ] || fail "Enable host networking in Docker Desktop, then run setup again."
    fi
    say "Create or claim an agent at https://playit.gg/account/setup/wizard/new-account/docker/docker-name"
    say "Copy its SECRET_KEY. CSCM runs Playit's official agent image with it."
    ask_secret "Playit agent SECRET_KEY"
    PLAYIT_SECRET_KEY=$ANSWER
    [ -n "$PLAYIT_SECRET_KEY" ] || fail "An agent secret key is required."
  else
    say "Using your existing Playit agent. Keep it running on this host."
  fi
  ask_yes "Use a Cloudflare custom DNS name" n
  if [ "$ANSWER" = yes ]; then
    CF_ENABLED=auto
    ask_secret "Cloudflare API token"
    CF_TOKEN=$ANSWER
    ask "Cloudflare zone ID" ""
    CF_ZONE=$ANSWER
    ask "Cloudflare base domain (example.com)" ""
    CF_DOMAIN=$ANSWER
    [ -n "$CF_TOKEN" ] && [ -n "$CF_ZONE" ] && [ -n "$CF_DOMAIN" ] || fail "All Cloudflare values are required."
  fi
fi

say "Downloading CSCM from $REPO_URL…"
git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" || fail "Could not clone CSCM. Check the repository is public and retry."
mkdir -p "$SERVER_DIR" "$BACKUP_DIR" "$DB_DIR"

{
  env_line WEB_PORT "$WEB_PORT"
  env_line DATA_DIR_HOST "$DB_DIR"
  env_line SERVERS_DIR_HOST "$SERVER_DIR"
  env_line BACKUPS_DIR_HOST "$BACKUP_DIR"
  env_line PLAYIT_EMAIL "$PLAYIT_EMAIL"
  env_line PLAYIT_PASSWORD "$PLAYIT_PASSWORD"
  env_line PLAYIT_HEADLESS true
  env_line PLAYIT_SUBSCRIPTION "$PLAYIT_SUBSCRIPTION"
  env_line PLAYIT_REGION "$PLAYIT_REGION"
  env_line PLAYIT_AGENT "$PLAYIT_AGENT"
  env_line CLOUDFLARE_ENABLED "$CF_ENABLED"
  env_line CLOUDFLARE_API_TOKEN "$CF_TOKEN"
  env_line CLOUDFLARE_ZONE_ID "$CF_ZONE"
  env_line CLOUDFLARE_BASE_DOMAIN "$CF_DOMAIN"
  env_line PLAYIT_SECRET_KEY "$PLAYIT_SECRET_KEY"
  env_line JWT_LIFETIME_HOURS 8
  env_line TOTP_ISSUER CSCM
} > "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/.env"

if [ "$MANAGED_AGENT" = yes ]; then
  cat > "$INSTALL_DIR/docker-compose.override.yml" <<'YAML'
services:
  playit:
    image: ghcr.io/playit-cloud/playit-agent:latest
    restart: unless-stopped
    network_mode: host
    environment:
      SECRET_KEY: ${PLAYIT_SECRET_KEY:?Playit agent key is required}
YAML
fi

say "Starting CSCM…"
cd "$INSTALL_DIR"
docker compose up --build -d
say "CSCM is ready at http://localhost:$WEB_PORT"
say "Open it and create the administrator account. Scan the QR code and enter one authenticator code to finish."
say "Installation: $INSTALL_DIR"
say "Usage guide: https://lephor.com/wiki/cscm/usage"
