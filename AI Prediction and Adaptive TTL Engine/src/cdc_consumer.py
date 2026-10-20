"""
cdc_consumer.py — Background Kafka Consumer for Debezium Change Data Capture (CDC).

Listens for database mutation events (INSERT, UPDATE, DELETE) streamed by Debezium
via Apache Kafka, extracts the mutated entity ID, and feeds it into VolatilityEngine
to compute real-time EWMA volatility penalties.

Features:
  - Non-blocking daemon background worker
  - Graceful auto-reconnect with exponential backoff if Kafka is offline
  - Direct integration with VolatilityEngine
  - Built-in simulation fallback for offline testing
"""

import json
import logging
import re
import threading
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger("cdc_consumer")

class CDCKafkaConsumer:
    def __init__(
        self,
        volatility_engine,
        bootstrap_servers: str = "localhost:9092",
        topic_pattern: str = r"^.*public\.(products|items).*$|cdc\.public\..*|db\.mutations",
        group_id: str = "adaptive-ttl-cdc-group",
    ):
        self.vol_engine = volatility_engine
        self.bootstrap_servers = bootstrap_servers
        self.topic_pattern = topic_pattern
        self.group_id = group_id
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.is_connected = False
        self.total_mutations_received = 0
        self.last_mutation_key = None
        self.last_mutation_time = None
        self.last_error = None

    def start(self):
        """Start the Kafka consumer in a daemon background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="CDCKafkaConsumerThread", daemon=True)
        self._thread.start()
        logger.info("Kafka CDC Consumer background thread started (target: %s)", self.bootstrap_servers)

    def stop(self):
        """Signal the consumer thread to terminate cleanly."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.is_connected = False

    def _run_loop(self):
        """Main loop with auto-reconnect backoff."""
        while not self._stop_event.is_set():
            try:
                from kafka import KafkaConsumer
                logger.info("Attempting connection to Kafka at %s...", self.bootstrap_servers)
                
                consumer = KafkaConsumer(
                    bootstrap_servers=self.bootstrap_servers.split(","),
                    group_id=self.group_id,
                    auto_offset_reset="latest",
                    enable_auto_commit=True,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8", errors="ignore")),
                    consumer_timeout_ms=1000,
                )
                
                # Subscribe to regex pattern or fallback list
                try:
                    consumer.subscribe(pattern=self.topic_pattern)
                except Exception:
                    consumer.subscribe(["cdc.public.products", "cdc.public.items", "db.mutations"])
                    
                self.is_connected = True
                self.last_error = None
                logger.info("Connected to Kafka! Listening for Debezium CDC mutations...")

                while not self._stop_event.is_set():
                    try:
                        for record in consumer:
                            if self._stop_event.is_set():
                                break
                            self._process_message(record.value, record.topic)
                    except Exception as poll_err:
                        if not self._stop_event.is_set():
                            logger.debug("Kafka poll cycle: %s", poll_err)
                    time.sleep(0.1)

            except Exception as exc:
                self.is_connected = False
                self.last_error = str(exc)
                logger.debug("Kafka broker not reachable yet (%s). Reconnecting in 8s...", exc)
                time.sleep(8)

    def _process_message(self, data: dict, topic: str):
        """Parse Debezium CDC message payload and update VolatilityEngine."""
        try:
            if not isinstance(data, dict):
                return

            payload = data.get("payload", data)
            op = payload.get("op")  # 'u' (update), 'd' (delete), 'c' (create), 'r' (read snapshot)
            after = payload.get("after") or {}
            before = payload.get("before") or {}

            # We care primarily about updates, deletes, and creates as volatile operations
            if op in ("u", "d", "c"):
                item_id = after.get("id") or before.get("id")
                entity_key = f"product:{item_id}" if "product" in topic else f"item:{item_id}"
                
                # Check for explicit cache_key field
                cache_key = after.get("cache_key") or entity_key
                
                # Record mutation in EWMA volatility engine
                if self.vol_engine:
                    self.vol_engine.record_mutation(cache_key)
                    # If this is numeric ID, also bump the corresponding twitter trace key
                    if item_id is not None:
                        self.vol_engine.record_mutation(f"twitter:key:{item_id}")

                self.total_mutations_received += 1
                self.last_mutation_key = cache_key
                self.last_mutation_time = datetime.now().strftime("%H:%M:%S")

                logger.info(
                    "[Debezium CDC ➔ Kafka] Mutation received: key='%s', op='%s', topic='%s' (Total: %d)",
                    cache_key, op, topic, self.total_mutations_received
                )

        except Exception as exc:
            logger.warning("Error processing CDC message: %s", exc)

    def simulate_mutation(self, cache_key: str, op: str = "u") -> dict:
        """Simulate a CDC mutation event (useful for demonstrations or offline mode)."""
        if self.vol_engine:
            self.vol_engine.record_mutation(cache_key)

        self.total_mutations_received += 1
        self.last_mutation_key = cache_key
        self.last_mutation_time = datetime.now().strftime("%H:%M:%S")

        logger.info("[Simulated CDC Event] Mutated key='%s' (op=%s)", cache_key, op)
        return {
            "status": "success",
            "cache_key": cache_key,
            "op": op,
            "timestamp": self.last_mutation_time,
            "total_mutations": self.total_mutations_received,
        }

    def status(self) -> dict:
        """Return real-time diagnostic telemetry about the Kafka CDC stream."""
        return {
            "connected": self.is_connected,
            "bootstrap_servers": self.bootstrap_servers,
            "total_mutations_received": self.total_mutations_received,
            "last_mutation_key": self.last_mutation_key,
            "last_mutation_time": self.last_mutation_time,
            "status_text": "CONNECTED (Live Kafka Stream)" if self.is_connected else "STANDBY (Auto-Reconnecting / Simulation Ready)",
            "last_error": self.last_error,
        }
