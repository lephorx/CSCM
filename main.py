import os
import requests
import urllib3
from dotenv import load_dotenv

load_dotenv()


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
  response = requests.post(f"{base_url}/api/v2/servers", json=data, headers=headers, verify=False)

  print(response.json())


token = login()
if token:
  create_server(token)