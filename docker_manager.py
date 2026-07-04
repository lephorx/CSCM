"""Native Minecraft server lifecycle management via the Docker Engine API.

Replaces the Crafty Controller integration entirely. Each Minecraft server
is one Docker container running the `itzg/minecraft-server` image, which
handles jar download/installation for every supported server type, EULA
acceptance, memory limits, and bundles `rcon-cli` for console commands.

Every container this module creates is labelled `cscm.managed=true` and
`cscm.server_id=<id>`; all lookups filter on these labels so the app never
touches a container it didn't create.
"""

import os
import shlex

import docker
from docker.errors import NotFound, APIError
from dotenv import load_dotenv

from logger import get_logger

load_dotenv()

log = get_logger("docker_manager")

MC_IMAGE = os.getenv("MC_IMAGE", "itzg/minecraft-server:java21")

# Path as seen by the Docker daemon (host path) — used only for bind mounts.
SERVERS_DIR_HOST = os.getenv("SERVERS_DIR_HOST", "/opt/cscm/servers")
# Path as seen inside the management container — used for all file I/O here.
SERVERS_DIR = os.getenv("SERVERS_DIR", "/data/servers")

CONTAINER_PREFIX = "cscm-mc-"
MANAGED_LABEL = "cscm.managed"
SERVER_ID_LABEL = "cscm.server_id"

# Public API type -> itzg/minecraft-server TYPE env value.
SERVER_TYPES = {
    "paper":   "PAPER",
    "forge":   "FORGE",
    "fabric":  "FABRIC",
    "vanilla": "VANILLA",
    "purpur":  "PURPUR",
}

_client: docker.DockerClient | None = None


def _get_client() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def container_name(server_id: int) -> str:
    return f"{CONTAINER_PREFIX}{server_id}"


def server_data_dir(server_id: int) -> str:
    """Path inside the management container for this server's data."""
    return f"{SERVERS_DIR}/{server_id}"


def _host_bind_path(server_id: int) -> str:
    """Path as seen by the Docker daemon for bind-mounting into the MC container."""
    return f"{SERVERS_DIR_HOST}/{server_id}"


def get_container(server_id: int):
    """Return the labelled container for a server, or None if it doesn't exist."""
    client = _get_client()
    try:
        container = client.containers.get(container_name(server_id))
    except NotFound:
        return None
    if container.labels.get(MANAGED_LABEL) != "true":
        log.warning("Container %s exists but is not cscm-managed; refusing to touch it", container.name)
        return None
    return container


def create_server_container(row) -> str:
    """Create and start a Minecraft server container for a DB server row.

    Args:
        row: sqlite3.Row (or dict) with keys id, type, version, serverport,
             mem_min_gb, mem_max_gb, rcon_password.

    Returns:
        The Docker container ID.
    """
    server_id = row["id"]
    itzg_type = SERVER_TYPES[row["type"]]

    # Remove any leftover container from a previous failed provision attempt.
    existing = get_container(server_id)
    if existing:
        log.warning("Removing leftover container for server_id=%d before create", server_id)
        try:
            existing.remove(force=True)
        except APIError as exc:
            log.warning("Could not remove leftover container: %s", exc)

    os.makedirs(server_data_dir(server_id), exist_ok=True)

    client = _get_client()
    container = client.containers.run(
        MC_IMAGE,
        name=container_name(server_id),
        detach=True,
        environment={
            "EULA": "TRUE",
            "TYPE": itzg_type,
            "VERSION": row["version"],
            "INIT_MEMORY": f"{row['mem_min_gb']}G",
            "MAX_MEMORY": f"{row['mem_max_gb']}G",
            "ENABLE_RCON": "true",
            "RCON_PASSWORD": row["rcon_password"],
        },
        ports={"25565/tcp": row["serverport"]},
        volumes={_host_bind_path(server_id): {"bind": "/data", "mode": "rw"}},
        restart_policy={"Name": "unless-stopped"},
        labels={MANAGED_LABEL: "true", SERVER_ID_LABEL: str(server_id)},
    )
    log.info("Container created: server_id=%d, container_id=%s", server_id, container.id)
    return container.id


