"""
Cloudflare DNS management module.

Provides helpers to create and delete DNS records (CNAME and SRV) via the
Cloudflare REST API v4.  All credentials are read from environment variables
at call time so that dotenv loading order does not matter.

Required environment variables:
    CLOUDFLARE_API_TOKEN   — Cloudflare API token with DNS edit permissions
    CLOUDFLARE_ZONE_ID     — Zone ID of the target domain
    CLOUDFLARE_BASE_DOMAIN — Root domain under which records are created
                             (e.g. "example.com")
"""

import os
import requests
from dotenv import load_dotenv

from logger import get_logger

load_dotenv()

log = get_logger("cloudflare")

_CF_BASE = "https://api.cloudflare.com/client/v4"


def _get_cf_env() -> tuple[str, str, str] | tuple[None, None, None]:
    """Read and validate required Cloudflare environment variables.

    Returns:
        (api_token, zone_id, base_domain) on success, or (None, None, None)
        when any variable is missing.
    """
    api_token   = os.getenv("CLOUDFLARE_API_TOKEN")
    zone_id     = os.getenv("CLOUDFLARE_ZONE_ID")
    base_domain = os.getenv("CLOUDFLARE_BASE_DOMAIN")
    if not api_token or not zone_id or not base_domain:
        log.error(
            "Missing Cloudflare environment variables: "
            "CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, CLOUDFLARE_BASE_DOMAIN"
        )
        return None, None, None
    return api_token, zone_id, base_domain


def _headers(api_token: str) -> dict:
    return {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}


def cloudflare_enabled() -> bool:
    """Use Cloudflare when credentials exist, unless explicitly disabled."""
    mode = os.getenv("CLOUDFLARE_ENABLED", "auto").strip().lower()
    if mode in {"false", "0", "no", "off"}:
        return False
    credentials = (
        os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
        os.getenv("CLOUDFLARE_ZONE_ID", "").strip(),
        os.getenv("CLOUDFLARE_BASE_DOMAIN", "").strip(),
    )
    ready = all(value and not value.startswith("<") for value in credentials)
    if not ready and (mode in {"true", "1", "yes", "on"} or any(value and not value.startswith("<") for value in credentials)):
        log.warning("Cloudflare credentials are incomplete; using the PlayIT address")
    return ready


def create_dns_record(subdomain: str, target: str, proxied: bool = False) -> tuple[str, str] | None:
    """Create a CNAME record pointing to a tunnel address.

    The full record name is ``<subdomain>.<CLOUDFLARE_BASE_DOMAIN>``.

    Args:
        subdomain: Subdomain label (e.g. ``my-server``).
        target:    CNAME target (e.g. ``abc.deu.mcjoin.link``).
        proxied:   Whether to proxy the record through Cloudflare.

    Returns:
        ``(full_name, cloudflare_record_id)`` on success, or ``None`` on failure.
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
            timeout=15,
        )
        data = response.json()
        if response.ok and data.get("success"):
            cf_id = data["result"]["id"]
            log.info("CNAME record created: %s -> %s (cf_id=%s)", full_name, target, cf_id)
            return full_name, cf_id
        log.error("Failed to create CNAME record for %s: %s", full_name, data.get("errors"))
        return None
    except (requests.exceptions.RequestException, ValueError, KeyError) as exc:
        log.error("Cloudflare API request failed (CNAME): %s", exc)
        return None


def create_srv_record(subdomain: str, target: str, port: int) -> str | None:
    """Create an SRV record so Minecraft clients discover the correct port.

    The record is created as:
        ``_minecraft._tcp.<subdomain>.<base_domain>  SRV  0 5 <port> <target>``

    Args:
        subdomain: Subdomain label (e.g. ``my-server``).
        target:    Hostname the SRV record points to.
        port:      External TCP port assigned by playit.gg.

    Returns:
        The Cloudflare record ID on success, or ``None`` on failure.
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
            timeout=15,
        )
        data = response.json()
        if response.ok and data.get("success"):
            cf_id = data["result"]["id"]
            log.info("SRV record created: %s -> %s:%d (cf_id=%s)", srv_name, target, port, cf_id)
            return cf_id
        log.error("Failed to create SRV record for %s: %s", srv_name, data.get("errors"))
        return None
    except (requests.exceptions.RequestException, ValueError, KeyError) as exc:
        log.error("Cloudflare API request failed (SRV): %s", exc)
        return None


def delete_dns_record_by_id(cf_record_id: str) -> bool:
    """Delete a single DNS record by its Cloudflare record ID.

    Args:
        cf_record_id: The opaque record identifier returned by the Cloudflare API.

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    zone_id   = os.getenv("CLOUDFLARE_ZONE_ID")
    if not api_token or not zone_id:
        log.error("Missing CLOUDFLARE_API_TOKEN or CLOUDFLARE_ZONE_ID for record deletion")
        return False

    try:
        response = requests.delete(
            f"{_CF_BASE}/zones/{zone_id}/dns_records/{cf_record_id}",
            headers=_headers(api_token),
            timeout=15,
        )
        data = response.json()
        if response.ok and data.get("success"):
            log.info("DNS record deleted: cf_id=%s", cf_record_id)
            return True
        log.error("Failed to delete DNS record %s: %s", cf_record_id, data.get("errors"))
        return False
    except (requests.exceptions.RequestException, ValueError, KeyError) as exc:
        log.error("Cloudflare API request failed (DELETE): %s", exc)
        return False
