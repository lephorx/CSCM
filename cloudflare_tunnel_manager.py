from dotenv import load_dotenv
import requests
import os
import subprocess
import time

load_dotenv()

# Cloudflare (used only for the NS delegation record)
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
DOMAIN = os.getenv("CLOUDFLARE_DOMAIN", "homeops.services")

# playit.gg
PLAYIT_SECRET_KEY = os.getenv("PLAYIT_SECRET_KEY")
PLAYIT_API = "https://api.playit.gg"


def _playit_headers():
    return {
        "Authorization": f"agent-key {PLAYIT_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def _cf_headers():
    return {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }


def _playit_result(response):
    """Parse a playit API response and return the data payload, or raise on failure."""
    response.raise_for_status()
    body = response.json()
    status = body.get("status")
    if status == "success":
        return body.get("data")
    raise ValueError(f"playit API error (status={status}): {body.get('data', body)}")


def create_tunnel(tunnel_name, server_port, subdomain):
    """
    1. Create a playit.gg Minecraft Java tunnel via the REST API.
    2. Wait for the tunnel to receive a public allocation.
    3. Map the tunnel to the local Minecraft port.
    4. Add a Cloudflare NS record delegating the subdomain to playit's DNS
       (ns1.playit-dns.com serves SRV records so players can connect directly).
    """
    try:
        # 0. Get agent ID (required by the origin field)
        rundata_res = requests.post(
            f"{PLAYIT_API}/agents/rundata",
            headers=_playit_headers(),
            json={},
        )
        agent_id = _playit_result(rundata_res)["agent_id"]
        print(f"Agent ID: {agent_id}")

        # 1. Create the tunnel with local port mapping in one call
        create_res = requests.post(
            f"{PLAYIT_API}/tunnels/create",
            headers=_playit_headers(),
            json={
                "name": tunnel_name,
                "tunnel_type": "minecraft-java",
                "port_type": "tcp",
                "port_count": 1,
                "origin": {
                    "type": "agent",
                    "data": {
                        "agent_id": agent_id,
                        "local_ip": "127.0.0.1",
                        "local_port": server_port,
                    },
                },
                "enabled": True,
            },
        )
        tunnel_id = str(_playit_result(create_res)["id"])
        print(f"Tunnel created: {tunnel_id}")

        # 2. Wait for the tunnel to receive a public allocation (up to 60 seconds)
        public_domain = None
        for attempt in range(20):
            time.sleep(3)
            list_res = requests.post(
                f"{PLAYIT_API}/tunnels/list",
                headers=_playit_headers(),
                json={"tunnel_id": tunnel_id, "agent_id": None},
            )
            tunnels = _playit_result(list_res).get("tunnels", [])
            if tunnels:
                alloc = tunnels[0].get("alloc", {})
                if alloc.get("status") == "allocated":
                    public_domain = alloc.get("data", {}).get("assigned_domain")
                    if public_domain:
                        print(f"Tunnel allocated at: {public_domain}")
                        break
            print(f"Waiting for allocation... ({attempt + 1}/20)")

        if not public_domain:
            print("Tunnel allocation timed out after 60 seconds.")
            return None

        # 3. Add Cloudflare NS record: subdomain.DOMAIN -> ns1.playit-dns.com
        #    This delegates DNS for the subdomain to playit, which serves the
        #    SRV records Minecraft clients need to connect.
        ns_res = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=_cf_headers(),
            json={
                "type": "NS",
                "name": subdomain,
                "content": "ns1.playit-dns.com",
                "ttl": 3600,
            },
        )
        ns_res.raise_for_status()
        print(f"NS record created: {subdomain}.{DOMAIN} -> ns1.playit-dns.com")

        return {
            "tunnel_id": tunnel_id,
            "tunnel_url": f"{subdomain}.{DOMAIN}",
        }

    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"Error creating tunnel: {e}")
        if isinstance(e, requests.exceptions.RequestException) and hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.text}")
        return None


def delete_tunnel(tunnel_id, subdomain=None):
    """Delete the playit.gg tunnel and the Cloudflare NS delegation record."""
    success = True

    # 1. Delete the playit tunnel
    try:
        res = requests.post(
            f"{PLAYIT_API}/tunnels/delete",
            headers=_playit_headers(),
            json={"tunnel_id": tunnel_id},
        )
        res.raise_for_status()
        print(f"Tunnel {tunnel_id} deleted")
    except requests.exceptions.RequestException as e:
        print(f"Error deleting playit tunnel: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.text}")
        success = False

    # 2. Delete the Cloudflare NS record for the subdomain
    if subdomain:
        try:
            cf_auth = {"Authorization": f"Bearer {CF_API_TOKEN}"}
            dns_list = requests.get(
                f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
                headers=cf_auth,
                params={"type": "NS", "name": f"{subdomain}.{DOMAIN}"},
            )
            dns_list.raise_for_status()
            for record in dns_list.json().get("result", []):
                requests.delete(
                    f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{record['id']}",
                    headers=cf_auth,
                )
                print(f"NS record deleted: {record['name']}")
        except requests.exceptions.RequestException as e:
            print(f"Error deleting Cloudflare NS record: {e}")
            success = False

    return success


def setup_and_run_tunnel():
    """Start the playit agent — it connects all configured tunnels automatically."""
    log_dir = os.path.expanduser("~/.playit/logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "playit.log")

    try:
        log_file = open(log_path, "a")
        process = subprocess.Popen(
            ["playit", "--secret", PLAYIT_SECRET_KEY, "start"],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        # Wait briefly to catch immediate failures (bad key, binary not found, etc.)
        time.sleep(3)
        if process.poll() is not None:
            print(f"playit exited immediately (exit code {process.returncode}).")
            print(f"Check logs: {log_path}")
            return None
        print(f"playit agent started (PID: {process.pid}, logs: {log_path})")
        return process
    except FileNotFoundError:
        print("playit is not installed.")
        print("Download from: https://playit.gg/download")
        return None