from dotenv import load_dotenv
import requests
import os

load_dotenv()

CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")

def create_tunnel(tunnel_name, server_port, subdomain):
    """Create a Cloudflare tunnel with a subdomain"""
    try:
        # Create tunnel
        tunnel_response = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/cfd_tunnel",
            headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
            json={"name": tunnel_name, "config_src": "cloudflare"}
        )
        tunnel_response.raise_for_status()
        tunnel_id = tunnel_response.json()['result']['id']
        
        print(f"Tunnel created: {tunnel_id}")
        
        # Create DNS CNAME record
        dns_response = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
            json={
                "type": "CNAME",
                "name": subdomain,
                "content": f"{tunnel_id}.cfargotunnel.com",
                "ttl": 1,
                "proxied": True
            }
        )
        dns_response.raise_for_status()
        
        print(f"DNS record created: {subdomain}")
        
        return {
            "tunnel_id": tunnel_id,
            "tunnel_url": f"{subdomain}.homeops.services"
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Error creating tunnel: {e}")
        return None

def delete_tunnel(tunnel_id):
    """Delete a Cloudflare tunnel"""
    try:
        response = requests.delete(
            f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/cfd_tunnel/{tunnel_id}",
            headers={"Authorization": f"Bearer {CF_API_TOKEN}"}
        )
        response.raise_for_status()
        print(f"Tunnel {tunnel_id} deleted")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error deleting tunnel: {e}")
        return False