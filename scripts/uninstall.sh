#!/bin/sh
# CSCM uninstaller, published at https://lephor.com/cscm/uninstall.sh
# Source: https://github.com/lephorx/CSCM/blob/main/scripts/uninstall.sh
# Usage: curl -fsSL https://lephor.com/cscm/uninstall.sh | sh
#
# Removes what scripts/install.sh set up:
#   - every Minecraft server container CSCM created (label cscm.managed=true)
#   - the Playit agent container the dashboard started (label cscm.playit=true)
#   - the CSCM dashboard containers, their Docker network and locally built images
#   - the installation directory, including .env with your saved credentials
#     (enter its path, or let the script search this computer for it)
#   - optionally: world data, backups and the database (asks separately)
#   - optionally: the downloaded Minecraft and Playit images
#
# It does not touch Docker itself, other containers, or your Playit / Cloudflare
# accounts. Delete your servers in the dashboard first so CSCM removes their
# Playit tunnels and Cloudflare DNS records.
set -eu

ANSWER=

say() { printf '%s\n' "$*" >&2; }
fail() { say "Error: $*"; exit 1; }

ask() {
  prompt=$1
  default=$2
  [ -r /dev/tty ] || fail "An interactive terminal is required."
  if [ -n "$default" ]; then
    printf '%s [%s]: ' "$prompt" "$default" >/dev/tty
  else
    printf '%s: ' "$prompt" >/dev/tty
  fi
  IFS= read -r ANSWER </dev/tty || fail "Input ended."
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

# Read one value from the installer's .env (KEY='value' lines).
env_value() {
  sed -n "s/^$1='\(.*\)'\$/\1/p" "$INSTALL_DIR/.env" | head -n 1 | sed "s/\\\\'/'/g"
}

# Refuse anything that is not a plain absolute directory below /.
safe_dir() {
  case "$1" in
    ''|/|"$HOME"|"$HOME/") return 1 ;;
    /*) return 0 ;;
    *) return 1 ;;
  esac
}

# A CSCM installation has the compose file and CSCM's own Docker manager.
is_cscm_dir() {
  [ -f "$1/docker-compose.yml" ] && grep -q 'cscm.managed' "$1/backend/docker_manager.py" 2>/dev/null
}

# Print every CSCM installation found, one path per line.
find_installs() {
  say "Checking Docker for CSCM containers…"
  docker ps -a --format '{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null \
    | sort -u | while IFS= read -r dir; do
      if [ -n "$dir" ] && is_cscm_dir "$dir"; then printf '%s\n' "$dir"; fi
    done
  for root in "$HOME" /opt /srv; do
    [ -d "$root" ] || continue
    say "Searching $root… (this can take a few minutes)"
    find "$root" \( -name node_modules -o -name .git -o -name Library -o -name .Trash \
      -o -name .cache -o -name .npm -o -name .docker -o -name proc \) -prune \
      -o -type f -path '*/backend/docker_manager.py' -print 2>/dev/null \
      | while IFS= read -r file; do
        dir=$(dirname -- "$(dirname -- "$file")")
        if is_cscm_dir "$dir"; then printf '%s\n' "$dir"; fi
      done
  done
}

# Ask for the installation directory, or search for it.
choose_install() {
  default=
  is_cscm_dir "$HOME/cscm" && default=$HOME/cscm
  ask "CSCM installation directory (or 's' to search this computer)" "${default:-s}"
  case "$ANSWER" in
    s|S|search) ;;
    *) INSTALL_DIR=${ANSWER%/}; return ;;
  esac

  say ""
  say "Searching for CSCM installations. This will take a while, depending on how many"
  say "files you have. You may be asked to allow Terminal to access some folders."
  found=$(find_installs | sort -u)
  [ -n "$found" ] || fail "No CSCM installation found. Run this again and enter its path."

  say ""
  say "Found:"
  i=0
  printf '%s\n' "$found" | while IFS= read -r dir; do
    i=$((i + 1))
    say "  $i) $dir"
  done
  count=$(printf '%s\n' "$found" | grep -c .)
  ask "Number of the installation to remove" 1
  case "$ANSWER" in *[!0-9]*|'') fail "Please enter a number." ;; esac
  [ "$ANSWER" -ge 1 ] && [ "$ANSWER" -le "$count" ] || fail "Please choose 1 to $count."
  INSTALL_DIR=$(printf '%s\n' "$found" | sed -n "${ANSWER}p")
}

# Container-created files can belong to root (e.g. on Linux); fall back to sudo.
remove_dir() {
  [ -e "$1" ] || return 0
  rm -rf -- "$1" 2>/dev/null || {
    say "Some files in $1 belong to root. Retrying with sudo…"
    sudo rm -rf -- "$1"
  }
}

