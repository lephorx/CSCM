import os
import requests
import urllib3
from dotenv import load_dotenv
import psycopg2
from datetime import datetime
from cloudflare_tunnel_manager import create_tunnel, delete_tunnel, setup_and_run_tunnel

load_dotenv()

try:
    connection = psycopg2.connect(
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        sslmode="require",
    )
    cursor = connection.cursor()
except psycopg2.OperationalError as e:
    print(f"Database connection failed: {e}")
    raise SystemExit(1)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

base_url = os.getenv("BASE_URL", "https://localhost:8443")
username = os.getenv("USERNAME", "admin")
password = os.getenv("PASSWORD", "admin")

def login():
    response = requests.post(
        f"{base_url}/api/v2/auth/login",
        json={"username": username, "password": password},
        verify=False
    )
    
    print(f"Login status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code == 200:
        token = response.json()["data"]["token"]
        return token
    else:
        print("Login failed!")
        return None

def create_server(token, server_name="Example name", server_type="paper", version="1.18.2", server_port=25570):
    subdomain = server_name.lower().replace(" ", "-")
    
    data = {
        "name": server_name,
        "monitoring_type": "minecraft_java",
        "minecraft_java_monitoring_data": {
            "host": "127.0.0.1",
            "port": server_port,
        },
        "create_type": "minecraft_java",
        "minecraft_java_create_data": {
            "create_type": "download_jar",
            "download_jar_create_data": {
                "category": "mc_java_servers",
                "type": server_type,
                "version": version,
                "mem_min": 2,
                "mem_max": 4,
                "server_properties_port": server_port
            }
        }
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.post(f"{base_url}/api/v2/servers", json=data, headers=headers, verify=False)
        response.raise_for_status()
        
        print(f"Server created: {response.json()}")
        
        cursor.execute(
            "INSERT INTO servers (name, type, version, serverPort, createdAt) VALUES (%s, %s, %s, %s, %s)",
            (server_name, server_type, version, server_port, datetime.now())
        )
        connection.commit()
        
        cursor.execute("SELECT id FROM servers WHERE name = %s", (server_name,))
        server_id = cursor.fetchone()[0]
        
        tunnel_info = create_tunnel(f"mc-{subdomain}", server_port, subdomain)
        
        if tunnel_info:
            cursor.execute(
                "INSERT INTO cloudflare_tunnels (serverId, tunnelName, tunnelId, tunnelUrl, status) VALUES (%s, %s, %s, %s, %s)",
                (server_id, f"mc-{subdomain}", tunnel_info['tunnel_id'], tunnel_info['tunnel_url'], 'active')
            )
            connection.commit()
            print(f"Tunnel created and linked to server: {tunnel_info['tunnel_url']}")
            
            print(f"\nStarting cloudflared tunnel...")
            tunnel_process = setup_and_run_tunnel(tunnel_info["tunnel_token"])
            
            if tunnel_process:
                print(f"✓ Tunnel is running!")
                print(f"✓ Connect to: {tunnel_info['tunnel_url']}")
            
    except requests.exceptions.RequestException as e:
        print(f"Error creating server via API: {e}")
        return
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        connection.rollback()
        return

if __name__ == "__main__":
    token = login()
    if token:
        create_server(token)