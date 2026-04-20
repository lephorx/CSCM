import asyncio
import os
import requests
import urllib3
from dotenv import load_dotenv
import psycopg2
from datetime import datetime

from playit_manager import create_tunnel
from cloudflare_manager import create_dns_record, create_srv_record, lookup_minecraft_srv_port

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
    try:
        response = requests.post(
            f"{base_url}/api/v2/auth/login",
            json={"username": username, "password": password},
            verify=False
        )
    except requests.exceptions.ConnectionError:
        print(f"Login failed: could not connect to Crafty at {base_url}. Is it running?")
        return None

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


def create_server(token, server_name="Minecraft test server", server_type="paper", version="1.18.2", server_port=25580):
    subdomain = server_name.lower().replace(" ", "-")
    headers = {"Authorization": f"Bearer {token}"}

    crafty_server_id = None
    db_server_id = None
    tunnel_info = None

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
        print("Server inserted into database with ID:", db_server_id)
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        connection.rollback()
        return

    # Step 3: Create PlayIT tunnel for the server port
    print(f"Creating PlayIT tunnel '{subdomain}' on port {server_port}...")
    tunnel_address = asyncio.run(create_tunnel(tunnel_name=subdomain, tunnel_port=server_port))

    if not tunnel_address:
        print("⚠️  PlayIT tunnel creation failed — skipping DNS record creation.")
        return

    # Step 4: Create Cloudflare DNS records pointing subdomain → tunnel address
    print(f"Creating Cloudflare DNS record for '{subdomain}' → '{tunnel_address}'...")
    dns_name = create_dns_record(subdomain=subdomain, target=tunnel_address)

    if not dns_name:
        print("⚠️  DNS record creation failed. Tunnel address:", tunnel_address)
        return

    # Step 5: Look up the external port playit assigned and create an SRV record
    print(f"Looking up external port for '{tunnel_address}'...")
    external_port = lookup_minecraft_srv_port(tunnel_address)

    if external_port:
        print(f"External port: {external_port} — creating SRV record...")
        create_srv_record(subdomain=subdomain, target=tunnel_address, port=external_port)
    else:
        print("⚠️  Could not determine external port — SRV record not created. Players must connect via direct tunnel address.")

    print(f"✅ Server fully provisioned. Players can connect at: {dns_name}")

if __name__ == "__main__":
    token = login()
    if token:
        create_server(token) 