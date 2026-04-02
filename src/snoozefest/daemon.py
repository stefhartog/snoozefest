from __future__ import annotations

import logging
import re
import signal
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .config import Config
from .humanize import duration_to_speech
from .humanize import remaining_to_day_phrase
from .mqtt_client import MQTTClient
from .scheduler import Scheduler
from .store import Store

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 60  # seconds
_ALARM_COUNTDOWN_REFRESH_INTERVAL = 600  # seconds
_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class Daemon:
    """
    Brings together the Store, Scheduler, and MQTTClient into the running
    alarm service.  The MQTT client runs in paho's background thread; the
    scheduler tick loop runs in the main thread.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._tz = ZoneInfo(config.timezone)
        self._store = Store(config.data_file)
        self._published_alarm_entities: set[str] = set()

        self._scheduler = Scheduler(
            store=self._store,
            tz=self._tz,
            alarm_trigger_grace_seconds=config.alarm_trigger_grace_seconds,
            on_alarm_triggered=self._on_alarm_triggered,
            on_timer_finished=self._on_timer_finished,
            on_state_changed=self._publish_all_state,
        )

        self._mqtt = MQTTClient(config=config, on_command=self._handle_command)
        self._running = False
        self._active_request_id: Optional[str] = None
        self._timer_add_seconds = max(1, int(config.timer_add_seconds))

    def _timestamp_payload(self, dt: datetime) -> dict:
        utc_dt = dt.astimezone(timezone.utc)
        local_dt = utc_dt.astimezone(self._tz)
        return {
            "utc": utc_dt.isoformat(),
            "local": local_dt.isoformat(),
            "friendly_local": local_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "timezone": str(self._tz),
        }

    # ------------------------------------------------------------------ scheduler callbacks

    def _on_alarm_triggered(self, alarm_id: str, label: str) -> None:
        logger.info("Alarm triggered: %s (%s)", label, alarm_id)
        ts = self._timestamp_payload(datetime.now(timezone.utc))
        self._mqtt.publish_state(
            "alarm_triggered",
            [{
                "alarm_id": alarm_id,
                "label": label,
                "triggered_at": ts["utc"],
                "triggered_at_utc": ts["utc"],
                "triggered_at_local": ts["local"],
                "triggered_at_friendly": ts["friendly_local"],
                "timezone": ts["timezone"],
            }],
            retain=False,
        )

    def _on_timer_finished(self, timer_id: str, label: str) -> None:
        logger.info("Timer finished: %s (%s)", label, timer_id)
        ts = self._timestamp_payload(datetime.now(timezone.utc))
        self._mqtt.publish_state(
            "timer_finished",
            [{
                "timer_id": timer_id,
                "label": label,
                "finished_at": ts["utc"],
                "finished_at_utc": ts["utc"],
                "finished_at_local": ts["local"],
                "finished_at_friendly": ts["friendly_local"],
                "timezone": ts["timezone"],
            }],
            retain=False,
        )

    def _publish_all_state(self) -> None:
        state = self._scheduler.full_state()
        ringing_alarm_count = self._ringing_alarm_count(state)
        ringing_timer_count = self._ringing_timer_count(state)
        self._mqtt.publish_state("alarms", state["alarms"])
        self._mqtt.publish_state("timers", state["timers"])
        self._mqtt.publish_state("alarms_glance", self._alarms_glance_summary(state))
        self._mqtt.publish_state("timers_glance", self._timers_glance_summary(state))
        # Clear deprecated aggregate active_alarm topic retained state.
        self._mqtt.publish_state("active_alarm", "")
        self._mqtt.publish_state("ringing_alarm_count", ringing_alarm_count)
        self._mqtt.publish_state("ringing_timer_count", ringing_timer_count)
        self._mqtt.publish_state("next_alarm", state["next_alarm"])
        self._publish_manager_entities()
        self._publish_alarm_entities(state)
        self._publish_timer_entities(state)

    def _publish_manager_entities(self) -> None:
        if not self._config.homeassistant_discovery_prefix:
            return

        add_alarm_payload = {
            "name": "Add Alarm",
            "unique_id": self._manager_add_alarm_object_id(),
            "object_id": self._manager_add_alarm_object_id(),
            "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
            "payload_available": "true",
            "payload_not_available": "false",
            "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/alarm/new",
            "payload_press": "{}",
            "icon": "mdi:alarm-plus",
            "device": self._root_device(),
        }
        add_timer_payload = {
            "name": "Add Timer",
            "unique_id": self._manager_add_timer_object_id(),
            "object_id": self._manager_add_timer_object_id(),
            "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
            "payload_available": "true",
            "payload_not_available": "false",
            "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/timer/new",
            "payload_press": "{}",
            "icon": "mdi:timer-plus",
            "device": self._root_device(),
        }
        purge_all_payload = {
            "name": "Purge All Alarms & Timers",
            "unique_id": self._manager_purge_all_object_id(),
            "object_id": self._manager_purge_all_object_id(),
            "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
            "payload_available": "true",
            "payload_not_available": "false",
            "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/purge_all",
            "payload_press": "{}",
            "icon": "mdi:delete-sweep",
            "device": self._root_device(),
        }
        online_payload = {
            "name": "Online",
            "unique_id": self._manager_online_object_id(),
            "object_id": self._manager_online_object_id(),
            "state_topic": f"{self._config.mqtt_topic_prefix}/state/online",
            "payload_on": "true",
            "payload_off": "false",
            "device_class": "connectivity",
            "device": self._root_device(),
        }
        ringing_alarm_count_payload = {
            "name": "Ringing Alarm Count",
            "unique_id": self._manager_ringing_alarm_count_object_id(),
            "object_id": self._manager_ringing_alarm_count_object_id(),
            "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
            "payload_available": "true",
            "payload_not_available": "false",
            "state_topic": f"{self._config.mqtt_topic_prefix}/state/ringing_alarm_count",
            "icon": "mdi:alarm-light",
            "device": self._root_device(),
        }
        ringing_timer_count_payload = {
            "name": "Ringing Timer Count",
            "unique_id": self._manager_ringing_timer_count_object_id(),
            "object_id": self._manager_ringing_timer_count_object_id(),
            "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
            "payload_available": "true",
            "payload_not_available": "false",
            "state_topic": f"{self._config.mqtt_topic_prefix}/state/ringing_timer_count",
            "icon": "mdi:timer-alert",
            "device": self._root_device(),
        }
        alarms_glance_payload = {
            "name": "Alarms Glance",
            "unique_id": self._manager_alarms_glance_object_id(),
            "object_id": self._manager_alarms_glance_object_id(),
            "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
            "payload_available": "true",
            "payload_not_available": "false",
            "state_topic": f"{self._config.mqtt_topic_prefix}/state/alarms_glance",
            "icon": "mdi:format-list-bulleted",
            "device": self._root_device(),
        }
        timers_glance_payload = {
            "name": "Timers Glance",
            "unique_id": self._manager_timers_glance_object_id(),
            "object_id": self._manager_timers_glance_object_id(),
            "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
            "payload_available": "true",
            "payload_not_available": "false",
            "state_topic": f"{self._config.mqtt_topic_prefix}/state/timers_glance",
            "icon": "mdi:format-list-bulleted",
            "device": self._root_device(),
        }
        timer_add_seconds_payload = {
            "name": "Timer Add Time Seconds",
            "unique_id": self._manager_timer_add_seconds_object_id(),
            "object_id": self._manager_timer_add_seconds_object_id(),
            "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
            "payload_available": "true",
            "payload_not_available": "false",
            "state_topic": self._manager_timer_add_seconds_state_topic(),
            "command_topic": self._manager_timer_add_seconds_command_topic(),
            "icon": "mdi:timer-plus-outline",
            "min": 1,
            "max": 3600,
            "step": 1,
            "mode": "box",
            "unit_of_measurement": "s",
            "device": self._root_device(),
        }
        self._mqtt.publish(self._manager_add_alarm_discovery_topic(), add_alarm_payload, retain=True)
        self._mqtt.publish(self._manager_add_timer_discovery_topic(), add_timer_payload, retain=True)
        self._mqtt.publish(self._manager_purge_all_discovery_topic(), purge_all_payload, retain=True)
        self._mqtt.publish(self._manager_online_discovery_topic(), online_payload, retain=True)
        self._mqtt.publish(self._manager_ringing_alarm_count_discovery_topic(), ringing_alarm_count_payload, retain=True)
        self._mqtt.publish(self._manager_ringing_timer_count_discovery_topic(), ringing_timer_count_payload, retain=True)
        self._mqtt.publish(self._manager_alarms_glance_discovery_topic(), alarms_glance_payload, retain=True)
        self._mqtt.publish(self._manager_timers_glance_discovery_topic(), timers_glance_payload, retain=True)
        self._mqtt.publish(self._manager_timer_add_seconds_discovery_topic(), timer_add_seconds_payload, retain=True)
        self._mqtt.publish(self._manager_timer_add_seconds_state_topic(), str(self._timer_add_seconds), retain=True)

    @staticmethod
    def _ringing_alarm_count(state: dict) -> int:
        return sum(1 for alarm in state.get("alarms", []) if str(alarm.get("status")) == "ringing")

    @staticmethod
    def _ringing_timer_count(state: dict) -> int:
        return sum(1 for timer in state.get("timers", []) if str(timer.get("status")) == "ringing")

    @staticmethod
    def _truncate_glance(text: str, limit: int = 250) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _alarms_glance_summary(self, state: dict) -> str:
        alarms = state.get("alarms", [])
        if not alarms:
            return "No alarms"

        parts: list[str] = []
        for alarm in alarms:
            alarm_id = str(alarm.get("id", "?"))
            time_set = str(alarm.get("time", "--:--"))
            status = str(alarm.get("status_normalized") or alarm.get("status") or "Unknown")
            parts.append(f"A{alarm_id} {time_set} {status}")
        return self._truncate_glance(" | ".join(parts))

    def _timers_glance_summary(self, state: dict) -> str:
        timers = state.get("timers", [])
        if not timers:
            return "No timers"

        parts: list[str] = []
        for timer in timers:
            timer_id = str(timer.get("id", "?"))
            label = str(timer.get("label", "Timer")).strip() or "Timer"
            status = str(timer.get("status_normalized") or timer.get("status") or "Unknown")
            parts.append(f"T{timer_id} {label} {status}")
        return self._truncate_glance(" | ".join(parts))

    def _alarm_object_id(self, alarm_id: str) -> str:
        safe_alarm_id = alarm_id.replace("-", "_")
        return f"{self._config.mqtt_topic_prefix}_alarm_{safe_alarm_id}"

    def _root_device_identifier(self) -> str:
        return self._config.mqtt_topic_prefix

    def _is_dev_instance(self) -> bool:
        prefix = self._config.mqtt_topic_prefix.lower()
        client_id = self._config.mqtt_client_id.lower()
        return prefix.endswith("_dev") or prefix.endswith("-dev") or "dev" in client_id

    def _instance_name_prefix(self) -> str:
        return "Snoozefest Dev" if self._is_dev_instance() else "Snoozefest"

    def _root_device(self) -> dict:
        return {
            "identifiers": [self._root_device_identifier()],
            "name": self._instance_name_prefix(),
            "manufacturer": "GitHub Copilot",
            "model": "MQTT Alarm Scheduler",
        }

    def _manager_add_alarm_object_id(self) -> str:
        return f"{self._config.mqtt_topic_prefix}_manager_add_alarm"

    def _manager_add_alarm_discovery_topic(self) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._manager_add_alarm_object_id()}/config"
        )

    def _manager_add_timer_object_id(self) -> str:
        return f"{self._config.mqtt_topic_prefix}_manager_add_timer"

    def _manager_add_timer_discovery_topic(self) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._manager_add_timer_object_id()}/config"
        )

    def _manager_purge_all_object_id(self) -> str:
        return f"{self._config.mqtt_topic_prefix}_manager_purge_all"

    def _manager_purge_all_discovery_topic(self) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._manager_purge_all_object_id()}/config"
        )

    def _manager_online_object_id(self) -> str:
        return f"{self._config.mqtt_topic_prefix}_manager_online"

    def _manager_online_discovery_topic(self) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/binary_sensor/"
            f"{self._manager_online_object_id()}/config"
        )

    def _manager_ringing_alarm_count_object_id(self) -> str:
        return f"{self._config.mqtt_topic_prefix}_manager_ringing_alarm_count"

    def _manager_ringing_alarm_count_discovery_topic(self) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._manager_ringing_alarm_count_object_id()}/config"
        )

    def _manager_ringing_timer_count_object_id(self) -> str:
        return f"{self._config.mqtt_topic_prefix}_manager_ringing_timer_count"

    def _manager_ringing_timer_count_discovery_topic(self) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._manager_ringing_timer_count_object_id()}/config"
        )

    def _manager_alarms_glance_object_id(self) -> str:
        return f"{self._config.mqtt_topic_prefix}_manager_alarms_glance"

    def _manager_alarms_glance_discovery_topic(self) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._manager_alarms_glance_object_id()}/config"
        )

    def _manager_timers_glance_object_id(self) -> str:
        return f"{self._config.mqtt_topic_prefix}_manager_timers_glance"

    def _manager_timers_glance_discovery_topic(self) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._manager_timers_glance_object_id()}/config"
        )

    def _manager_timer_add_seconds_object_id(self) -> str:
        return f"{self._config.mqtt_topic_prefix}_manager_timer_add_seconds"

    def _manager_timer_add_seconds_discovery_topic(self) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/number/"
            f"{self._manager_timer_add_seconds_object_id()}/config"
        )

    def _manager_timer_add_seconds_state_topic(self) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/settings/timer_add_seconds"

    def _manager_timer_add_seconds_command_topic(self) -> str:
        return f"{self._config.mqtt_topic_prefix}/cmd/settings/timer_add_seconds/set"

    def _alarm_device_identifier(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_device"

    def _timer_device_identifier(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_device"

    def _alarm_label(self, alarm: dict, alarm_id: str) -> str:
        label = str(alarm.get("label") or "").strip()
        suffix = label or f"Alarm {alarm_id}"
        return f"{self._instance_name_prefix()} Alarm - {suffix}"

    def _timer_label(self, timer: dict, timer_id: str) -> str:
        label = str(timer.get("label") or "").strip()
        suffix = label or f"Timer {timer_id}"
        return f"{self._instance_name_prefix()} Timer - {suffix}"

    def _alarm_device(self, alarm: dict, alarm_id: str) -> dict:
        return {
            "identifiers": [self._alarm_device_identifier(alarm_id)],
            "name": self._alarm_label(alarm, alarm_id),
            "manufacturer": "GitHub Copilot",
            "model": "MQTT Alarm",
            "via_device": self._root_device_identifier(),
        }

    def _timer_device(self, timer: dict, timer_id: str) -> dict:
        return {
            "identifiers": [self._timer_device_identifier(timer_id)],
            "name": self._timer_label(timer, timer_id),
            "manufacturer": "GitHub Copilot",
            "model": "MQTT Timer",
            "via_device": self._root_device_identifier(),
        }

    def _alarm_remove_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_remove"

    def _alarm_snooze_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_snooze"

    def _alarm_dismiss_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_dismiss"

    def _alarm_status_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_status"

    def _alarm_remaining_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_remaining"

    def _alarm_remaining_friendly_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_remaining_friendly"

    def _alarm_next_day_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_next_day"

    def _alarm_eta_object_id(self, alarm_id: str) -> str:
        # Backward-compatible alias retained for transitional references.
        return self._alarm_remaining_object_id(alarm_id)

    def _alarm_recurring_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_recurring"

    def _alarm_kind_object_id(self, alarm_id: str) -> str:
        # Backward-compatible alias retained for transitional cleanup.
        return self._alarm_recurring_object_id(alarm_id)

    def _alarm_label_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_label"

    def _alarm_time_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_time"

    def _alarm_time_picker_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_time_picker"

    def _alarm_time_set_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_time_set_display"

    def _alarm_status_text_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_status_display"

    def _alarm_time_set_discovery_topic_legacy_text(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/text/"
            f"{self._alarm_object_id(alarm_id)}_time_set/config"
        )

    def _alarm_status_text_discovery_topic_legacy_text(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/text/"
            f"{self._alarm_object_id(alarm_id)}_status_text/config"
        )

    def _alarm_time_set_discovery_topic_legacy_sensor(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._alarm_object_id(alarm_id)}_time_set/config"
        )

    def _alarm_status_text_discovery_topic_legacy_sensor(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._alarm_object_id(alarm_id)}_status_text/config"
        )

    def _alarm_weekdays_object_id(self, alarm_id: str) -> str:
        return f"{self._alarm_object_id(alarm_id)}_weekdays"

    def _alarm_weekday_object_id(self, alarm_id: str, weekday: int) -> str:
        return f"{self._alarm_object_id(alarm_id)}_weekday_{weekday}"

    def _alarm_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/switch/"
            f"{self._alarm_object_id(alarm_id)}/config"
        )

    def _alarm_remove_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._alarm_remove_object_id(alarm_id)}/config"
        )

    def _alarm_snooze_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._alarm_snooze_object_id(alarm_id)}/config"
        )

    def _alarm_dismiss_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._alarm_dismiss_object_id(alarm_id)}/config"
        )

    def _alarm_status_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._alarm_status_object_id(alarm_id)}/config"
        )

    def _alarm_remaining_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._alarm_remaining_object_id(alarm_id)}/config"
        )

    def _alarm_remaining_friendly_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._alarm_remaining_friendly_object_id(alarm_id)}/config"
        )

    def _alarm_next_day_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._alarm_next_day_object_id(alarm_id)}/config"
        )

    def _alarm_eta_discovery_topic_legacy(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._alarm_object_id(alarm_id)}_eta/config"
        )

    def _alarm_eta_discovery_topic(self, alarm_id: str) -> str:
        return self._alarm_remaining_discovery_topic(alarm_id)

    def _alarm_recurring_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/switch/"
            f"{self._alarm_recurring_object_id(alarm_id)}/config"
        )

    def _alarm_kind_discovery_topic_legacy(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._alarm_object_id(alarm_id)}_kind/config"
        )

    def _alarm_kind_discovery_topic(self, alarm_id: str) -> str:
        return self._alarm_recurring_discovery_topic(alarm_id)

    def _alarm_label_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/text/"
            f"{self._alarm_label_object_id(alarm_id)}/config"
        )

    def _alarm_time_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/text/"
            f"{self._alarm_time_object_id(alarm_id)}/config"
        )

    def _alarm_time_discovery_topic_time_picker(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/time/"
            f"{self._alarm_time_picker_object_id(alarm_id)}/config"
        )

    def _alarm_time_set_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._alarm_time_set_object_id(alarm_id)}/config"
        )

    def _alarm_status_text_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._alarm_status_text_object_id(alarm_id)}/config"
        )

    def _alarm_time_discovery_topic_legacy_time(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/time/"
            f"{self._alarm_time_object_id(alarm_id)}/config"
        )

    def _alarm_weekdays_discovery_topic(self, alarm_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/text/"
            f"{self._alarm_weekdays_object_id(alarm_id)}/config"
        )

    def _alarm_weekday_discovery_topic(self, alarm_id: str, weekday: int) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/switch/"
            f"{self._alarm_weekday_object_id(alarm_id, weekday)}/config"
        )

    def _alarm_enabled_state_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/enabled"

    def _alarm_enabled_command_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/cmd/alarm/{alarm_id}/enabled/set"

    def _alarm_attributes_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/attributes"

    def _alarm_status_state_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/status"

    def _alarm_remaining_state_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/remaining"

    def _alarm_remaining_friendly_state_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/remaining_friendly"

    def _alarm_next_day_state_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/next_day"

    def _alarm_eta_state_topic_legacy(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/eta"

    def _alarm_eta_state_topic(self, alarm_id: str) -> str:
        return self._alarm_remaining_state_topic(alarm_id)

    def _alarm_recurring_state_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/recurring"

    def _alarm_recurring_command_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/cmd/alarm/{alarm_id}/recurring/set"

    def _alarm_kind_state_topic_legacy(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/kind"

    def _alarm_kind_state_topic(self, alarm_id: str) -> str:
        return self._alarm_recurring_state_topic(alarm_id)

    def _alarm_label_state_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/label"

    def _alarm_label_command_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/cmd/alarm/{alarm_id}/label/set"

    def _alarm_time_state_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/time"

    def _alarm_time_command_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/cmd/alarm/{alarm_id}/time/set"

    def _alarm_weekdays_state_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/weekdays"

    def _alarm_weekdays_command_topic(self, alarm_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/cmd/alarm/{alarm_id}/weekdays/set"

    def _alarm_weekday_state_topic(self, alarm_id: str, weekday: int) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/alarm/{alarm_id}/weekday/{weekday}"

    def _alarm_weekday_command_topic(self, alarm_id: str, weekday: int) -> str:
        return f"{self._config.mqtt_topic_prefix}/cmd/alarm/{alarm_id}/weekday/{weekday}/set"

    def _alarm_switch_name(self, alarm: dict) -> str:
        return str(alarm.get("label") or "Alarm")

    def _alarm_remove_name(self, alarm: dict) -> str:
        return f"Remove {self._alarm_switch_name(alarm)}"

    def _alarm_snooze_name(self, alarm: dict) -> str:
        return f"Snooze {self._alarm_switch_name(alarm)}"

    def _alarm_dismiss_name(self, alarm: dict) -> str:
        return f"Dismiss {self._alarm_switch_name(alarm)}"

    @staticmethod
    def _alarm_time_value(alarm: dict) -> str:
        raw = str(alarm.get("time") or "")
        if raw and len(raw) == 5:
            return f"{raw}:00"
        return raw

    def _alarm_time_entity_value(self, alarm: dict) -> str:
        base = self._alarm_time_value(alarm)
        if not base:
            fallback = (datetime.now(self._tz) + timedelta(minutes=1)).replace(second=0, microsecond=0)
            return fallback.strftime("%H:%M:%S")
        if len(base) >= 8:
            return base[:8]
        if len(base) == 5:
            return f"{base}:00"
        return base

    @staticmethod
    def _seconds_to_ddhhmmss(total_seconds: int) -> str:
        total_seconds = max(0, int(total_seconds))
        days, remainder = divmod(total_seconds, 24 * 3600)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _timer_remaining_entity_value(self, timer: dict) -> str:
        remaining = int(timer.get("remaining", timer.get("remaining_seconds", 0)))
        return self._seconds_to_ddhhmmss(remaining)

    def _timer_remaining_friendly_entity_value(self, timer: dict) -> str:
        remaining = int(timer.get("remaining", timer.get("remaining_seconds", 0)))
        return duration_to_speech(remaining)

    @staticmethod
    def _normalized_alarm_status_fallback(alarm: dict, status: str) -> str:
        status = str(status).strip().lower()
        if status == "ringing":
            return "Ringing"
        if status == "snoozed":
            return "Snoozed"
        if status == "active":
            return "Active"
        if not bool(alarm.get("enabled", True)):
            return "Inactive"
        return "Active"

    @staticmethod
    def _normalized_timer_status_fallback(timer_status: str) -> str:
        status = str(timer_status).strip().lower()
        if status == "ringing":
            return "Ringing"
        if status == "active":
            return "Active"
        if status == "paused":
            return "Paused"
        return "Inactive"

    def _timer_object_id(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}_timer_{timer_id}"

    def _timer_remove_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_remove"

    def _timer_label_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_label"

    def _timer_duration_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_duration"

    def _timer_temporary_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_temporary"

    def _timer_time_set_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_time_set_display"

    def _timer_status_text_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_status_display"

    def _timer_time_set_discovery_topic_legacy_text(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/text/"
            f"{self._timer_object_id(timer_id)}_time_set/config"
        )

    def _timer_status_text_discovery_topic_legacy_text(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/text/"
            f"{self._timer_object_id(timer_id)}_status_text/config"
        )

    def _timer_time_set_discovery_topic_legacy_sensor(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._timer_object_id(timer_id)}_time_set/config"
        )

    def _timer_status_text_discovery_topic_legacy_sensor(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._timer_object_id(timer_id)}_status_text/config"
        )

    def _timer_add_time_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_add_time"

    def _timer_snooze_object_id_legacy(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_snooze"

    def _timer_activate_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_activate"

    def _timer_reset_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_reset"

    def _timer_pause_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_pause"

    def _timer_resume_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_resume"

    def _timer_dismiss_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_dismiss"

    def _timer_status_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_status"

    def _timer_remaining_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_remaining"

    def _timer_remaining_friendly_object_id(self, timer_id: str) -> str:
        return f"{self._timer_object_id(timer_id)}_remaining_friendly"

    def _timer_status_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._timer_status_object_id(timer_id)}/config"
        )

    def _timer_label_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/text/"
            f"{self._timer_label_object_id(timer_id)}/config"
        )

    def _timer_duration_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/text/"
            f"{self._timer_duration_object_id(timer_id)}/config"
        )

    def _timer_temporary_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/switch/"
            f"{self._timer_temporary_object_id(timer_id)}/config"
        )

    def _timer_time_set_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._timer_time_set_object_id(timer_id)}/config"
        )

    def _timer_status_text_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._timer_status_text_object_id(timer_id)}/config"
        )

    def _timer_duration_discovery_topic_legacy(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/number/"
            f"{self._timer_duration_object_id(timer_id)}/config"
        )

    def _timer_remaining_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._timer_remaining_object_id(timer_id)}/config"
        )

    def _timer_remaining_friendly_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/sensor/"
            f"{self._timer_remaining_friendly_object_id(timer_id)}/config"
        )

    def _timer_remove_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._timer_remove_object_id(timer_id)}/config"
        )

    def _timer_add_time_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._timer_add_time_object_id(timer_id)}/config"
        )

    def _timer_snooze_discovery_topic_legacy(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._timer_snooze_object_id_legacy(timer_id)}/config"
        )

    def _timer_activate_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._timer_activate_object_id(timer_id)}/config"
        )

    def _timer_reset_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._timer_reset_object_id(timer_id)}/config"
        )

    def _timer_pause_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._timer_pause_object_id(timer_id)}/config"
        )

    def _timer_resume_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._timer_resume_object_id(timer_id)}/config"
        )

    def _timer_dismiss_discovery_topic(self, timer_id: str) -> str:
        return (
            f"{self._config.homeassistant_discovery_prefix}/button/"
            f"{self._timer_dismiss_object_id(timer_id)}/config"
        )

    def _timer_status_state_topic(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/timer/{timer_id}/status"

    def _timer_label_state_topic(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/timer/{timer_id}/label"

    def _timer_label_command_topic(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/cmd/timer/{timer_id}/label/set"

    def _timer_duration_state_topic(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/timer/{timer_id}/duration_seconds"

    def _timer_duration_command_topic(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/cmd/timer/{timer_id}/duration/set"

    def _timer_temporary_state_topic(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/timer/{timer_id}/temporary"

    def _timer_temporary_command_topic(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/cmd/timer/{timer_id}/temporary/set"

    def _timer_remaining_state_topic(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/timer/{timer_id}/remaining"

    def _timer_remaining_friendly_state_topic(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/timer/{timer_id}/remaining_friendly"

    def _timer_remaining_state_topic_legacy(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/timer/{timer_id}/remaining_seconds"

    def _timer_attributes_topic(self, timer_id: str) -> str:
        return f"{self._config.mqtt_topic_prefix}/state/timer/{timer_id}/attributes"

    @staticmethod
    def _timer_name(timer: dict) -> str:
        return str(timer.get("label") or "Timer")

    @staticmethod
    def _timer_duration_seconds(timer: dict) -> int:
        return max(0, int(timer.get("duration_seconds", 0)))

    def _timer_duration_entity_value(self, timer: dict) -> str:
        return self._seconds_to_ddhhmmss(self._timer_duration_seconds(timer))

    def _publish_timer_entities(self, state: dict) -> None:
        if not self._config.homeassistant_discovery_prefix:
            return

        timers: list[dict] = state.get("timers", [])
        current_ids = {str(timer["id"]) for timer in timers}
        previous_ids = getattr(self, "_published_timer_entities", set())

        for timer in timers:
            timer_id = str(timer["id"])
            label_payload = {
                "name": "01 Label",
                "unique_id": self._timer_label_object_id(timer_id),
                "object_id": self._timer_label_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._timer_label_state_topic(timer_id),
                "command_topic": self._timer_label_command_topic(timer_id),
                "icon": "mdi:form-textbox",
                "device": self._timer_device(timer, timer_id),
            }
            duration_payload = {
                "name": "02 Duration",
                "unique_id": self._timer_duration_object_id(timer_id),
                "object_id": self._timer_duration_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._timer_duration_state_topic(timer_id),
                "command_topic": self._timer_duration_command_topic(timer_id),
                "icon": "mdi:timer-edit-outline",
                "pattern": "^(\\d{1,3}:([01]\\d|2[0-3]):[0-5]\\d:[0-5]\\d|([01]\\d|2[0-3]):[0-5]\\d:[0-5]\\d|[0-5]?\\d:[0-5]\\d)$",
                "mode": "text",
                "device": self._timer_device(timer, timer_id),
            }
            temporary_payload = {
                "name": "03 Temporary",
                "unique_id": self._timer_temporary_object_id(timer_id),
                "object_id": self._timer_temporary_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._timer_temporary_state_topic(timer_id),
                "command_topic": self._timer_temporary_command_topic(timer_id),
                "payload_on": "ON",
                "payload_off": "OFF",
                "state_on": "ON",
                "state_off": "OFF",
                "icon": "mdi:content-save-outline",
                "device": self._timer_device(timer, timer_id),
            }
            status_payload = {
                "name": "08 Status",
                "unique_id": self._timer_status_object_id(timer_id),
                "object_id": self._timer_status_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._timer_status_state_topic(timer_id),
                "json_attributes_topic": self._timer_attributes_topic(timer_id),
                "icon": "mdi:timer-outline",
                "device": self._timer_device(timer, timer_id),
            }
            remaining_payload = {
                "name": "09 Remaining",
                "unique_id": self._timer_remaining_object_id(timer_id),
                "object_id": self._timer_remaining_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._timer_remaining_state_topic(timer_id),
                "icon": "mdi:timer-sand",
                "device": self._timer_device(timer, timer_id),
            }
            remaining_friendly_payload = {
                "name": "09b Remaining Friendly",
                "unique_id": self._timer_remaining_friendly_object_id(timer_id),
                "object_id": self._timer_remaining_friendly_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._timer_remaining_friendly_state_topic(timer_id),
                "icon": "mdi:account-voice",
                "device": self._timer_device(timer, timer_id),
            }
            remove_payload = {
                "name": "15 Remove",
                "unique_id": self._timer_remove_object_id(timer_id),
                "object_id": self._timer_remove_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/timer/remove",
                "payload_press": f'{{"id":"{timer_id}"}}',
                "icon": "mdi:delete",
                "device": self._timer_device(timer, timer_id),
            }
            add_time_payload = {
                "name": "10 Add Time",
                "unique_id": self._timer_add_time_object_id(timer_id),
                "object_id": self._timer_add_time_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/timer/add_time",
                "payload_press": f'{{"id":"{timer_id}"}}',
                "icon": "mdi:timer-plus",
                "device": self._timer_device(timer, timer_id),
            }
            activate_payload = {
                "name": "13 Activate",
                "unique_id": self._timer_activate_object_id(timer_id),
                "object_id": self._timer_activate_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/timer/activate",
                "payload_press": f'{{"id":"{timer_id}"}}',
                "icon": "mdi:play",
                "device": self._timer_device(timer, timer_id),
            }
            reset_payload = {
                "name": "13b Reset",
                "unique_id": self._timer_reset_object_id(timer_id),
                "object_id": self._timer_reset_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/timer/reset",
                "payload_press": f'{{"id":"{timer_id}"}}',
                "icon": "mdi:restore",
                "device": self._timer_device(timer, timer_id),
            }
            pause_payload = {
                "name": "11 Pause",
                "unique_id": self._timer_pause_object_id(timer_id),
                "object_id": self._timer_pause_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/timer/pause",
                "payload_press": f'{{"id":"{timer_id}"}}',
                "icon": "mdi:pause",
                "device": self._timer_device(timer, timer_id),
            }
            resume_payload = {
                "name": "12 Resume",
                "unique_id": self._timer_resume_object_id(timer_id),
                "object_id": self._timer_resume_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/timer/resume",
                "payload_press": f'{{"id":"{timer_id}"}}',
                "icon": "mdi:play-pause",
                "device": self._timer_device(timer, timer_id),
            }
            dismiss_payload = {
                "name": "14 Dismiss",
                "unique_id": self._timer_dismiss_object_id(timer_id),
                "object_id": self._timer_dismiss_object_id(timer_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/timer/dismiss",
                "payload_press": f'{{"id":"{timer_id}"}}',
                "icon": "mdi:stop",
                "device": self._timer_device(timer, timer_id),
            }

            self._mqtt.publish(self._timer_label_discovery_topic(timer_id), label_payload, retain=True)
            self._mqtt.publish(self._timer_duration_discovery_topic_legacy(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_duration_discovery_topic(timer_id), duration_payload, retain=True)
            self._mqtt.publish(self._timer_temporary_discovery_topic(timer_id), temporary_payload, retain=True)
            self._mqtt.publish(self._timer_time_set_discovery_topic_legacy_text(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_status_text_discovery_topic_legacy_text(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_time_set_discovery_topic_legacy_sensor(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_status_text_discovery_topic_legacy_sensor(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_time_set_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_status_discovery_topic(timer_id), status_payload, retain=True)
            self._mqtt.publish(self._timer_status_text_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_remaining_discovery_topic(timer_id), remaining_payload, retain=True)
            self._mqtt.publish(self._timer_remaining_friendly_discovery_topic(timer_id), remaining_friendly_payload, retain=True)
            self._mqtt.publish(self._timer_remove_discovery_topic(timer_id), remove_payload, retain=True)
            self._mqtt.publish(self._timer_snooze_discovery_topic_legacy(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_add_time_discovery_topic(timer_id), add_time_payload, retain=True)
            self._mqtt.publish(self._timer_pause_discovery_topic(timer_id), pause_payload, retain=True)
            self._mqtt.publish(self._timer_resume_discovery_topic(timer_id), resume_payload, retain=True)
            self._mqtt.publish(self._timer_activate_discovery_topic(timer_id), activate_payload, retain=True)
            self._mqtt.publish(self._timer_reset_discovery_topic(timer_id), reset_payload, retain=True)
            self._mqtt.publish(self._timer_dismiss_discovery_topic(timer_id), dismiss_payload, retain=True)
            self._mqtt.publish(self._timer_label_state_topic(timer_id), str(timer.get("label", "Timer")), retain=True)
            self._mqtt.publish(self._timer_duration_state_topic(timer_id), self._timer_duration_entity_value(timer), retain=True)
            self._mqtt.publish(self._timer_temporary_state_topic(timer_id), "ON" if bool(timer.get("temporary", False)) else "OFF", retain=True)
            self._mqtt.publish(
                self._timer_status_state_topic(timer_id),
                str(timer.get("status_normalized") or self._normalized_timer_status_fallback(str(timer.get("status", "inactive")))),
                retain=True,
            )
            self._mqtt.publish(self._timer_remaining_state_topic(timer_id), self._timer_remaining_entity_value(timer), retain=True)
            self._mqtt.publish(self._timer_remaining_friendly_state_topic(timer_id), self._timer_remaining_friendly_entity_value(timer), retain=True)
            self._mqtt.publish(self._timer_remaining_state_topic_legacy(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_attributes_topic(timer_id), timer, retain=True)

        removed_ids = previous_ids - current_ids
        for timer_id in removed_ids:
            self._mqtt.publish(self._timer_label_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_duration_discovery_topic_legacy(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_duration_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_temporary_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_time_set_discovery_topic_legacy_text(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_status_text_discovery_topic_legacy_text(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_time_set_discovery_topic_legacy_sensor(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_status_text_discovery_topic_legacy_sensor(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_time_set_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_status_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_status_text_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_remaining_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_remaining_friendly_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_remove_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_snooze_discovery_topic_legacy(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_add_time_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_pause_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_resume_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_activate_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_reset_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_dismiss_discovery_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_label_state_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_duration_state_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_temporary_state_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_status_state_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_remaining_state_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_remaining_friendly_state_topic(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_remaining_state_topic_legacy(timer_id), "", retain=True)
            self._mqtt.publish(self._timer_attributes_topic(timer_id), "", retain=True)

        self._published_timer_entities = current_ids

    def _publish_alarm_entities(self, state: dict) -> None:
        if not self._config.homeassistant_discovery_prefix:
            return

        alarms: list[dict] = state.get("alarms", [])

        current_ids = {str(alarm["id"]) for alarm in alarms}

        for alarm in alarms:
            alarm_id = str(alarm["id"])
            config_payload = {
                "name": "03 Enabled",
                "unique_id": self._alarm_object_id(alarm_id),
                "object_id": self._alarm_object_id(alarm_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._alarm_enabled_state_topic(alarm_id),
                "command_topic": self._alarm_enabled_command_topic(alarm_id),
                "json_attributes_topic": self._alarm_attributes_topic(alarm_id),
                "payload_on": "ON",
                "payload_off": "OFF",
                "state_on": "ON",
                "state_off": "OFF",
                "icon": "mdi:alarm",
                "device": self._alarm_device(alarm, alarm_id),
            }
            remove_payload = {
                "name": "10 Remove",
                "unique_id": self._alarm_remove_object_id(alarm_id),
                "object_id": self._alarm_remove_object_id(alarm_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/alarm/remove",
                "payload_press": f'{{"id":"{alarm_id}"}}',
                "icon": "mdi:delete",
                "device": self._alarm_device(alarm, alarm_id),
            }
            snooze_payload = {
                "name": "08 Snooze",
                "unique_id": self._alarm_snooze_object_id(alarm_id),
                "object_id": self._alarm_snooze_object_id(alarm_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/alarm/snooze",
                "payload_press": f'{{"id":"{alarm_id}","minutes":{self._config.default_snooze_minutes}}}',
                "icon": "mdi:alarm-snooze",
                "device": self._alarm_device(alarm, alarm_id),
            }
            dismiss_payload = {
                "name": "09 Dismiss",
                "unique_id": self._alarm_dismiss_object_id(alarm_id),
                "object_id": self._alarm_dismiss_object_id(alarm_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "command_topic": f"{self._config.mqtt_topic_prefix}/cmd/alarm/dismiss",
                "payload_press": f'{{"id":"{alarm_id}"}}',
                "icon": "mdi:alarm-off",
                "device": self._alarm_device(alarm, alarm_id),
            }
            status_payload = {
                "name": "06 Status",
                "unique_id": self._alarm_status_object_id(alarm_id),
                "object_id": self._alarm_status_object_id(alarm_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._alarm_status_state_topic(alarm_id),
                "icon": "mdi:alarm-light",
                "device": self._alarm_device(alarm, alarm_id),
            }
            remaining_payload = {
                "name": "07 Remaining",
                "unique_id": self._alarm_remaining_object_id(alarm_id),
                "object_id": self._alarm_remaining_object_id(alarm_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._alarm_remaining_state_topic(alarm_id),
                "icon": "mdi:timer-sand",
                "device": self._alarm_device(alarm, alarm_id),
            }
            remaining_friendly_payload = {
                "name": "07b Remaining Friendly",
                "unique_id": self._alarm_remaining_friendly_object_id(alarm_id),
                "object_id": self._alarm_remaining_friendly_object_id(alarm_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._alarm_remaining_friendly_state_topic(alarm_id),
                "icon": "mdi:account-voice",
                "device": self._alarm_device(alarm, alarm_id),
            }
            next_day_payload = {
                "name": "07c Next Day",
                "unique_id": self._alarm_next_day_object_id(alarm_id),
                "object_id": self._alarm_next_day_object_id(alarm_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._alarm_next_day_state_topic(alarm_id),
                "icon": "mdi:calendar-today",
                "device": self._alarm_device(alarm, alarm_id),
            }
            label_payload = {
                "name": "01 Label",
                "unique_id": self._alarm_label_object_id(alarm_id),
                "object_id": self._alarm_label_object_id(alarm_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._alarm_label_state_topic(alarm_id),
                "command_topic": self._alarm_label_command_topic(alarm_id),
                "icon": "mdi:form-textbox",
                "device": self._alarm_device(alarm, alarm_id),
            }
            time_payload = {
                "name": "02 Time",
                "unique_id": self._alarm_time_object_id(alarm_id),
                "object_id": self._alarm_time_object_id(alarm_id),
                "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                "payload_available": "true",
                "payload_not_available": "false",
                "state_topic": self._alarm_time_state_topic(alarm_id),
                "command_topic": self._alarm_time_command_topic(alarm_id),
                "icon": "mdi:clock-time-four-outline",
                "pattern": "^([01]\\d|2[0-3]):[0-5]\\d(:[0-5]\\d)?$",
                "mode": "text",
                "device": self._alarm_device(alarm, alarm_id),
            }
            weekday_switch_payloads = []
            for wd in range(7):
                weekday_switch_payloads.append({
                    "name": f"04{wd + 1} {_WEEKDAY_NAMES[wd]}",
                    "unique_id": self._alarm_weekday_object_id(alarm_id, wd),
                    "object_id": self._alarm_weekday_object_id(alarm_id, wd),
                    "availability_topic": f"{self._config.mqtt_topic_prefix}/state/online",
                    "payload_available": "true",
                    "payload_not_available": "false",
                    "state_topic": self._alarm_weekday_state_topic(alarm_id, wd),
                    "command_topic": self._alarm_weekday_command_topic(alarm_id, wd),
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "state_on": "ON",
                    "state_off": "OFF",
                    "icon": "mdi:calendar-week",
                    "device": self._alarm_device(alarm, alarm_id),
                })
            self._mqtt.publish(self._alarm_discovery_topic(alarm_id), config_payload, retain=True)
            self._mqtt.publish(self._alarm_remove_discovery_topic(alarm_id), remove_payload, retain=True)
            self._mqtt.publish(self._alarm_snooze_discovery_topic(alarm_id), snooze_payload, retain=True)
            self._mqtt.publish(self._alarm_dismiss_discovery_topic(alarm_id), dismiss_payload, retain=True)
            self._mqtt.publish(self._alarm_status_discovery_topic(alarm_id), status_payload, retain=True)
            self._mqtt.publish(self._alarm_eta_discovery_topic_legacy(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_remaining_discovery_topic(alarm_id), remaining_payload, retain=True)
            self._mqtt.publish(self._alarm_remaining_friendly_discovery_topic(alarm_id), remaining_friendly_payload, retain=True)
            self._mqtt.publish(self._alarm_next_day_discovery_topic(alarm_id), next_day_payload, retain=True)
            self._mqtt.publish(self._alarm_kind_discovery_topic_legacy(alarm_id), "", retain=True)
            # Recurring is derived from weekday selection and is no longer user-configurable.
            self._mqtt.publish(self._alarm_recurring_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_label_discovery_topic(alarm_id), label_payload, retain=True)
            self._mqtt.publish(self._alarm_time_discovery_topic_legacy_time(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_discovery_topic_time_picker(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_discovery_topic(alarm_id), time_payload, retain=True)
            self._mqtt.publish(self._alarm_time_set_discovery_topic_legacy_text(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_status_text_discovery_topic_legacy_text(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_set_discovery_topic_legacy_sensor(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_status_text_discovery_topic_legacy_sensor(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_set_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_status_text_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_weekdays_discovery_topic(alarm_id), "", retain=True)
            for wd, wd_payload in enumerate(weekday_switch_payloads):
                self._mqtt.publish(self._alarm_weekday_discovery_topic(alarm_id, wd), wd_payload, retain=True)
            self._mqtt.publish(self._alarm_enabled_state_topic(alarm_id), "ON" if alarm.get("enabled", True) else "OFF", retain=True)
            self._mqtt.publish(
                self._alarm_status_state_topic(alarm_id),
                str(alarm.get("status_normalized") or self._normalized_alarm_status_fallback(alarm, str(alarm.get("status", "inactive")))),
                retain=True,
            )
            recurring_value = "ON" if bool(alarm.get("weekdays", [])) else "OFF"
            self._mqtt.publish(self._alarm_recurring_state_topic(alarm_id), recurring_value, retain=True)
            self._mqtt.publish(self._alarm_kind_state_topic_legacy(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_label_state_topic(alarm_id), str(alarm.get("label", "Alarm")), retain=True)
            self._mqtt.publish(self._alarm_time_state_topic(alarm_id), self._alarm_time_entity_value(alarm), retain=True)
            weekdays_set = {int(d) for d in alarm.get("weekdays", [])}
            for wd in range(7):
                self._mqtt.publish(self._alarm_weekday_state_topic(alarm_id, wd), "ON" if wd in weekdays_set else "OFF", retain=True)
            self._mqtt.publish(
                self._alarm_remaining_state_topic(alarm_id),
                self._alarm_eta_state(alarm),
                retain=True,
            )
            self._mqtt.publish(
                self._alarm_remaining_friendly_state_topic(alarm_id),
                self._alarm_eta_friendly_state(alarm),
                retain=True,
            )
            self._mqtt.publish(
                self._alarm_next_day_state_topic(alarm_id),
                self._alarm_next_day_state(alarm),
                retain=True,
            )
            self._mqtt.publish(self._alarm_eta_state_topic_legacy(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_attributes_topic(alarm_id), alarm, retain=True)

        removed_ids = self._published_alarm_entities - current_ids
        for alarm_id in removed_ids:
            self._mqtt.publish(self._alarm_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_remove_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_snooze_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_dismiss_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_status_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_eta_discovery_topic_legacy(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_remaining_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_remaining_friendly_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_next_day_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_kind_discovery_topic_legacy(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_label_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_discovery_topic_legacy_time(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_discovery_topic_time_picker(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_set_discovery_topic_legacy_text(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_status_text_discovery_topic_legacy_text(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_set_discovery_topic_legacy_sensor(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_status_text_discovery_topic_legacy_sensor(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_set_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_status_text_discovery_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_weekdays_discovery_topic(alarm_id), "", retain=True)
            for wd in range(7):
                self._mqtt.publish(self._alarm_weekday_discovery_topic(alarm_id, wd), "", retain=True)
            self._mqtt.publish(self._alarm_enabled_state_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_status_state_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_recurring_state_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_kind_state_topic_legacy(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_label_state_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_time_state_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_weekdays_state_topic(alarm_id), "", retain=True)
            for wd in range(7):
                self._mqtt.publish(self._alarm_weekday_state_topic(alarm_id, wd), "", retain=True)
            self._mqtt.publish(self._alarm_remaining_state_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_remaining_friendly_state_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_next_day_state_topic(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_eta_state_topic_legacy(alarm_id), "", retain=True)
            self._mqtt.publish(self._alarm_attributes_topic(alarm_id), "", retain=True)

        self._published_alarm_entities = current_ids

    def _alarm_remaining_seconds(self, alarm: dict) -> Optional[int]:
        status = str(alarm.get("status", "inactive")).strip().lower()
        if status == "ringing":
            return 0
        if status == "snoozed":
            raw_snoozed_until = alarm.get("snoozed_until")
            if not raw_snoozed_until:
                return 0
            try:
                snoozed_until = datetime.fromisoformat(str(raw_snoozed_until).replace("Z", "+00:00"))
                if snoozed_until.tzinfo is None:
                    snoozed_until = snoozed_until.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                remaining_seconds = int((snoozed_until.astimezone(timezone.utc) - now_utc).total_seconds())
                return max(0, remaining_seconds)
            except (TypeError, ValueError):
                return 0
        if not alarm.get("enabled", True):
            return None

        next_trigger = self._next_alarm_trigger_utc(alarm)
        if next_trigger is None:
            return None

        now_utc = datetime.now(timezone.utc)
        remaining_seconds = int((next_trigger - now_utc).total_seconds())
        return max(0, remaining_seconds)

    def _alarm_eta_state(self, alarm: dict) -> str:
        remaining_seconds = self._alarm_remaining_seconds(alarm)
        if remaining_seconds is None:
            return ""

        days, rem_seconds = divmod(remaining_seconds, 24 * 3600)
        hours, rem_seconds = divmod(rem_seconds, 3600)
        minutes, seconds = divmod(rem_seconds, 60)
        return f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _alarm_eta_friendly_state(self, alarm: dict) -> str:
        return duration_to_speech(self._alarm_remaining_seconds(alarm))

    def _alarm_next_day_state(self, alarm: dict) -> str:
        return remaining_to_day_phrase(self._alarm_remaining_seconds(alarm), now=datetime.now(self._tz))

    def _next_alarm_trigger_utc(self, alarm: dict) -> Optional[datetime]:
        now_utc = datetime.now(timezone.utc)
        time_str = str(alarm.get("time", ""))
        if ":" not in time_str:
            return None
        hour, minute = map(int, time_str.split(":", 1))

        now_local = now_utc.astimezone(self._tz)
        recurring = bool(alarm.get("weekdays") or [])

        if not recurring and alarm.get("last_triggered_date") is not None:
            return None

        raw_weekdays = alarm.get("weekdays") or []
        weekdays = {int(day) for day in raw_weekdays if 0 <= int(day) <= 6}
        if recurring and not weekdays:
            return None
        if not recurring and not weekdays:
            weekdays = set(range(7))

        for day_offset in range(8):
            target_date = now_local.date() + timedelta(days=day_offset)
            if target_date.weekday() not in weekdays:
                continue
            if recurring and day_offset == 0 and alarm.get("last_triggered_date") == target_date.isoformat():
                continue

            target_local = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                hour,
                minute,
                0,
                tzinfo=self._tz,
            )
            target_utc = target_local.astimezone(timezone.utc)
            if target_utc > now_utc:
                return target_utc
        return None

    @staticmethod
    def _format_eta_duration(total_seconds: int) -> str:
        total_minutes = max(0, total_seconds // 60)
        days, rem_minutes = divmod(total_minutes, 24 * 60)
        hours, minutes = divmod(rem_minutes, 60)

        parts: list[str] = []
        if days:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes and not days:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

        if not parts:
            return "less than a minute"
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        return f"{parts[0]}, {parts[1]} and {parts[2]}"

    @staticmethod
    def _words_to_number(text: str) -> Optional[float]:
        raw = str(text).strip().lower()
        if raw == "":
            return None

        try:
            return float(raw)
        except ValueError:
            pass

        # Handle "one and a half", "two and half", etc.
        half_match = re.fullmatch(r"(.+?)\s+and\s+(?:a\s+)?half", raw)
        if half_match:
            base = Daemon._words_to_number(half_match.group(1))
            if base is None:
                return None
            return base + 0.5

        if raw in {"half", "a half", "an half"}:
            return 0.5

        unit_words = {
            "zero": 0,
            "a": 1,
            "an": 1,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
        }
        tens_words = {
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "sixty": 60,
            "seventy": 70,
            "eighty": 80,
            "ninety": 90,
        }

        tokens = [t for t in re.split(r"[\s-]+", raw) if t and t != "and"]
        if not tokens:
            return None

        total = 0.0
        current = 0.0
        for tok in tokens:
            if tok in unit_words:
                current += unit_words[tok]
            elif tok in tens_words:
                current += tens_words[tok]
            elif tok == "hundred":
                current = max(1.0, current) * 100.0
            elif tok == "half":
                current += 0.5
            else:
                return None

        total += current
        return total

    @classmethod
    def _parse_duration_seconds(cls, payload: dict, *, default_seconds: int = 300) -> int:
        raw_seconds = payload.get("duration_seconds")
        if raw_seconds is not None:
            seconds = int(raw_seconds)
            if seconds >= 0:
                return seconds

        raw_text = payload.get("duration_text")
        if raw_text is None:
            raw_text = payload.get("minutes")

        if raw_text is None:
            return default_seconds

        text = str(raw_text).strip().lower()
        if text == "":
            return default_seconds

        unit_seconds = {
            "d": 86400,
            "day": 86400,
            "days": 86400,
            "h": 3600,
            "hr": 3600,
            "hrs": 3600,
            "hour": 3600,
            "hours": 3600,
            "m": 60,
            "min": 60,
            "mins": 60,
            "minute": 60,
            "minutes": 60,
            "s": 1,
            "sec": 1,
            "secs": 1,
            "second": 1,
            "seconds": 1,
        }

        total_seconds = 0.0
        pattern = re.compile(
            r"(?P<value>[a-z0-9\.\-\s]+?)\s*(?P<unit>days?|d|hours?|hrs?|hr|h|minutes?|mins?|min|m|seconds?|secs?|sec|s)\b"
        )

        for match in pattern.finditer(text):
            value_text = match.group("value").strip()
            value_text = re.sub(r"^and\s+", "", value_text)
            value = cls._words_to_number(value_text)
            if value is None:
                continue
            unit = match.group("unit")
            total_seconds += value * unit_seconds[unit]

        if total_seconds <= 0:
            # Backward-compatible fallback: plain number means minutes.
            plain = cls._words_to_number(text)
            if plain is not None and plain > 0:
                total_seconds = plain * 60

        seconds_int = int(round(total_seconds))
        if seconds_int < 0:
            raise ValueError("duration must be at least 0 seconds")
        return seconds_int

    # ------------------------------------------------------------------ MQTT command dispatch

    @staticmethod
    def _extract_request_id(payload: object) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        raw = payload.get("request_id")
        if raw is None:
            return None
        request_id = str(raw).strip()
        return request_id if request_id else None

    def _handle_command(self, cmd: str, payload: object) -> None:
        logger.debug("Command received: %s %s", cmd, payload)
        self._active_request_id = self._extract_request_id(payload)
        try:
            if self._try_handle_alarm_enabled_command(cmd, payload):
                return
            if self._try_handle_alarm_weekday_toggle_command(cmd, payload):
                return
            if self._try_handle_alarm_setting_command(cmd, payload):
                return
            if self._try_handle_timer_setting_command(cmd, payload):
                return
            if self._try_handle_manager_setting_command(cmd, payload):
                return

            handler = {
                "purge_all":      self._cmd_purge_all,
                "alarm/new":      self._cmd_alarm_new,
                "alarm/set":      self._cmd_alarm_set,
                "alarm/update":   self._cmd_alarm_update,
                "alarm/remove":   self._cmd_alarm_remove,
                "alarm/snooze":   self._cmd_alarm_snooze,
                "alarm/dismiss":  self._cmd_alarm_dismiss,
                "timer/new":      self._cmd_timer_new,
                "timer/set":      self._cmd_timer_set,
                "timer/update":   self._cmd_timer_update,
                "timer/cancel":   self._cmd_timer_cancel,
                "timer/remove":   self._cmd_timer_remove,
                "timer/snooze":   self._cmd_timer_snooze,
                "timer/add_time": self._cmd_timer_add_time,
                "timer/pause":    self._cmd_timer_pause,
                "timer/resume":   self._cmd_timer_resume,
                "timer/reset":    self._cmd_timer_reset,
                "timer/activate": self._cmd_timer_activate,
                "timer/dismiss":  self._cmd_timer_dismiss,
                "state/request":  self._cmd_state_request,
            }.get(cmd)

            if handler is None:
                self._cmd_unknown(payload)
                return

            if not isinstance(payload, dict):
                raise TypeError("Command payload must be a JSON object")

            handler(payload)
        except (KeyError, ValueError, TypeError) as exc:
            self._ack(cmd, False, f"Invalid payload: {exc}")
            self._mqtt.publish_state("error", {"command": cmd, "error": str(exc)}, retain=False)
        except Exception as exc:
            logger.exception("Error handling command %s", cmd)
            self._ack(cmd, False, str(exc))
            self._mqtt.publish_state("error", {"command": cmd, "error": str(exc)}, retain=False)
        finally:
            self._active_request_id = None

    def _try_handle_alarm_enabled_command(self, cmd: str, payload: object) -> bool:
        parts = cmd.split("/")
        if len(parts) != 4 or parts[0] != "alarm" or parts[2] != "enabled" or parts[3] != "set":
            return False

        alarm_id = parts[1]
        if isinstance(payload, bool):
            enabled = payload
        elif isinstance(payload, str):
            normalized = payload.strip().upper()
            if normalized in {"ON", "TRUE", "1"}:
                enabled = True
            elif normalized in {"OFF", "FALSE", "0"}:
                enabled = False
            else:
                raise ValueError(f"Unsupported enabled payload: {payload!r}")
        else:
            raise TypeError("Alarm enabled payload must be ON/OFF or boolean")

        updated = self._scheduler.update_alarm(alarm_id, enabled=enabled)
        if updated:
            self._ack(cmd, True, f"Alarm {'enabled' if enabled else 'disabled'}: {alarm_id}")
        else:
            self._ack(cmd, False, f"Alarm not found: {alarm_id}")
        return True

    def _try_handle_alarm_setting_command(self, cmd: str, payload: object) -> bool:
        parts = cmd.split("/")
        if len(parts) != 4 or parts[0] != "alarm" or parts[3] != "set":
            return False

        alarm_id = parts[1]
        field = parts[2]

        if field == "time":
            if not isinstance(payload, str):
                raise TypeError("Alarm time payload must be HH:MM string")
            updated = self._scheduler.set_alarm(alarm_id, time=payload)
            if updated:
                self._ack(cmd, True, f"Alarm time updated: {alarm_id}")
            else:
                self._ack(cmd, False, f"Alarm not found: {alarm_id}")
            return True

        if field == "label":
            if not isinstance(payload, str):
                raise TypeError("Alarm label payload must be a string")
            updated = self._scheduler.set_alarm(alarm_id, label=payload)
            if updated:
                self._ack(cmd, True, f"Alarm label updated: {alarm_id}")
            else:
                self._ack(cmd, False, f"Alarm not found: {alarm_id}")
            return True

        if field == "weekdays":
            if not isinstance(payload, str):
                raise TypeError("Alarm weekdays payload must be CSV string")
            raw = payload.strip()
            if raw == "":
                weekdays: list[int] = []
            else:
                weekdays = [int(part.strip()) for part in raw.split(",") if part.strip() != ""]
            updated = self._scheduler.set_alarm(alarm_id, weekdays=weekdays)
            if updated:
                self._ack(cmd, True, f"Alarm weekdays updated: {alarm_id}")
            else:
                self._ack(cmd, False, f"Alarm not found: {alarm_id}")
            return True

        if field == "recurring":
            self._ack(cmd, False, "Alarm recurring is derived from weekdays and cannot be set directly")
            return True

        return False

    def _try_handle_alarm_weekday_toggle_command(self, cmd: str, payload: object) -> bool:
        parts = cmd.split("/")
        if len(parts) != 5 or parts[0] != "alarm" or parts[2] != "weekday" or parts[4] != "set":
            return False

        alarm_id = parts[1]
        weekday = int(parts[3])
        if not 0 <= weekday <= 6:
            raise ValueError("weekday must be in range 0..6")

        if isinstance(payload, bool):
            enabled = payload
        elif isinstance(payload, str):
            normalized = payload.strip().upper()
            if normalized in {"ON", "TRUE", "1"}:
                enabled = True
            elif normalized in {"OFF", "FALSE", "0"}:
                enabled = False
            else:
                raise ValueError(f"Unsupported weekday payload: {payload!r}")
        else:
            raise TypeError("Alarm weekday payload must be ON/OFF or boolean")

        alarms = self._scheduler.full_state().get("alarms", [])
        alarm = next((a for a in alarms if str(a.get("id")) == alarm_id), None)
        if alarm is None:
            self._ack(cmd, False, f"Alarm not found: {alarm_id}")
            return True

        current_days = sorted({int(d) for d in alarm.get("weekdays", [])})
        if enabled:
            if weekday not in current_days:
                current_days.append(weekday)
                current_days.sort()
        else:
            current_days = [d for d in current_days if d != weekday]

        updated = self._scheduler.set_alarm(alarm_id, weekdays=current_days)
        if updated:
            self._ack(cmd, True, f"Alarm weekday updated: {alarm_id}")
        else:
            self._ack(cmd, False, f"Alarm not found: {alarm_id}")
        return True

    def _try_handle_timer_setting_command(self, cmd: str, payload: object) -> bool:
        parts = cmd.split("/")
        if len(parts) != 4 or parts[0] != "timer" or parts[3] != "set":
            return False

        timer_id = parts[1]
        field = parts[2]

        if field == "label":
            if not isinstance(payload, str):
                raise TypeError("Timer label payload must be a string")
            if self._scheduler.update_timer(timer_id, label=payload):
                self._ack(cmd, True, f"Timer label updated: {timer_id}")
            else:
                self._ack(cmd, False, f"Timer not found: {timer_id}")
            return True

        if field == "duration":
            if isinstance(payload, (int, float)):
                duration_seconds = self._parse_duration_seconds({"duration_seconds": int(payload)}, default_seconds=300)
            elif isinstance(payload, str):
                text = payload.strip()
                if text == "":
                    raise ValueError("Timer duration payload must not be empty")
                if ":" in text:
                    parts = [int(p) for p in text.split(":")]
                    if len(parts) == 2:
                        dd, hh, mm, ss = 0, 0, parts[0], parts[1]
                    elif len(parts) == 3:
                        dd, hh, mm, ss = 0, parts[0], parts[1], parts[2]
                    elif len(parts) == 4:
                        dd, hh, mm, ss = parts
                    else:
                        raise ValueError("Timer duration must be DD:HH:MM:SS, HH:MM:SS, or MM:SS")
                    duration_seconds = dd * 86400 + hh * 3600 + mm * 60 + ss
                    if duration_seconds < 0:
                        raise ValueError("duration_seconds must be ≥ 0")
                else:
                    duration_seconds = self._parse_duration_seconds({"duration_text": text}, default_seconds=300)
            else:
                raise TypeError("Timer duration payload must be numeric, DD:HH:MM:SS/HH:MM:SS/MM:SS, or duration text")

            if self._scheduler.update_timer(timer_id, duration_seconds=duration_seconds):
                self._ack(cmd, True, f"Timer duration updated: {timer_id}")
            else:
                self._ack(cmd, False, f"Timer not found: {timer_id}")
            return True

        if field == "temporary":
            if isinstance(payload, bool):
                temporary = payload
            elif isinstance(payload, str):
                normalized = payload.strip().upper()
                if normalized in {"ON", "TRUE", "1"}:
                    temporary = True
                elif normalized in {"OFF", "FALSE", "0"}:
                    temporary = False
                else:
                    raise ValueError(f"Unsupported temporary payload: {payload!r}")
            else:
                raise TypeError("Timer temporary payload must be ON/OFF or boolean")

            if self._scheduler.update_timer(timer_id, temporary=temporary):
                self._ack(cmd, True, f"Timer temporary updated: {timer_id}")
            else:
                self._ack(cmd, False, f"Timer not found: {timer_id}")
            return True

        return False

    def _try_handle_manager_setting_command(self, cmd: str, payload: object) -> bool:
        if cmd != "settings/timer_add_seconds/set":
            return False

        if isinstance(payload, (int, float)):
            seconds = int(payload)
        elif isinstance(payload, str):
            raw = payload.strip()
            if raw == "":
                raise ValueError("timer_add_seconds must not be empty")
            seconds = int(raw)
        else:
            raise TypeError("timer_add_seconds payload must be numeric")

        if seconds < 1:
            raise ValueError("timer_add_seconds must be >= 1")

        self._timer_add_seconds = seconds
        self._mqtt.publish(self._manager_timer_add_seconds_state_topic(), str(self._timer_add_seconds), retain=True)
        self._ack(cmd, True, f"Timer add-time updated: {self._timer_add_seconds}s")
        return True

    def _ack(self, cmd: str, success: bool, message: str = "") -> None:
        payload = {"command": cmd, "success": success, "message": message}
        if self._active_request_id is not None:
            payload["request_id"] = self._active_request_id
        self._mqtt.publish_state(
            "command_result",
            payload,
            retain=False,
        )

    # ------------------------------------------------------------------ individual handlers

    def _cmd_purge_all(self, payload: dict) -> None:
        removed_alarms, removed_timers = self._scheduler.purge_all()

        self._ack(
            "purge_all",
            True,
            f"Purged {removed_alarms} alarm(s) and {removed_timers} timer(s)",
        )

    def _cmd_alarm_new(self, payload: dict) -> None:
        """Create a new alarm. Payload can include:
        - time: "HH:MM" string (default: now+1min)
        - label: string (default: "")
        - enabled: bool (default: true)
        - temporary: bool (default: false)
        - weekdays: [0..6] list (default: empty => one-off)
        """
        now_local = datetime.now(self._tz)
        default_time = (now_local + timedelta(minutes=1)).replace(second=0, microsecond=0).strftime("%H:%M")

        time_str = payload.get("time", default_time)
        label = payload.get("label", "")
        enabled = bool(payload.get("enabled", True))
        temporary = bool(payload.get("temporary", False))
        weekdays_raw = payload.get("weekdays")
        weekdays = [int(d) for d in weekdays_raw] if weekdays_raw is not None else []
        if not all(0 <= d <= 6 for d in weekdays):
            raise ValueError("weekdays must be integers 0-6")

        alarm = self._scheduler.add_alarm(
            str(time_str),
            str(label),
            enabled=enabled,
            temporary=temporary,
            weekdays=weekdays,
        )
        status = "enabled" if enabled else "disabled"
        temp_suffix = " temporary" if temporary else ""
        kind = "Recurring alarm" if weekdays else "Alarm"
        self._ack("alarm/new", True, f"{kind}{temp_suffix} created {status}: {alarm.id}")

    def _cmd_alarm_set(self, payload: dict) -> None:
        label = str(payload.get("label", "Alarm"))
        raw_time = payload["time"]
        time_str = str(raw_time)
        if "T" in time_str:
            dt = datetime.fromisoformat(time_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=self._tz)
            time_str = dt.astimezone(self._tz).strftime("%H:%M")

        weekdays_raw = payload.get("weekdays")
        temporary = bool(payload.get("temporary", False))
        weekdays = [int(d) for d in weekdays_raw] if weekdays_raw is not None else []
        if not all(0 <= d <= 6 for d in weekdays):
            raise ValueError("weekdays must be integers 0-6")

        alarm = self._scheduler.add_alarm(
            time_str,
            label,
            enabled=True,
            temporary=temporary,
            weekdays=weekdays,
        )
        if weekdays:
            self._ack("alarm/set", True, f"Recurring alarm created enabled: {alarm.id}")
        else:
            self._ack("alarm/set", True, f"One-off alarm created enabled: {alarm.id}")

    def _cmd_alarm_update(self, payload: dict) -> None:
        alarm_id = str(payload["id"])
        updated = self._scheduler.set_alarm(
            alarm_id,
            time=payload.get("time"),
            weekdays=payload.get("weekdays"),
            label=payload.get("label"),
            enabled=payload.get("enabled"),
        )
        if updated:
            self._ack("alarm/update", True, f"Alarm updated: {alarm_id}")
        else:
            self._ack("alarm/update", False, f"Alarm not found: {alarm_id}")

    def _cmd_alarm_remove(self, payload: dict) -> None:
        alarm_id = str(payload["id"])
        if self._scheduler.remove_alarm(alarm_id):
            self._ack("alarm/remove", True, f"Alarm removed: {alarm_id}")
        else:
            self._ack("alarm/remove", False, f"Alarm not found: {alarm_id}")

    def _cmd_alarm_snooze(self, payload: dict) -> None:
        alarm_id: Optional[str] = payload.get("id")
        if alarm_id is not None:
            alarm_id = str(alarm_id)
        minutes = int(payload.get("minutes", self._config.default_snooze_minutes))
        if minutes < 1:
            raise ValueError("minutes must be ≥ 1")
        snoozed = self._scheduler.snooze(minutes, alarm_id=alarm_id)
        if snoozed:
            self._ack("alarm/snooze", True, f"Snoozed {len(snoozed)} alarm(s) for {minutes} min")
        else:
            self._ack("alarm/snooze", False, "No ringing alarms to snooze")

    def _cmd_alarm_dismiss(self, payload: dict) -> None:
        alarm_id: Optional[str] = payload.get("id")
        if alarm_id is not None:
            alarm_id = str(alarm_id)
        dismissed = self._scheduler.dismiss(alarm_id)
        if dismissed:
            self._ack("alarm/dismiss", True, f"Dismissed {len(dismissed)} alarm(s)")
        else:
            self._ack("alarm/dismiss", False, "No alarms to dismiss")

    def _cmd_timer_new(self, payload: dict) -> None:
        """Create a new timer. Payload can include:
        - duration_seconds: int (default: 0)
        - label: string (default: "")
        - active: bool (default: true when payload is non-empty, else false)
        - temporary: bool (default: true)
        """
        duration = self._parse_duration_seconds(payload, default_seconds=0)
        
        label = payload.get("label", "")
        is_active = bool(payload.get("active", payload.get("running", bool(payload))))
        temporary = bool(payload.get("temporary", True))
        initial_status = "active" if is_active else "inactive"
        timer = self._scheduler.add_timer(
            duration,
            str(label),
            initial_status=initial_status,
            temporary=temporary,
        )
        temp_suffix = " temporary" if temporary else ""
        self._ack("timer/new", True, f"Timer created {initial_status}{temp_suffix}: {timer.id}")

    def _cmd_timer_set(self, payload: dict) -> None:
        duration = self._parse_duration_seconds(payload, default_seconds=300)
        label = str(payload.get("label", ""))
        temporary = bool(payload.get("temporary", True))
        timer = self._scheduler.add_timer(duration, label, initial_status="inactive", temporary=temporary)
        temp_suffix = " temporary" if temporary else ""
        self._ack("timer/set", True, f"Timer created inactive{temp_suffix}: {timer.id}")

    def _publish_timer_runtime_state(self, state: dict) -> None:
        timers: list[dict] = state.get("timers", [])
        for timer in timers:
            timer_id = str(timer.get("id"))
            self._mqtt.publish(self._timer_label_state_topic(timer_id), str(timer.get("label", "Timer")), retain=True)
            self._mqtt.publish(self._timer_duration_state_topic(timer_id), self._timer_duration_entity_value(timer), retain=True)
            self._mqtt.publish(self._timer_temporary_state_topic(timer_id), "ON" if bool(timer.get("temporary", False)) else "OFF", retain=True)
            self._mqtt.publish(
                self._timer_status_state_topic(timer_id),
                str(timer.get("status_normalized") or self._normalized_timer_status_fallback(str(timer.get("status", "inactive")))),
                retain=True,
            )
            self._mqtt.publish(self._timer_remaining_state_topic(timer_id), self._timer_remaining_entity_value(timer), retain=True)
            self._mqtt.publish(self._timer_remaining_friendly_state_topic(timer_id), self._timer_remaining_friendly_entity_value(timer), retain=True)
            self._mqtt.publish(self._timer_attributes_topic(timer_id), timer, retain=True)

    def _publish_alarm_runtime_state(self, state: dict) -> None:
        alarms: list[dict] = state.get("alarms", [])
        for alarm in alarms:
            alarm_id = str(alarm.get("id"))
            self._mqtt.publish(
                self._alarm_remaining_state_topic(alarm_id),
                self._alarm_eta_state(alarm),
                retain=True,
            )
            self._mqtt.publish(
                self._alarm_remaining_friendly_state_topic(alarm_id),
                self._alarm_eta_friendly_state(alarm),
                retain=True,
            )
            self._mqtt.publish(
                self._alarm_next_day_state_topic(alarm_id),
                self._alarm_next_day_state(alarm),
                retain=True,
            )

    def _cmd_timer_update(self, payload: dict) -> None:
        timer_id = str(payload["id"])
        updates: dict[str, object] = {}
        if "duration_seconds" in payload:
            updates["duration_seconds"] = int(payload["duration_seconds"])
        if "label" in payload:
            updates["label"] = str(payload["label"])
        if "temporary" in payload:
            updates["temporary"] = bool(payload["temporary"])
        if not updates:
            raise ValueError("No timer update fields provided")
        if self._scheduler.update_timer(timer_id, **updates):
            self._ack("timer/update", True, f"Timer updated: {timer_id}")
        else:
            self._ack("timer/update", False, f"Timer not found: {timer_id}")

    def _cmd_timer_cancel(self, payload: dict) -> None:
        timer_id = str(payload["id"])
        if self._scheduler.cancel_timer(timer_id):
            self._ack("timer/cancel", True, f"Timer cancelled: {timer_id}")
        else:
            self._ack("timer/cancel", False, f"Timer not found: {timer_id}")

    def _cmd_timer_remove(self, payload: dict) -> None:
        timer_id = str(payload["id"])
        if self._scheduler.cancel_timer(timer_id):
            self._ack("timer/remove", True, f"Timer removed: {timer_id}")
        else:
            self._ack("timer/remove", False, f"Timer not found: {timer_id}")

    def _cmd_timer_add_time(self, payload: dict, ack_command: str = "timer/add_time") -> None:
        timer_id_raw = payload.get("id")
        timer_id = str(timer_id_raw) if timer_id_raw is not None else None
        seconds_raw = payload.get("seconds")
        if seconds_raw is None:
            seconds_raw = payload.get("duration_seconds")
        minutes_raw = payload.get("minutes")
        duration_text_raw = payload.get("duration_text")
        seconds_to_add = self._timer_add_seconds
        if seconds_raw is not None:
            seconds_to_add = int(seconds_raw)
        elif minutes_raw is not None:
            seconds_to_add = int(minutes_raw) * 60
        elif duration_text_raw is not None:
            seconds_to_add = self._parse_duration_seconds({"duration_text": duration_text_raw}, default_seconds=self._timer_add_seconds)
        if seconds_to_add < 1:
            raise ValueError("seconds must be >= 1")

        if self._scheduler.add_time_timer(timer_id, seconds=seconds_to_add):
            if timer_id is None:
                self._ack(ack_command, True, "Added time to timer(s)")
            else:
                self._ack(ack_command, True, f"Added {seconds_to_add}s: {timer_id}")
        else:
            if timer_id is None:
                self._ack(ack_command, False, "No active, paused, or ringing timers to add time")
            else:
                self._ack(ack_command, False, f"Timer is not active, paused, or ringing: {timer_id}")

    def _cmd_timer_snooze(self, payload: dict) -> None:
        self._cmd_timer_add_time(payload, ack_command="timer/snooze")

    def _cmd_timer_pause(self, payload: dict) -> None:
        timer_id_raw = payload.get("id")
        timer_id = str(timer_id_raw) if timer_id_raw is not None else None
        if self._scheduler.pause_timer(timer_id):
            if timer_id is None:
                self._ack("timer/pause", True, "Paused active timer(s)")
            else:
                self._ack("timer/pause", True, f"Timer paused: {timer_id}")
        else:
            if timer_id is None:
                self._ack("timer/pause", False, "No active timers to pause")
            else:
                self._ack("timer/pause", False, f"Timer is not active: {timer_id}")

    def _cmd_timer_resume(self, payload: dict) -> None:
        timer_id_raw = payload.get("id")
        timer_id = str(timer_id_raw) if timer_id_raw is not None else None
        if self._scheduler.resume_timer(timer_id):
            if timer_id is None:
                self._ack("timer/resume", True, "Resumed paused timer(s)")
            else:
                self._ack("timer/resume", True, f"Timer resumed: {timer_id}")
        else:
            if timer_id is None:
                self._ack("timer/resume", False, "No paused timers to resume")
            else:
                self._ack("timer/resume", False, f"Timer is not paused: {timer_id}")

    def _cmd_timer_activate(self, payload: dict) -> None:
        timer_id_raw = payload.get("id")
        timer_id = str(timer_id_raw) if timer_id_raw is not None else None
        if self._scheduler.activate_timer(timer_id):
            if timer_id is None:
                self._ack("timer/activate", True, "Started or restarted timer(s)")
            else:
                self._ack("timer/activate", True, f"Timer started or restarted: {timer_id}")
        else:
            if timer_id is None:
                self._ack("timer/activate", False, "No timers available to start or restart")
            else:
                self._ack("timer/activate", False, f"Timer cannot be started or restarted: {timer_id}")

    def _cmd_timer_reset(self, payload: dict) -> None:
        timer_id_raw = payload.get("id")
        timer_id = str(timer_id_raw) if timer_id_raw is not None else None
        if self._scheduler.reset_timer(timer_id):
            if timer_id is None:
                self._ack("timer/reset", True, "Reset active, paused, or ringing timer(s)")
            else:
                self._ack("timer/reset", True, f"Timer reset: {timer_id}")
        else:
            if timer_id is None:
                self._ack("timer/reset", False, "No active, paused, or ringing timers to reset")
            else:
                self._ack("timer/reset", False, f"Timer is not active, paused, or ringing: {timer_id}")

    def _cmd_timer_dismiss(self, payload: dict) -> None:
        timer_id_raw = payload.get("id")
        timer_id = str(timer_id_raw) if timer_id_raw is not None else None
        if self._scheduler.dismiss_timer(timer_id):
            if timer_id is None:
                self._ack("timer/dismiss", True, "Dismissed timer(s)")
            else:
                self._ack("timer/dismiss", True, f"Timer dismissed: {timer_id}")
        else:
            if timer_id is None:
                self._ack("timer/dismiss", False, "No active, paused, or ringing timers to dismiss")
            else:
                self._ack("timer/dismiss", False, f"Timer is not active, paused, or ringing: {timer_id}")

    def _cmd_state_request(self, payload: dict) -> None:
        self._publish_all_state()

    def _cmd_unknown(self, payload: object) -> None:
        self._ack("unknown", False, "Unknown command")

    # ------------------------------------------------------------------ main loop

    def run(self) -> None:
        self._running = True

        def _stop(signum, frame):
            logger.info("Signal %s received — shutting down", signum)
            self._running = False

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        self._mqtt.connect()
        self._publish_all_state()
        logger.info("Snoozefest daemon running (tick=%ss)", self._config.tick_seconds)

        last_heartbeat = 0.0
        last_alarm_countdown_refresh = 0.0
        while self._running:
            self._scheduler.tick()

            loop_state = self._scheduler.full_state()
            self._mqtt.publish_state("ringing_alarm_count", self._ringing_alarm_count(loop_state))
            self._mqtt.publish_state("ringing_timer_count", self._ringing_timer_count(loop_state))

            if self._store.state.alarms:
                self._publish_alarm_runtime_state(loop_state)

            if self._store.state.timers:
                self._publish_timer_runtime_state(loop_state)

            now = time.monotonic()
            if now - last_alarm_countdown_refresh >= _ALARM_COUNTDOWN_REFRESH_INTERVAL:
                self._publish_alarm_entities(self._scheduler.full_state())
                last_alarm_countdown_refresh = now

            if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                ts = self._timestamp_payload(datetime.now(timezone.utc))
                self._mqtt.publish_state(
                    "heartbeat",
                    {
                        "timestamp": ts["utc"],
                        "timestamp_utc": ts["utc"],
                        "timestamp_local": ts["local"],
                        "timestamp_friendly": ts["friendly_local"],
                        "timezone": ts["timezone"],
                    },
                    retain=False,
                )
                last_heartbeat = now

            time.sleep(self._config.tick_seconds)

        self._mqtt.disconnect()
        logger.info("Snoozefest daemon stopped")