command -v docker >/dev/null 2>&1 || fail "docker is required to remove the CSCM containers."
docker info >/dev/null 2>&1 || fail "Start Docker first, then run this again."

say "CSCM uninstall"
say ""
say "Before you continue: delete your servers in the CSCM dashboard if they use"
say "Playit or Cloudflare. That removes their tunnels and DNS records, which this"
say "script cannot reach."
say ""

INSTALL_DIR=
choose_install
safe_dir "$INSTALL_DIR" || fail "Refusing to use '$INSTALL_DIR'. Give the absolute path of the CSCM folder."
is_cscm_dir "$INSTALL_DIR" \
  || fail "$INSTALL_DIR does not look like a CSCM installation. Run this again and choose 's' to search."

DB_DIR=
SERVER_DIR=
BACKUP_DIR=
if [ -f "$INSTALL_DIR/.env" ]; then
  DB_DIR=$(env_value DATA_DIR_HOST)
  SERVER_DIR=$(env_value SERVERS_DIR_HOST)
  BACKUP_DIR=$(env_value BACKUPS_DIR_HOST)
fi

MC_CONTAINERS=$(docker ps -aq --filter label=cscm.managed=true)
AGENT_CONTAINERS=$(docker ps -aq --filter label=cscm.playit=true)
MC_COUNT=$(printf '%s' "$MC_CONTAINERS" | grep -c . || true)

say ""
say "This will remove:"
say "  - $MC_COUNT Minecraft server container(s) created by CSCM"
say "  - the CSCM dashboard containers, network and built images"
[ -n "$AGENT_CONTAINERS" ] && say "  - the Playit agent container"
say "  - $INSTALL_DIR (code and .env with saved credentials)"
[ -n "$SERVER_DIR$BACKUP_DIR$DB_DIR" ] && say "World data and backups are kept unless you choose to delete them next."
ask_yes "Continue" n
[ "$ANSWER" = yes ] || { say "Nothing was changed."; exit 0; }

DELETE_DATA=no
if [ -n "$SERVER_DIR$BACKUP_DIR$DB_DIR" ]; then
  say ""
  say "Data directories:"
  for d in "$SERVER_DIR" "$BACKUP_DIR" "$DB_DIR"; do [ -n "$d" ] && say "  $d"; done
  say "These hold your worlds, backups and the account database."
  ask "Type 'delete' to delete them permanently, or press Enter to keep them" ""
  [ "$ANSWER" = delete ] && DELETE_DATA=yes
fi

ask_yes "Also remove the downloaded Minecraft and Playit Docker images" n
REMOVE_IMAGES=$ANSWER

if [ -n "$MC_CONTAINERS" ]; then
  say "Removing Minecraft server containers…"
  # shellcheck disable=SC2086
  docker rm -f $MC_CONTAINERS >/dev/null
fi

if [ -n "$AGENT_CONTAINERS" ]; then
  say "Removing the Playit agent container…"
  # shellcheck disable=SC2086
  docker rm -f $AGENT_CONTAINERS >/dev/null
fi

say "Stopping CSCM…"
(cd "$INSTALL_DIR" && docker compose down --rmi local --volumes --remove-orphans) \
  || say "docker compose down failed; continuing with the files."

if [ "$REMOVE_IMAGES" = yes ]; then
  say "Removing Minecraft and Playit images…"
  for image in itzg/minecraft-server:java25 itzg/minecraft-bedrock-server ghcr.io/playit-cloud/playit-agent:latest; do
    docker image rm "$image" >/dev/null 2>&1 || true
  done
fi

if [ "$DELETE_DATA" = yes ]; then
  say "Deleting data directories…"
  for d in "$SERVER_DIR" "$BACKUP_DIR" "$DB_DIR"; do
    [ -n "$d" ] || continue
    safe_dir "$d" || { say "Skipping unsafe path '$d'."; continue; }
    remove_dir "$d"
    # the installer keeps all three in one parent folder; remove it once empty
    rmdir -- "$(dirname -- "$d")" 2>/dev/null || true
  done
fi

say "Deleting $INSTALL_DIR…"
remove_dir "$INSTALL_DIR"

say ""
say "CSCM is uninstalled."
if [ "$DELETE_DATA" = no ] && [ -n "$SERVER_DIR$BACKUP_DIR$DB_DIR" ]; then
  say "Your data is still in: $(dirname -- "${SERVER_DIR:-$DB_DIR}")"
fi
say "If you used a managed Playit agent, remove it at https://playit.gg/account/agents"
say "If you added a Cloudflare API token for CSCM, you can revoke it in the Cloudflare dashboard."