def recreate_server(row) -> str:
    """Stop and remove the container, then recreate it with the current DB config.

    The bind-mounted data directory is untouched, so world data survives.
    """
    server_id = row["id"]
    container = get_container(server_id)
    if container:
        try:
            container.stop(timeout=30)
        except APIError as exc:
            log.warning("Error stopping container before recreate: %s", exc)
        container.remove(force=True)
    return create_server_container(row)


def remove_server(server_id: int) -> None:
    """Stop and remove a server's container (data directory is left intact)."""
    container = get_container(server_id)
    if not container:
        return
    try:
        container.stop(timeout=30)
    except APIError as exc:
        log.warning("Error stopping container for server_id=%d: %s", server_id, exc)
    container.remove(force=True)
    log.info("Container removed: server_id=%d", server_id)


def start_server(server_id: int) -> tuple[bool, str]:
    container = get_container(server_id)
    if not container:
        return False, "Container not found"
    container.start()
    return True, "Start command sent"


def stop_server(server_id: int) -> tuple[bool, str]:
    container = get_container(server_id)
    if not container:
        return False, "Container not found"
    try:
        send_rcon(server_id, "stop")
    except APIError:
        pass
    container.stop(timeout=60)
    return True, "Stop command sent"


def restart_server(server_id: int) -> tuple[bool, str]:
    container = get_container(server_id)
    if not container:
        return False, "Container not found"
    container.restart(timeout=60)
    return True, "Restart command sent"


def kill_server(server_id: int) -> tuple[bool, str]:
    container = get_container(server_id)
    if not container:
        return False, "Container not found"
    container.kill()
    return True, "Kill command sent"


def send_rcon(server_id: int, command: str) -> str:
    """Run a command via rcon-cli inside the server's container and return its output."""
    container = get_container(server_id)
    if not container:
        raise NotFound(f"No container for server_id={server_id}")
    exit_code, output = container.exec_run(["rcon-cli", *shlex.split(command)])
    text = output.decode("utf-8", errors="replace").strip()
    if exit_code != 0:
        log.warning("rcon-cli exited %d for server_id=%d: %s", exit_code, server_id, text)
    return text


def get_logs(server_id: int, tail: int = 200) -> list[str]:
    container = get_container(server_id)
    if not container:
        return []
    raw = container.logs(tail=tail, timestamps=False)
    return raw.decode("utf-8", errors="replace").splitlines()


def stream_logs(server_id: int):
    """Generator yielding new log lines as they are produced. For SSE streaming."""
    container = get_container(server_id)
    if not container:
        return
    for chunk in container.logs(stream=True, follow=True, tail=50):
        yield chunk.decode("utf-8", errors="replace")


def get_stats(server_id: int) -> dict:
    """One-shot container resource stats plus online player count via rcon."""
    container = get_container(server_id)
    if not container:
        return {"running": False}

    container.reload()
    state = container.attrs.get("State", {})
    running = bool(state.get("Running"))

    result = {
        "running": running,
        "status": state.get("Status"),
        "health": (state.get("Health") or {}).get("Status"),
    }

    if running:
        raw_stats = container.stats(stream=False)
        cpu = raw_stats.get("cpu_stats", {})
        precpu = raw_stats.get("precpu_stats", {})
        cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - precpu.get("cpu_usage", {}).get("total_usage", 0)
        system_delta = cpu.get("system_cpu_usage", 0) - precpu.get("system_cpu_usage", 0)
        online_cpus = cpu.get("online_cpus") or len(cpu.get("cpu_usage", {}).get("percpu_usage") or [1])
        cpu_percent = (cpu_delta / system_delta * online_cpus * 100) if system_delta > 0 else 0.0

        mem = raw_stats.get("memory_stats", {})
        result["cpu_percent"] = round(cpu_percent, 2)
        result["memory_usage_bytes"] = mem.get("usage")
        result["memory_limit_bytes"] = mem.get("limit")

        try:
            players_output = send_rcon(server_id, "list")
            result["players_raw"] = players_output
        except (NotFound, APIError):
            pass

    return result


def runtime_status(server_id: int) -> str:
    """Return a simple status string: not_created | starting | healthy | unhealthy | stopped."""
    container = get_container(server_id)
    if not container:
        return "not_created"
    container.reload()
    state = container.attrs.get("State", {})
    if not state.get("Running"):
        return "stopped"
    health = (state.get("Health") or {}).get("Status")
    if health == "healthy":
        return "healthy"
    if health in ("starting", "unhealthy"):
        return health
    return "running"
