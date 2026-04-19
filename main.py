import os
import requests
import urllib3
from dotenv import load_dotenv
import psycopg2
from datetime import datetime

load_dotenv()

connection=psycopg2.connect(
database=os.getenv("DB_NAME"),
user=os.getenv("DB_USER"),
password=os.getenv("DB_PASSWORD"),
host=os.getenv("DB_HOST"),
port=os.getenv("DB_PORT"),
sslmode="require" 
)

cursor = connection.cursor()




urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

base_url = os.getenv("BASE_URL", "https://localhost:8443")
username = os.getenv("USERNAME", "admin")
password = os.getenv("PASSWORD", "admin")

server_name = "My Minecraft Server"
type = "paper"
version = "1.18.2"
min_mem = 2
max_mem = 4
server_properties_port = 25570


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

def create_server(token):

  server_name = "Example name"#input("Enter server name: ")
  type = "paper"#input("Enter server type (e.g. paper): ")
  version = "1.18.2"#input("Enter server version (e.g. 1.18.2): ")
  min_mem = 2#int(input("Enter minimum memory (GB): "))
  max_mem = 4#int(input("Enter maximum memory (GB): "))
  server_properties_port = 25570#int(input("Enter server properties port (e.g. 25570): "))

  data = {
    "name": server_name,
    "monitoring_type": "minecraft_java",
    "minecraft_java_monitoring_data": {
      "host": "127.0.0.1",
      "port": server_properties_port,
    },
    "create_type": "minecraft_java",
    "minecraft_java_create_data": {
      "create_type": "download_jar",
      "download_jar_create_data": {
        "category": "mc_java_servers",
        "type": type,
        "version": version,
        "mem_min": min_mem, 
        "mem_max": max_mem,
        "server_properties_port": server_properties_port
      }
    }
  }

  headers = {"Authorization": f"Bearer {token}"}
  try:
    cursor.execute(
        "INSERT INTO servers (name, type, version, serverPort, createdAt) VALUES (%s, %s, %s, %s, %s)",
        (server_name, type, version, server_properties_port, datetime.now())
    )
    connection.commit()
    print("Server inserted successfully")
  except Exception as e:
      print(f"Database insert failed: {e}")
      connection.rollback()

      print(response.json())


token = login()
if token:
  create_server(token)