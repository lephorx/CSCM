import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
CLOUDFLARE_BASE_DOMAIN = os.getenv("CLOUDFLARE_BASE_DOMAIN")  # e.g. "example.com"

_CF_BASE = "https://api.cloudflare.com/client/v4"


def create_dns_record(subdomain: str, target: str, proxied: bool = False) -> str | None:
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
    if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_ZONE_ID or not CLOUDFLARE_BASE_DOMAIN:
        print("Cloudflare env vars missing: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, CLOUDFLARE_BASE_DOMAIN required")
        return None

    full_name = f"{subdomain}.{CLOUDFLARE_BASE_DOMAIN}"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
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
            f"{_CF_BASE}/zones/{CLOUDFLARE_ZONE_ID}/dns_records",
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
