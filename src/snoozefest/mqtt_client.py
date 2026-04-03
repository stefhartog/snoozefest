from __future__ import annotations

import json
import logging
from typing import Callable

import paho.mqtt.client as mqtt

from .config import Config

logger = logging.getLogger(__name__)


class MQTTClient:
    """
    Thin wrapper around paho-mqtt (≥ 2.0) that:
    - Subscribes to all snoozefest command topics on connect.
    - Publishes LWT "false" / online "true" on the online topic.
    - Dispatches inbound JSON payloads to *on_command(cmd_suffix, payload)*.
    """

    def __init__(self, config: Config, on_command: Callable[[str, object], None]) -> None:
        self._config = config
        self._on_command = on_command
        self._prefix = config.mqtt_topic_prefix

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.mqtt_client_id,
        )

        if config.mqtt_username:
            self._client.username_pw_set(config.mqtt_username, config.mqtt_password)

        # LWT: broker publishes "false" if we disconnect unexpectedly
        self._client.will_set(
            f"{self._prefix}/state/online",
            payload="false",
            qos=1,
            retain=True,
        )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # ------------------------------------------------------------------ lifecycle

    def connect(self) -> None:
        self._client.connect(self._config.mqtt_host, self._config.mqtt_port, keepalive=60)
        self._client.loop_start()

    def disconnect(self) -> None:
        self.publish(f"{self._prefix}/state/online", "false", retain=True)
        self._client.loop_stop()
        self._client.disconnect()

    # ------------------------------------------------------------------ paho callbacks

    def _on_connect(self, client, userdata, connect_flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            logger.error("MQTT connection refused: %s", reason_code)
            return

        logger.info("MQTT connected to %s:%s", self._config.mqtt_host, self._config.mqtt_port)

        # Clear any stale retained message on command_result so voice automations
        # do not immediately receive an old cached response on subscribe.
        client.publish(f"{self._prefix}/state/command_result", payload=None, retain=True)

        for suffix in (
            "purge_all",
            "alarm/new",
            "alarm/set",
            "alarm/update",
            "alarm/remove",
            "alarm/snooze",
            "alarm/dismiss",
            "timer/new",
            "timer/set",
            "timer/update",
            "timer/cancel",
            "timer/remove",
            "timer/snooze",
            "timer/add_time",
            "timer/pause",
            "timer/resume",
            "timer/reset",
            "timer/activate",
            "timer/dismiss",
            "settings/timer_add_seconds/set",
            "settings/selected_alarm_id/set",
            "settings/selected_timer_id/set",
            "state/request",
        ):
            client.subscribe(f"{self._prefix}/cmd/{suffix}")
        client.subscribe(f"{self._prefix}/cmd/alarm/+/enabled/set")
        client.subscribe(f"{self._prefix}/cmd/alarm/+/time/set")
        client.subscribe(f"{self._prefix}/cmd/alarm/+/label/set")
        client.subscribe(f"{self._prefix}/cmd/alarm/+/weekdays/set")
        client.subscribe(f"{self._prefix}/cmd/alarm/+/weekday/+/set")
        client.subscribe(f"{self._prefix}/cmd/timer/+/label/set")
        client.subscribe(f"{self._prefix}/cmd/timer/+/duration/set")
        client.subscribe(f"{self._prefix}/cmd/timer/+/temporary/set")

        self.publish(f"{self._prefix}/state/online", "true", retain=True)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        logger.warning("MQTT disconnected: %s", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload_text = msg.payload.decode()
        except UnicodeDecodeError as exc:
            logger.warning("Bad payload on %s: %s", msg.topic, exc)
            return

        try:
            payload: object = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = payload_text.strip()

        cmd = msg.topic.removeprefix(f"{self._prefix}/cmd/")
        try:
            self._on_command(cmd, payload)
        except Exception:
            logger.exception("Unhandled error in command handler for %s", cmd)

    # ------------------------------------------------------------------ publish

    def publish(self, topic: str, payload, *, retain: bool = False, qos: int = 0) -> None:
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        elif payload is None:
            payload = "null"
        elif isinstance(payload, bool):
            payload = "true" if payload else "false"
        else:
            payload = str(payload)
        self._client.publish(topic, payload=payload, retain=retain, qos=qos)

    def publish_state(self, key: str, payload, *, retain: bool = True) -> None:
        self.publish(f"{self._prefix}/state/{key}", payload, retain=retain)
