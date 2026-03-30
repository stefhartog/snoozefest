from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    mqtt_topic_prefix: str
    mqtt_client_id: str
    homeassistant_discovery_prefix: str
    timezone: str
    data_file: str
    tick_seconds: int
    default_snooze_minutes: int
    timer_add_seconds: int
    alarm_trigger_grace_seconds: int

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        with open(path) as f:
            data = json.load(f)
        return cls(
            mqtt_host=data["mqtt_host"],
            mqtt_port=int(data.get("mqtt_port", 1883)),
            mqtt_username=data.get("mqtt_username", ""),
            mqtt_password=data.get("mqtt_password", ""),
            mqtt_topic_prefix=data.get("mqtt_topic_prefix", "snoozefest"),
            mqtt_client_id=data.get("mqtt_client_id", "snoozefest"),
            homeassistant_discovery_prefix=data.get("homeassistant_discovery_prefix", "homeassistant"),
            timezone=data.get("timezone", "UTC"),
            data_file=data.get("data_file", "snoozefest_data.json"),
            tick_seconds=int(data.get("tick_seconds", 1)),
            default_snooze_minutes=int(data.get("default_snooze_minutes", 10)),
            timer_add_seconds=max(1, int(data.get("timer_add_seconds") or 60)),
            alarm_trigger_grace_seconds=max(0, int(data.get("alarm_trigger_grace_seconds", 120))),
        )
