import os
import requests
import dns.resolver
from dotenv import load_dotenv

load_dotenv()

_CF_BASE = "https://api.cloudflare.com/client/v4"


def _get_cf_env() -> tuple[str, str, str] | tuple[None, None, None]:
    """Return (api_token, zone_id, base_domain) from env, or (None, None, None)."""
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
    base_domain = os.getenv("CLOUDFLARE_BASE_DOMAIN")
    if not api_token or not zone_id or not base_domain:
        print("Cloudflare env vars missing: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, CLOUDFLARE_BASE_DOMAIN required")
        return None, None, None
    return api_token, zone_id, base_domain


def _headers(api_token: str) -> dict:
    return {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}


def lookup_minecraft_srv_port(playit_address: str) -> int | None:
    """Query the SRV record playit sets up for a tunnel address to find the external port."""
    try:
        answers = dns.resolver.resolve(f"_minecraft._tcp.{playit_address}", "SRV")
        for rdata in answers:
            return int(rdata.port)
    except Exception as e:
        print(f"SRV lookup failed for {playit_address}: {e}")
        return None


def create_dns_record(subdomain: str, target: str, proxied: bool = False) -> tuple[str, str] | None:
    """Create a CNAME record: <subdomain>.<base_domain> → target.

    Returns (full_name, cloudflare_record_id) on success, or None on failure.
    """
    api_token, zone_id, base_domain = _get_cf_env()
    if not api_token:
        return None

    full_name = f"{subdomain}.{base_domain}"
    payload = {
        "type": "CNAME",
        "name": full_name,
        "content": target,
        "ttl": 1,
        "proxied": proxied,
    }

    try:
        response = requests.post(
            f"{_CF_BASE}/zones/{zone_id}/dns_records",
            headers=_headers(api_token),
            json=payload,
        )
        data = response.json()
        if response.ok and data.get("success"):
            cf_id = data["result"]["id"]
            print(f"CNAME record created: {full_name} → {target} (id={cf_id})")
            return full_name, cf_id
        else:
            print(f"Failed to create CNAME record: {data.get('errors')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Cloudflare request error: {e}")
        return None


def create_srv_record(subdomain: str, target: str, port: int) -> str | None:
    """Create SRV record: _minecraft._tcp.<subdomain>.<base_domain> → target:port.

    Returns the Cloudflare record ID on success, or None on failure.
    """
    api_token, zone_id, base_domain = _get_cf_env()
    if not api_token:
        return None

    srv_name = f"_minecraft._tcp.{subdomain}.{base_domain}"
    payload = {
        "type": "SRV",
        "name": srv_name,
        "data": {"priority": 0, "weight": 5, "port": port, "target": target},
        "ttl": 1,
    }

    try:
        response = requests.post(
            f"{_CF_BASE}/zones/{zone_id}/dns_records",
            headers=_headers(api_token),
            json=payload,
        )
        data = response.json()
        if response.ok and data.get("success"):
            cf_id = data["result"]["id"]
            print(f"SRV record created: {srv_name} → {target}:{port} (id={cf_id})")
            return cf_id
        else:
            print(f"Failed to create SRV record: {data.get('errors')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Cloudflare SRV request error: {e}")
        return None


def delete_dns_record_by_id(cf_record_id: str) -> bool:
    """Delete a single Cloudflare DNS record by its CF record ID."""
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
    if not api_token or not zone_id:
        print("Cloudflare env vars missing for DNS record deletion")
        return False

    try:
        response = requests.delete(
            f"{_CF_BASE}/zones/{zone_id}/dns_records/{cf_record_id}",
            headers=_headers(api_token),
        )
        data = response.json()
        if response.ok and data.get("success"):
            print(f"DNS record deleted (id={cf_record_id})")
            return True
        else:
            print(f"Failed to delete DNS record {cf_record_id}: {data.get('errors')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Cloudflare request error: {e}")
        return False
