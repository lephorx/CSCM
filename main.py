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

def delete_crafty_server(crafty_server_id, headers):
    """Delete a Crafty server by its ID."""
    try:
        response = requests.delete(
            f"{base_url}/api/v2/servers/{crafty_server_id}",
            headers=headers,
            verify=False,
        )
        if response.ok:
            print(f"Crafty server {crafty_server_id} deleted")
        else:
            print(f"Failed to delete Crafty server: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Error deleting Crafty server: {e}")


def create_server(token, server_name="Example name", server_type="paper", version="1.18.2", server_port=25570):
    subdomain = server_name.lower().replace(" ", "-")
    headers = {"Authorization": f"Bearer {token}"}

    crafty_server_id = None
    db_server_id = None
    tunnel_info = None

    def rollback(reason):
        print(f"\nRolling back: {reason}")
        if tunnel_info:
            delete_tunnel(tunnel_info["tunnel_id"])
        if db_server_id:
            try:
                cursor.execute("DELETE FROM cloudflare_tunnels WHERE serverId = %s", (db_server_id,))
                cursor.execute("DELETE FROM servers WHERE id = %s", (db_server_id,))
                connection.commit()
                print("DB entries removed")
            except psycopg2.Error as db_err:
                print(f"DB rollback error: {db_err}")
                connection.rollback()
        if crafty_server_id:
            delete_crafty_server(crafty_server_id, headers)

    # Step 1: Create Crafty server
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
                "server_properties_port": server_port,
            },
        },
    }

    try:
        response = requests.post(f"{base_url}/api/v2/servers", json=data, headers=headers, verify=False)
        response.raise_for_status()
        crafty_server_id = response.json()["data"]["new_server_id"]
        print(f"Crafty server created: {crafty_server_id}")
    except requests.exceptions.RequestException as e:
        print(f"Error creating Crafty server: {e}")
        return

    # Step 2: Insert server into DB
    try:
        cursor.execute(
            "INSERT INTO servers (name, type, version, serverPort, createdAt) VALUES (%s, %s, %s, %s, %s)",
            (server_name, server_type, version, server_port, datetime.now()),
        )
        connection.commit()
        cursor.execute("SELECT id FROM servers WHERE name = %s", (server_name,))
        db_server_id = cursor.fetchone()[0]
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        connection.rollback()
        rollback("DB insert failed")
        return

    # Step 3: Create Cloudflare tunnel
    tunnel_info = create_tunnel(f"mc-{subdomain}", server_port, subdomain)
    if not tunnel_info:
        rollback("Cloudflare tunnel creation failed")
        return

    # Step 4: Insert tunnel into DB
    try:
        cursor.execute(
            "INSERT INTO cloudflare_tunnels (serverId, tunnelName, tunnelId, tunnelUrl, status) VALUES (%s, %s, %s, %s, %s)",
            (db_server_id, f"mc-{subdomain}", tunnel_info["tunnel_id"], tunnel_info["tunnel_url"], "active"),
        )
        connection.commit()
        print(f"Tunnel linked to server: {tunnel_info['tunnel_url']}")
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        connection.rollback()
        rollback("DB tunnel insert failed")
        return

    # Step 5: Start cloudflared
    print("\nStarting cloudflared tunnel...")
    tunnel_process = setup_and_run_tunnel(tunnel_info["tunnel_token"])
    if not tunnel_process:
        rollback("cloudflared failed to start or exited immediately")
        return

    print(f"✓ Tunnel is running!")
    print(f"✓ Connect to: {tunnel_info['tunnel_url']}")

if __name__ == "__main__":
    token = login()
    if token:
        create_server(token)