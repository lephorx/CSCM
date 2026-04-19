from dotenv import load_dotenv
import requests
import os
import subprocess
import json

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
        dns_payload = {
            "type": "CNAME",
            "name": subdomain,
            "content": f"{tunnel_id}.cfargotunnel.com",
            "ttl": 1,
            "proxied": True
        }
        
        dns_response = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
            json=dns_payload
        )
        dns_response.raise_for_status()
        
        print(f"DNS record created: {subdomain}")
        
        return {
            "tunnel_id": tunnel_id,
            "tunnel_url": f"{subdomain}.homeops.services"
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Error creating tunnel: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
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

def setup_and_run_tunnel(tunnel_id, server_port, subdomain, domain="homeops.services"):
    """Setup cloudflared config and run the tunnel"""
    
    cloudflared_dir = os.path.expanduser("~/.cloudflared")
    os.makedirs(cloudflared_dir, exist_ok=True)
    
    creds_file = os.path.join(cloudflared_dir, f"{tunnel_id}.json")
    config_file = os.path.join(cloudflared_dir, "config.yml")
    
    # Create config.yml
    config_content = f"""tunnel: {tunnel_id}
credentials-file: {creds_file}

ingress:
  - hostname: {subdomain}.{domain}
    service: tcp://localhost:{server_port}
  - service: http_status:404
"""
    
    with open(config_file, 'w') as f:
        f.write(config_content)
    
    print(f"Config created: {config_file}")
    
    # Start cloudflared in background
    try:
        process = subprocess.Popen(
            ["cloudflared", "tunnel", "run", tunnel_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )
        print(f"Tunnel started with PID: {process.pid}")
        return process
    except FileNotFoundError:
        print("cloudflared not installed. Install with:")
        print("wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64")
        print("chmod +x cloudflared-linux-amd64")
        print("sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared")
        print("\nThen run: cloudflared tunnel login")
        return None