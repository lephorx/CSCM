from dotenv import load_dotenv
import requests
import os
import subprocess
import time

load_dotenv()

CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
DOMAIN = os.getenv("CLOUDFLARE_DOMAIN", "homeops.services")


def create_tunnel(tunnel_name, server_port, subdomain):
    """Create a Cloudflare tunnel, configure ingress via API, and set up DNS — fully automated."""
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        # 1. Create the tunnel
        tunnel_response = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/cfd_tunnel",
            headers=headers,
            json={"name": tunnel_name, "config_src": "cloudflare"},
        )
        tunnel_response.raise_for_status()
        tunnel_id = tunnel_response.json()["result"]["id"]
        print(f"Tunnel created: {tunnel_id}")

        # 2. Configure ingress rules via the API (no local config file required)
        config_response = requests.put(
            f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/cfd_tunnel/{tunnel_id}/configurations",
            headers=headers,
            json={
                "config": {
                    "ingress": [
                        {
                            "hostname": f"{subdomain}.{DOMAIN}",
                            "service": f"tcp://localhost:{server_port}",
                        },
                        {"service": "http_status:404"},
                    ]
                }
            },
        )
        config_response.raise_for_status()
        print(f"Ingress configured: {subdomain}.{DOMAIN} -> tcp://localhost:{server_port}")

        # 3. Fetch the tunnel token so cloudflared can run without a credentials file
        token_response = requests.get(
            f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/cfd_tunnel/{tunnel_id}/token",
            headers=headers,
        )
        token_response.raise_for_status()
        tunnel_token = token_response.json()["result"]
        print("Tunnel token retrieved")

        # 4. Create the DNS CNAME record
        dns_response = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=headers,
            json={
                "type": "CNAME",
                "name": subdomain,
                "content": f"{tunnel_id}.cfargotunnel.com",
                "ttl": 1,
                "proxied": False,
            },
        )
        dns_response.raise_for_status()
        print(f"DNS record created: {subdomain}.{DOMAIN}")

        return {
            "tunnel_id": tunnel_id,
            "tunnel_token": tunnel_token,
            "tunnel_url": f"{subdomain}.{DOMAIN}",
        }

    except requests.exceptions.RequestException as e:
        print(f"Error creating tunnel: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.text}")
        return None


def delete_tunnel(tunnel_id):
    """Delete all DNS records pointing to the tunnel, then delete the tunnel itself."""
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        # Remove DNS records first to avoid orphaned entries
        dns_list = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=headers,
            params={"content": f"{tunnel_id}.cfargotunnel.com"},
        )
        dns_list.raise_for_status()
        for record in dns_list.json().get("result", []):
            requests.delete(
                f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{record['id']}",
                headers=headers,
            )
            print(f"DNS record deleted: {record['name']}")

        # Delete the tunnel
        response = requests.delete(
            f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/cfd_tunnel/{tunnel_id}",
            headers=headers,
        )
        response.raise_for_status()
        print(f"Tunnel {tunnel_id} deleted")
        return True

    except requests.exceptions.RequestException as e:
        print(f"Error deleting tunnel: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.text}")
        return False


def setup_and_run_tunnel(tunnel_token):
    """Start cloudflared using the tunnel token — no credentials file or config file needed."""
    log_dir = os.path.expanduser("~/.cloudflared/logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "cloudflared.log")

    try:
        log_file = open(log_path, "a")
        process = subprocess.Popen(
            ["cloudflared", "tunnel", "run", "--token", tunnel_token],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        # Wait briefly to detect immediate startup failures (bad token, network issue, etc.)
        time.sleep(3)
        if process.poll() is not None:
            print(f"cloudflared exited immediately (exit code {process.returncode}).")
            print(f"Check logs: {log_path}")
            return None
        print(f"Tunnel started with PID: {process.pid} (logs: {log_path})")
        return process
    except FileNotFoundError:
        print("cloudflared is not installed.")
        print("Download it from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        return None