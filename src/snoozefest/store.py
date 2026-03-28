from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import ActiveAlarm, AlarmOneOff, AlarmRecurring, Timer

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
    oneoffs: List[AlarmOneOff]
    recurring: List[AlarmRecurring]
    timers: List[Timer]
    active_alarms: List[ActiveAlarm]


class Store:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._state = AppState([], [], [], [])
        self._load()

    # ------------------------------------------------------------------ load

    def _load(self) -> None:
        if not self._path.exists():
            return
        with open(self._path) as f:
            data = json.load(f)
        self._state = AppState(
            oneoffs=[self._decode_oneoff(o) for o in data.get("oneoffs", [])],
            recurring=[self._decode_recurring(r) for r in data.get("recurring", [])],
            timers=[self._decode_timer(t) for t in data.get("timers", [])],
            active_alarms=[self._decode_active(a) for a in data.get("active_alarms", [])],
        )
        if self._normalize_numeric_ids():
            self.save()

    def _normalize_numeric_ids(self) -> bool:
        """Migrate persisted IDs to compact numeric 1..25 IDs."""
        state = self._state
        changed = False

        alarms = [*state.oneoffs, *state.recurring]
        if len(alarms) > MAX_ALARMS:
            raise ValueError(f"Too many alarms in state ({len(alarms)} > {MAX_ALARMS})")

        alarm_map: dict[str, str] = {}
        for idx, alarm in enumerate(alarms, start=1):
            new_id = str(idx)
            old_id = str(alarm.id)
            alarm_map[old_id] = new_id
            if old_id != new_id:
                alarm.id = new_id
                changed = True

        for active in state.active_alarms:
            old_id = str(active.alarm_id)
            if old_id in alarm_map and old_id != alarm_map[old_id]:
                active.alarm_id = alarm_map[old_id]
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
    def _decode_oneoff(d: dict) -> AlarmOneOff:
        return AlarmOneOff(
            id=d["id"],
            time=datetime.fromisoformat(d["time"]),
            label=d["label"],
            enabled=d.get("enabled", True),
            temporary=d.get("temporary", False),
        )

    @staticmethod
    def _decode_recurring(d: dict) -> AlarmRecurring:
        return AlarmRecurring(
            id=d["id"],
            time=d["time"],
            weekdays=d["weekdays"],
            label=d["label"],
            enabled=d.get("enabled", True),
            temporary=d.get("temporary", False),
            last_triggered_date=d.get("last_triggered_date"),
        )

    @staticmethod
    def _decode_timer(d: dict) -> Timer:
        return Timer(
            id=d["id"],
            label=d["label"],
            duration_seconds=d["duration_seconds"],
            started_at=datetime.fromisoformat(d["started_at"]),
            expires_at=datetime.fromisoformat(d["expires_at"]),
            status=d.get("status", "running"),
            temporary=d.get("temporary", False),
        )

    @staticmethod
    def _decode_active(d: dict) -> ActiveAlarm:
        return ActiveAlarm(
            alarm_id=d["alarm_id"],
            triggered_at=datetime.fromisoformat(d["triggered_at"]),
            snoozed_until=_parse_dt(d.get("snoozed_until")),
        )

    # ------------------------------------------------------------------ save

    def save(self) -> None:
        data = {
            "oneoffs": [self._encode_oneoff(o) for o in self._state.oneoffs],
            "recurring": [self._encode_recurring(r) for r in self._state.recurring],
            "timers": [self._encode_timer(t) for t in self._state.timers],
            "active_alarms": [self._encode_active(a) for a in self._state.active_alarms],
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
    def _encode_oneoff(o: AlarmOneOff) -> dict:
        return {
            "id": o.id,
            "time": o.time.isoformat(),
            "label": o.label,
            "enabled": o.enabled,
            "temporary": o.temporary,
        }

    @staticmethod
    def _encode_recurring(r: AlarmRecurring) -> dict:
        return {
            "id": r.id,
            "time": r.time,
            "weekdays": r.weekdays,
            "label": r.label,
            "enabled": r.enabled,
            "temporary": r.temporary,
            "last_triggered_date": r.last_triggered_date,
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

    @staticmethod
    def _encode_active(a: ActiveAlarm) -> dict:
        return {
            "alarm_id": a.alarm_id,
            "triggered_at": a.triggered_at.isoformat(),
            "snoozed_until": _dt_str(a.snoozed_until),
        }

    # ------------------------------------------------------------------ accessor

    @property
    def state(self) -> AppState:
        return self._state

    def next_alarm_id(self) -> str:
        used = {int(a.id) for a in [*self._state.oneoffs, *self._state.recurring]}
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
