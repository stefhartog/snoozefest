from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models import Alarm, Timer

MAX_ALARMS = 25
MAX_TIMERS = 25


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if s is None:
        return None
    return datetime.fromisoformat(s)


def _dt_str(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


@dataclass
class AppState:
    alarms: List[Alarm]
    timers: List[Timer]


class Store:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._state = AppState([], [])
        self._load()

    # ------------------------------------------------------------------ load

    def _load(self) -> None:
        if not self._path.exists():
            return
        with open(self._path) as f:
            data = json.load(f)
        alarms = data.get("alarms")
        if alarms is None:
            alarms = [
                *[self._decode_oneoff_legacy(o) for o in data.get("oneoffs", [])],
                *[self._decode_recurring_legacy(r) for r in data.get("recurring", [])],
            ]
        decoded_alarms = [self._decode_alarm(a) for a in alarms]

        # Migrate legacy active_alarms runtime entries into the corresponding alarm records.
        for legacy_active in data.get("active_alarms", []):
            alarm_id = str(legacy_active.get("alarm_id"))
            alarm = next((a for a in decoded_alarms if str(a.id) == alarm_id), None)
            if alarm is None:
                continue

            triggered_at = _parse_dt(legacy_active.get("triggered_at"))
            snoozed_until = _parse_dt(legacy_active.get("snoozed_until"))
            now_utc = datetime.now(timezone.utc)

            if triggered_at is not None:
                alarm.triggered_at = triggered_at
            if snoozed_until is not None and snoozed_until > now_utc:
                alarm.status = "snoozed"
                alarm.snoozed_until = snoozed_until
            else:
                alarm.status = "ringing"
                alarm.snoozed_until = None
            alarm.enabled = True

        self._state = AppState(
            alarms=decoded_alarms,
            timers=[self._decode_timer(t) for t in data.get("timers", [])],
        )
        if self._normalize_numeric_ids():
            self.save()

    def _normalize_numeric_ids(self) -> bool:
        """Migrate persisted IDs to compact numeric 1..25 IDs."""
        state = self._state
        changed = False

        if len(state.alarms) > MAX_ALARMS:
            raise ValueError(f"Too many alarms in state ({len(state.alarms)} > {MAX_ALARMS})")

        alarm_map: dict[str, str] = {}
        for idx, alarm in enumerate(state.alarms, start=1):
            new_id = str(idx)
            old_id = str(alarm.id)
            alarm_map[old_id] = new_id
            if old_id != new_id:
                alarm.id = new_id
                changed = True

        if len(state.timers) > MAX_TIMERS:
            raise ValueError(f"Too many timers in state ({len(state.timers)} > {MAX_TIMERS})")

        for idx, timer in enumerate(state.timers, start=1):
            new_id = str(idx)
            old_id = str(timer.id)
            if old_id != new_id:
                timer.id = new_id
                changed = True

        return changed

    @staticmethod
    def _decode_alarm(d: dict) -> Alarm:
        if "weekdays" in d:
            weekdays = [int(day) for day in d.get("weekdays", []) if 0 <= int(day) <= 6]
        else:
            weekdays = [0, 1, 2, 3, 4, 5, 6]
        raw_status = str(d.get("status", "active")).strip().lower()
        if raw_status in {"active", "inactive", "ringing", "snoozed"}:
            status = raw_status
        else:
            status = "active" if d.get("enabled", True) else "inactive"

        if status in {"ringing", "snoozed"}:
            enabled = True
        elif status == "inactive":
            enabled = False
        else:
            enabled = bool(d.get("enabled", True))

        return Alarm(
            id=d["id"],
            time=d["time"],
            label=d["label"],
            enabled=enabled,
            temporary=d.get("temporary", False),
            recurring=d.get("recurring", False),
            weekdays=weekdays,
            last_triggered_date=d.get("last_triggered_date"),
            status=status,
            triggered_at=_parse_dt(d.get("triggered_at")),
            snoozed_until=_parse_dt(d.get("snoozed_until")),
        )

    @staticmethod
    def _decode_oneoff_legacy(d: dict) -> dict:
        dt = datetime.fromisoformat(d["time"])
        return {
            "id": d["id"],
            "time": dt.strftime("%H:%M"),
            "label": d["label"],
            "enabled": d.get("enabled", True),
            "temporary": d.get("temporary", False),
            "recurring": False,
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "last_triggered_date": None,
        }

    @staticmethod
    def _decode_recurring_legacy(d: dict) -> dict:
        weekdays = [int(day) for day in d.get("weekdays", []) if 0 <= int(day) <= 6]
        if not weekdays:
            weekdays = [0, 1, 2, 3, 4, 5, 6]
        return {
            "id": d["id"],
            "time": d["time"],
            "label": d["label"],
            "enabled": d.get("enabled", True),
            "temporary": d.get("temporary", False),
            "recurring": True,
            "weekdays": weekdays,
            "last_triggered_date": d.get("last_triggered_date"),
        }

    @staticmethod
    def _decode_timer(d: dict) -> Timer:
        raw_status = str(d.get("status", "active")).strip().lower()
        if raw_status == "running":
            status = "active"
        elif raw_status == "dismissed":
            status = "inactive"
        elif raw_status in {"active", "inactive", "ringing", "snoozed"}:
            status = raw_status
        else:
            status = "inactive"
        return Timer(
            id=d["id"],
            label=d["label"],
            duration_seconds=d["duration_seconds"],
            started_at=datetime.fromisoformat(d["started_at"]),
            expires_at=datetime.fromisoformat(d["expires_at"]),
            status=status,
            temporary=d.get("temporary", False),
        )

    # ------------------------------------------------------------------ save

    def save(self) -> None:
        data = {
            "alarms": [self._encode_alarm(a) for a in self._state.alarms],
            "timers": [self._encode_timer(t) for t in self._state.timers],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def _encode_alarm(r: Alarm) -> dict:
        return {
            "id": r.id,
            "time": r.time,
            "weekdays": r.weekdays,
            "label": r.label,
            "enabled": r.enabled,
            "temporary": r.temporary,
            "recurring": r.recurring,
            "last_triggered_date": r.last_triggered_date,
            "status": r.status,
            "triggered_at": _dt_str(r.triggered_at),
            "snoozed_until": _dt_str(r.snoozed_until),
        }

    @staticmethod
    def _encode_timer(t: Timer) -> dict:
        return {
            "id": t.id,
            "label": t.label,
            "duration_seconds": t.duration_seconds,
            "started_at": t.started_at.isoformat(),
            "expires_at": t.expires_at.isoformat(),
            "status": t.status,
            "temporary": t.temporary,
        }

    # ------------------------------------------------------------------ accessor

    @property
    def state(self) -> AppState:
        return self._state

    def next_alarm_id(self) -> str:
        used = {int(a.id) for a in self._state.alarms}
        if len(used) >= MAX_ALARMS:
            raise ValueError(f"Maximum alarm count reached ({MAX_ALARMS})")
        for candidate in range(1, MAX_ALARMS + 1):
            if candidate not in used:
                return str(candidate)
        raise ValueError(f"Maximum alarm count reached ({MAX_ALARMS})")

    def next_timer_id(self) -> str:
        used = {int(t.id) for t in self._state.timers}
        if len(used) >= MAX_TIMERS:
            raise ValueError(f"Maximum timer count reached ({MAX_TIMERS})")
        for candidate in range(1, MAX_TIMERS + 1):
            if candidate not in used:
                return str(candidate)
        raise ValueError(f"Maximum timer count reached ({MAX_TIMERS})")
