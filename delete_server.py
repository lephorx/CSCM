#!/usr/bin/env python3
"""
Server deletion script.
Deletes a server by its database ID:
  1. Looks up the server + linked records in Neon (PostgreSQL)
  2. Deletes the Crafty server
  3. Deletes all Cloudflare DNS records by stored CF record IDs
  4. Deletes the database entry (cascades to playit_tunnels + dns_records)
"""

import os
import sys
import requests
import urllib3
import psycopg2
from dotenv import load_dotenv

from cloudflare_manager import delete_dns_record_by_id

load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- DB connection ---
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
    sys.exit(1)

# --- Crafty connection ---
base_url = os.getenv("BASE_URL", "https://localhost:8443")
crafty_username = os.getenv("USERNAME", "admin")
crafty_password = os.getenv("PASSWORD", "admin")


def crafty_login() -> str | None:
    try:
        response = requests.post(
            f"{base_url}/api/v2/auth/login",
            json={"username": crafty_username, "password": crafty_password},
            verify=False,
        )
        if response.status_code == 200:
            return response.json()["data"]["token"]
        print(f"Crafty login failed: {response.text}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to Crafty at {base_url}. Is it running?")
        return None


def delete_crafty_server(crafty_server_id: str, headers: dict) -> bool:
    try:
        response = requests.delete(
            f"{base_url}/api/v2/servers/{crafty_server_id}",
            headers=headers,
            verify=False,
        )
        if response.ok:
            print(f"Crafty server {crafty_server_id} deleted")
            return True
        else:
            print(f"Failed to delete Crafty server: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error deleting Crafty server: {e}")
        return False


def delete_server(db_server_id: int) -> None:
    # Step 1: Look up server in DB
    cursor.execute(
        'SELECT id, name, "craftyId" FROM servers WHERE id = %s',
        (db_server_id,),
    )
    row = cursor.fetchone()
    if not row:
        print(f"No server found with database ID {db_server_id}")
        return

    db_id, server_name, crafty_server_id = row
    subdomain = server_name.lower().replace(" ", "-")

    # Fetch linked DNS records
    cursor.execute(
        "SELECT record_type, name, target, port, cloudflare_record_id FROM dns_records WHERE server_id = %s",
        (db_server_id,),
    )
    dns_rows = cursor.fetchall()

    # Fetch linked PlayIT tunnels
    cursor.execute(
        "SELECT tunnel_name, tunnel_address, local_port, external_port FROM playit_tunnels WHERE server_id = %s",
        (db_server_id,),
    )
    tunnel_rows = cursor.fetchall()

    print(f"\nServer found:")
    print(f"  DB ID:      {db_id}")
    print(f"  Name:       {server_name}")
    print(f"  Subdomain:  {subdomain}")
    print(f"  Crafty ID:  {crafty_server_id or '(none)'}")
    if tunnel_rows:
        for t in tunnel_rows:
            print(f"  Tunnel:     {t[1]} (local:{t[2]} external:{t[3]})")
    if dns_rows:
        for d in dns_rows:
            print(f"  DNS [{d[0]}]: {d[1]} → {d[2]}{f':{d[3]}' if d[3] else ''}")

    confirm = input("\nAre you sure you want to delete this server? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    # Step 2: Delete Crafty server
    if crafty_server_id:
        print("\n[1/3] Deleting Crafty server...")
        token = crafty_login()
        if token:
            delete_crafty_server(crafty_server_id, {"Authorization": f"Bearer {token}"})
        else:
            print("⚠️  Could not log in to Crafty — skipping Crafty deletion")
    else:
        print("[1/3] No Crafty ID stored — skipping Crafty deletion")

    # Step 3: Delete Cloudflare DNS records by stored CF record IDs
    print("\n[2/3] Deleting Cloudflare DNS records...")
    if dns_rows:
        for _, name, _, _, cf_id in dns_rows:
            print(f"  Deleting {name}...")
            delete_dns_record_by_id(cf_id)
    else:
        print("  No DNS records stored for this server")

    # Step 4: Delete DB entry (cascades to playit_tunnels + dns_records)
    print("\n[3/3] Deleting database entry...")
    try:
        cursor.execute("DELETE FROM servers WHERE id = %s", (db_server_id,))
        connection.commit()
        print(f"Database entry {db_server_id} deleted (tunnels + DNS records cascaded)")
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        connection.rollback()
        return

    print(f"\n✅ Server '{server_name}' fully deleted.")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        server_id = sys.argv[1]
    else:
        server_id = input("Enter the database server ID to delete: ").strip()

    if not server_id.isdigit():
        print("Error: server ID must be a number")
        sys.exit(1)

    delete_server(int(server_id))

