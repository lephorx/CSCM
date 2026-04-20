import os
import requests
import dns.resolver
from dotenv import load_dotenv

load_dotenv()

CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
CLOUDFLARE_BASE_DOMAIN = os.getenv("CLOUDFLARE_BASE_DOMAIN")  # e.g. "example.com"

_CF_BASE = "https://api.cloudflare.com/client/v4"


def lookup_minecraft_srv_port(playit_address: str) -> int | None:
    """Query the SRV record playit sets up for a tunnel address to find the external port."""
    try:
        answers = dns.resolver.resolve(f"_minecraft._tcp.{playit_address}", "SRV")
        for rdata in answers:
            return int(rdata.port)
    except Exception as e:
        print(f"SRV lookup failed for {playit_address}: {e}")
        return None


def create_dns_record(subdomain: str, target: str, proxied: bool = False) -> str | None:
    """Create a CNAME DNS record pointing subdomain.<base_domain> → target."""
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
    base_domain = os.getenv("CLOUDFLARE_BASE_DOMAIN")

    if not api_token or not zone_id or not base_domain:
        print("Cloudflare env vars missing: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, CLOUDFLARE_BASE_DOMAIN required")
        return None

    full_name = f"{subdomain}.{base_domain}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "type": "CNAME",
        "name": full_name,
        "content": target,
        "ttl": 1,  # 1 = automatic
        "proxied": proxied,
    }

    try:
        response = requests.post(
            f"{_CF_BASE}/zones/{zone_id}/dns_records",
            headers=headers,
            json=payload,
        )
        data = response.json()
        if response.ok and data.get("success"):
            print(f"CNAME record created: {full_name} → {target}")
            return full_name
        else:
            errors = data.get("errors", [])
            print(f"Failed to create CNAME record: {errors}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Cloudflare request error: {e}")
        return None


def create_srv_record(subdomain: str, target: str, port: int) -> bool:
    """Create an SRV record so Minecraft clients find the correct port.

    Creates: _minecraft._tcp.<subdomain>.<base_domain> → 0 5 <port> <target>
    """
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
    base_domain = os.getenv("CLOUDFLARE_BASE_DOMAIN")

    if not api_token or not zone_id or not base_domain:
        print("Cloudflare env vars missing for SRV record creation")
        return False

    srv_name = f"_minecraft._tcp.{subdomain}.{base_domain}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "type": "SRV",
        "name": srv_name,
        "data": {
            "priority": 0,
            "weight": 5,
            "port": port,
            "target": target,
        },
        "ttl": 1,
    }

    try:
        response = requests.post(
            f"{_CF_BASE}/zones/{zone_id}/dns_records",
            headers=headers,
            json=payload,
        )
        data = response.json()
        if response.ok and data.get("success"):
            print(f"SRV record created: {srv_name} → {target}:{port}")
            return True
        else:
            errors = data.get("errors", [])
            print(f"Failed to create SRV record: {errors}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Cloudflare SRV request error: {e}")
        return False

    """Create a CNAME DNS record in Cloudflare.

    Args:
        subdomain: The subdomain portion of the record (e.g. ``my-server``).
                   The full record name will be ``<subdomain>.<CLOUDFLARE_BASE_DOMAIN>``.
        target:    The value the CNAME points to (e.g. the playit.gg tunnel address).
        proxied:   Whether the record should be proxied through Cloudflare.

    Returns:
        The full DNS name that was created (e.g. ``my-server.example.com``),
        or ``None`` on failure.
    """
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
    base_domain = os.getenv("CLOUDFLARE_BASE_DOMAIN")

    if not api_token or not zone_id or not base_domain:
        print("Cloudflare env vars missing: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, CLOUDFLARE_BASE_DOMAIN required")
        return None

    full_name = f"{subdomain}.{base_domain}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "type": "CNAME",
        "name": full_name,
        "content": target,
        "ttl": 1,  # 1 = automatic
        "proxied": proxied,
    }

    try:
        response = requests.post(
            f"{_CF_BASE}/zones/{zone_id}/dns_records",
            headers=headers,
            json=payload,
        )
        data = response.json()
        if response.ok and data.get("success"):
            print(f"DNS record created: {full_name} → {target}")
            return full_name
        else:
            errors = data.get("errors", [])
            print(f"Failed to create DNS record: {errors}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Cloudflare request error: {e}")
        return None
