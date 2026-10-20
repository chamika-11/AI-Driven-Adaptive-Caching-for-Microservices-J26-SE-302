"""
register_debezium.py — Automated registration script for Debezium PostgreSQL CDC Connector.

Sends HTTP POST to Debezium Connect (default: http://localhost:8083/connectors)
to register the PostgreSQL CDC connector for table 'items'.
"""

import json
import sys
import time
import urllib.request
import urllib.error

DEBEZIUM_URL = "http://localhost:8083/connectors"

CONNECTOR_CONFIG = {
    "name": "postgres-cdc-connector",
    "config": {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "tasks.max": "1",
        "plugin.name": "pgoutput",
        "database.hostname": "postgres",
        "database.port": "5432",
        "database.user": "cache",
        "database.password": "cache",
        "database.dbname": "cache",
        "table.include.list": "public.products,public.items",
        "topic.prefix": "cdc"
    }
}

def register(max_retries=10, retry_delay=3):
    print("=== Registering Debezium PostgreSQL CDC Connector ===")
    print(f"Target URL: {DEBEZIUM_URL}")
    
    payload_bytes = json.dumps(CONNECTOR_CONFIG).encode("utf-8")
    
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                DEBEZIUM_URL,
                data=payload_bytes,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"[SUCCESS] Connector registered successfully on attempt {attempt}:")
                print(json.dumps(data, indent=2))
                return True
        except urllib.error.HTTPError as e:
            if e.code == 409:
                print("[INFO] Connector 'postgres-cdc-connector' already exists and is active!")
                return True
            err_body = e.read().decode("utf-8", errors="ignore")
            print(f"[HTTP {e.code}] Error: {err_body}")
        except Exception as exc:
            print(f"[Attempt {attempt}/{max_retries}] Debezium Connect not ready yet ({exc}). Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            
    print("[ERROR] Failed to reach Debezium Connect after retries. Ensure 'docker compose up -d debezium' is running.")
    return False

if __name__ == "__main__":
    success = register()
    sys.exit(0 if success else 1)
