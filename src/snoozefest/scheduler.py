from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional
from zoneinfo import ZoneInfo

from .models import ActiveAlarm, AlarmOneOff, AlarmRecurring, Timer
from .store import AppState, Store


class Scheduler:
    """
    Tick-based alarm and timer engine.

    All public mutating methods release the lock before firing callbacks, so
    callbacks (which publish MQTT state) can safely call back into read-only
    Scheduler methods without deadlocking.
    """

    def __init__(
        self,
        store: Store,
        tz: ZoneInfo,
        on_alarm_triggered: Callable[[str, str], None],
        on_timer_finished: Callable[[str, str], None],
        on_state_changed: Callable[[], None],
    ) -> None:
        self._store = store
        self._tz = tz
        self._on_alarm_triggered = on_alarm_triggered
        self._on_timer_finished = on_timer_finished
        self._on_state_changed = on_state_changed
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ time

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def _now_local(self) -> datetime:
        return datetime.now(self._tz)

    @staticmethod
    def _parse_hour_minute(time_str: str) -> tuple[int, int]:
        parts = [int(p) for p in str(time_str).split(":")]
        if len(parts) < 2:
            raise ValueError("time must be in HH:MM or HH:MM:SS format")
        hour, minute = parts[0], parts[1]
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("time must be a valid 24h time")
        return hour, minute

    def _next_oneoff_utc_from_time(self, time_str: str, now_local: Optional[datetime] = None) -> datetime:
        now_local = now_local or self._now_local()
        hour, minute = self._parse_hour_minute(time_str)
        candidate_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate_local <= now_local:
            candidate_local += timedelta(days=1)
        return candidate_local.astimezone(timezone.utc)

    def _oneoff_time_str(self, dt_utc: datetime) -> str:
        return dt_utc.astimezone(self._tz).strftime("%H:%M")

    # ------------------------------------------------------------------ tick

    def tick(self) -> None:
        triggered: list[tuple[str, str]] = []
        finished: list[tuple[str, str]] = []
        state_changed = False

        with self._lock:
            now_utc = self._now_utc()
            now_local = self._now_local()
            state = self._store.state
            active_ids = {a.alarm_id for a in state.active_alarms}

            # One-off alarms
            for alarm in state.oneoffs:
                if not alarm.enabled or alarm.id in active_ids:
                    continue
                if now_utc >= alarm.time:
                    state.active_alarms.append(ActiveAlarm(alarm_id=alarm.id, triggered_at=now_utc))
                    active_ids.add(alarm.id)
                    state_changed = True
                    triggered.append((alarm.id, alarm.label))

            # Recurring alarms
            today_local = now_local.date()
            today_wd = now_local.weekday()
            for alarm in state.recurring:
                if not alarm.enabled or alarm.id in active_ids:
                    continue
                if alarm.last_triggered_date == today_local.isoformat():
                    continue
                if today_wd not in alarm.weekdays:
                    continue
                h, m = self._parse_hour_minute(alarm.time)
                # Recurring alarms fire only during their scheduled minute.
                # This avoids immediate "catch-up" triggers after restarts.
                if now_local.hour == h and now_local.minute == m:
                    state.active_alarms.append(ActiveAlarm(alarm_id=alarm.id, triggered_at=now_utc))
                    active_ids.add(alarm.id)
                    state_changed = True
                    triggered.append((alarm.id, alarm.label))

            # Snoozed alarms becoming ringing again
            for active in state.active_alarms:
                if active.snoozed_until is not None and now_utc >= active.snoozed_until:
                    active.snoozed_until = None
                    state_changed = True

            # Expired timers
            for timer in state.timers:
                if timer.status in {"running", "snoozed"} and now_utc >= timer.expires_at:
                    timer.status = "ringing"
                    state_changed = True
                    finished.append((timer.id, timer.label))

            if state_changed:
                self._store.save()

        # Fire callbacks outside the lock
        for alarm_id, label in triggered:
            self._on_alarm_triggered(alarm_id, label)
        for timer_id, label in finished:
            self._on_timer_finished(timer_id, label)
        if state_changed:
            self._on_state_changed()

    # ------------------------------------------------------------------ mutations

    def add_oneoff(self, time: datetime, label: str) -> AlarmOneOff:
        with self._lock:
            alarm = AlarmOneOff(id=self._store.next_alarm_id(), time=time, label=label)
            self._store.state.oneoffs.append(alarm)
            self._store.save()
        self._on_state_changed()
        return alarm

    def add_oneoff_time(self, time_str: str, label: str, *, enabled: bool = True) -> AlarmOneOff:
        with self._lock:
            alarm_time = self._next_oneoff_utc_from_time(time_str)
            alarm = AlarmOneOff(id=self._store.next_alarm_id(), time=alarm_time, label=label, enabled=enabled)
            self._store.state.oneoffs.append(alarm)
            self._store.save()
        self._on_state_changed()
        return alarm

    def add_recurring(self, time: str, weekdays: List[int], label: str, *, enabled: bool = True) -> AlarmRecurring:
        with self._lock:
            alarm = AlarmRecurring(
                id=self._store.next_alarm_id(),
                time=time,
                weekdays=weekdays,
                label=label,
                enabled=enabled,
            )
            self._store.state.recurring.append(alarm)
            self._store.save()
        self._on_state_changed()
        return alarm

    def update_alarm(self, alarm_id: str, **kwargs) -> Optional[str]:
        """
        Update arbitrary fields on an alarm. Returns kind string on success,
        None if not found.  For one-off 'time' values supply an ISO string;
        this method converts it to a timezone-aware datetime.
        """
        with self._lock:
            state = self._store.state
            for alarm in state.oneoffs:
                if alarm.id != alarm_id:
                    continue
                for k, v in kwargs.items():
                    if k == "time" and isinstance(v, str):
                        if "T" in v:
                            dt = datetime.fromisoformat(v)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=self._tz)
                            local_time_str = dt.astimezone(self._tz).strftime("%H:%M")
                            setattr(alarm, "time", self._next_oneoff_utc_from_time(local_time_str))
                        else:
                            setattr(alarm, "time", self._next_oneoff_utc_from_time(v))
                    elif k == "enabled":
                        enabled = bool(v)
                        alarm.enabled = enabled
                        if enabled:
                            local_time_str = self._oneoff_time_str(alarm.time)
                            alarm.time = self._next_oneoff_utc_from_time(local_time_str)
                    elif hasattr(alarm, k):
                        setattr(alarm, k, v)
                self._store.save()
                kind = "oneoff"
                break
            else:
                kind = None
                for alarm in state.recurring:
                    if alarm.id != alarm_id:
                        continue
                    for k, v in kwargs.items():
                        if hasattr(alarm, k):
                            setattr(alarm, k, v)
                    self._store.save()
                    kind = "recurring"
                    break

        if kind:
            self._on_state_changed()
        return kind

    def set_alarm(
        self,
        alarm_id: str,
        *,
        time: Optional[str] = None,
        weekdays: Optional[List[int]] = None,
        label: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[str]:
        """
        Unified alarm edit path.

        Behavior:
        - weekdays omitted -> keep current alarm kind.
        - weekdays empty [] -> one-off alarm.
        - weekdays non-empty -> recurring alarm.
        """

        def _local_time_str(raw: str) -> str:
            text = str(raw)
            if "T" in text:
                dt = datetime.fromisoformat(text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=self._tz)
                return dt.astimezone(self._tz).strftime("%H:%M")
            return text

        normalized_weekdays: Optional[List[int]]
        if weekdays is None:
            normalized_weekdays = None
        else:
            normalized_weekdays = [int(d) for d in weekdays]
            if not all(0 <= d <= 6 for d in normalized_weekdays):
                raise ValueError("weekdays must be integers 0-6")

        with self._lock:
            state = self._store.state

            for oneoff in state.oneoffs:
                if oneoff.id != alarm_id:
                    continue

                target_kind = "oneoff"
                if normalized_weekdays is not None and len(normalized_weekdays) > 0:
                    target_kind = "recurring"

                if target_kind == "recurring":
                    recurring_time = _local_time_str(time) if time is not None else self._oneoff_time_str(oneoff.time)
                    recurring = AlarmRecurring(
                        id=oneoff.id,
                        time=recurring_time,
                        weekdays=normalized_weekdays or [],
                        label=str(label) if label is not None else oneoff.label,
                        enabled=bool(enabled) if enabled is not None else oneoff.enabled,
                    )
                    state.oneoffs.remove(oneoff)
                    state.recurring.append(recurring)
                    kind = "recurring"
                else:
                    if time is not None:
                        oneoff.time = self._next_oneoff_utc_from_time(_local_time_str(time))
                    if label is not None:
                        oneoff.label = str(label)
                    if enabled is not None:
                        oneoff.enabled = bool(enabled)
                        if oneoff.enabled:
                            oneoff.time = self._next_oneoff_utc_from_time(self._oneoff_time_str(oneoff.time))
                    kind = "oneoff"

                self._store.save()
                break
            else:
                kind = None
                for recurring in state.recurring:
                    if recurring.id != alarm_id:
                        continue

                    target_kind = "recurring"
                    if normalized_weekdays is not None and len(normalized_weekdays) == 0:
                        target_kind = "oneoff"

                    if target_kind == "oneoff":
                        oneoff_time = _local_time_str(time) if time is not None else recurring.time
                        oneoff = AlarmOneOff(
                            id=recurring.id,
                            time=self._next_oneoff_utc_from_time(oneoff_time),
                            label=str(label) if label is not None else recurring.label,
                            enabled=bool(enabled) if enabled is not None else recurring.enabled,
                        )
                        state.recurring.remove(recurring)
                        state.oneoffs.append(oneoff)
                        kind = "oneoff"
                    else:
                        if time is not None:
                            recurring.time = _local_time_str(time)
                        if normalized_weekdays is not None:
                            recurring.weekdays = normalized_weekdays
                        if label is not None:
                            recurring.label = str(label)
                        if enabled is not None:
                            recurring.enabled = bool(enabled)
                        kind = "recurring"

                    self._store.save()
                    break

        if kind:
            self._on_state_changed()
        return kind

    def remove_alarm(self, alarm_id: str) -> bool:
        with self._lock:
            state = self._store.state
            for container in (state.oneoffs, state.recurring):
                for alarm in container:
                    if alarm.id == alarm_id:
                        container.remove(alarm)
                        state.active_alarms = [
                            a for a in state.active_alarms if a.alarm_id != alarm_id
                        ]
                        self._store.save()
                        found = True
                        break
                else:
                    found = False
                    continue
                break
        if found:
            self._on_state_changed()
        return found

    def snooze(self, minutes: int, alarm_id: Optional[str] = None) -> List[str]:
        """Snooze ringing alarms. Optionally target one alarm by ID."""
        snoozed: List[str] = []
        with self._lock:
            now_utc = self._now_utc()
            for active in self._store.state.active_alarms:
                if active.is_ringing and (alarm_id is None or active.alarm_id == alarm_id):
                    active.snoozed_until = now_utc + timedelta(minutes=minutes)
                    snoozed.append(active.alarm_id)
            if snoozed:
                self._store.save()
        if snoozed:
            self._on_state_changed()
        return snoozed

    def dismiss(self, alarm_id: Optional[str] = None) -> List[str]:
        """
        Dismiss active alarm(s) — ringing or snoozed.

        - One-off: sets enabled=False.
        - Recurring: sets last_triggered_date to today; alarm stays enabled.

        Returns list of dismissed alarm IDs.
        """
        dismissed: List[str] = []
        with self._lock:
            state = self._store.state
            today = self._now_local().date().isoformat()

            to_dismiss = [
                a for a in state.active_alarms
                if alarm_id is None or a.alarm_id == alarm_id
            ]

            for active in to_dismiss:
                state.active_alarms.remove(active)
                dismissed.append(active.alarm_id)

                for alarm in state.oneoffs:
                    if alarm.id == active.alarm_id:
                        alarm.enabled = False
                        break

                for alarm in state.recurring:
                    if alarm.id == active.alarm_id:
                        alarm.last_triggered_date = today
                        break

            if dismissed:
                self._store.save()

        if dismissed:
            self._on_state_changed()
        return dismissed

    def add_timer(self, duration_seconds: int, label: str, *, initial_status: str = "running") -> Timer:
        if duration_seconds < 1:
            raise ValueError("duration_seconds must be ≥ 1")
        if initial_status not in {"running", "dismissed"}:
            raise ValueError("initial_status must be 'running' or 'dismissed'")

        with self._lock:
            now_utc = self._now_utc()
            timer = Timer(
                id=self._store.next_timer_id(),
                label=label,
                duration_seconds=duration_seconds,
                started_at=now_utc,
                expires_at=(now_utc if initial_status == "dismissed" else now_utc + timedelta(seconds=duration_seconds)),
                status=initial_status,
            )
            self._store.state.timers.append(timer)
            self._store.save()
        self._on_state_changed()
        return timer

    def purge_all(self) -> tuple[int, int]:
        with self._lock:
            state = self._store.state
            removed_alarms = len(state.oneoffs) + len(state.recurring)
            removed_timers = len(state.timers)

            if removed_alarms == 0 and removed_timers == 0 and not state.active_alarms:
                return (0, 0)

            state.oneoffs.clear()
            state.recurring.clear()
            state.timers.clear()
            state.active_alarms.clear()
            self._store.save()

        self._on_state_changed()
        return (removed_alarms, removed_timers)

    def update_timer(
        self,
        timer_id: str,
        *,
        duration_seconds: Optional[int] = None,
        label: Optional[str] = None,
    ) -> bool:
        with self._lock:
            now_utc = self._now_utc()
            for timer in self._store.state.timers:
                if timer.id != timer_id:
                    continue

                if label is not None:
                    timer.label = str(label)

                if duration_seconds is not None:
                    if duration_seconds < 1:
                        raise ValueError("duration_seconds must be ≥ 1")
                    timer.duration_seconds = duration_seconds
                    if timer.status == "dismissed":
                        timer.started_at = now_utc
                        timer.expires_at = now_utc
                    else:
                        timer.started_at = now_utc
                        timer.expires_at = now_utc + timedelta(seconds=duration_seconds)
                        timer.status = "running"

                self._store.save()
                found = True
                break
            else:
                found = False
        if found:
            self._on_state_changed()
        return found

    def snooze_timer(self, timer_id: str, seconds: int = 60) -> bool:
        with self._lock:
            now_utc = self._now_utc()
            for timer in self._store.state.timers:
                if timer.id == timer_id and timer.status == "ringing":
                    timer.expires_at = now_utc + timedelta(seconds=seconds)
                    timer.status = "snoozed"
                    self._store.save()
                    found = True
                    break
            else:
                found = False
        if found:
            self._on_state_changed()
        return found

    def dismiss_timer(self, timer_id: str) -> bool:
        with self._lock:
            now_utc = self._now_utc()
            for timer in self._store.state.timers:
                if timer.id != timer_id:
                    continue

                if timer.status in {"running", "ringing", "snoozed"}:
                    timer.status = "dismissed"
                    timer.expires_at = now_utc
                    self._store.save()
                    found = True
                    break

                if timer.status == "dismissed":
                    timer.started_at = now_utc
                    timer.expires_at = now_utc + timedelta(seconds=timer.duration_seconds)
                    timer.status = "running"
                    self._store.save()
                    found = True
                    break
            else:
                found = False
        if found:
            self._on_state_changed()
        return found

    def cancel_timer(self, timer_id: str) -> bool:
        with self._lock:
            state = self._store.state
            for timer in state.timers:
                if timer.id == timer_id:
                    state.timers.remove(timer)
                    self._store.save()
                    found = True
                    break
            else:
                found = False
        if found:
            self._on_state_changed()
        return found

    # ------------------------------------------------------------------ queries

    def next_alarm(self) -> Optional[dict]:
        with self._lock:
            return self._next_alarm_unlocked()

    def _next_alarm_unlocked(self) -> Optional[dict]:
        now_utc = self._now_utc()
        now_local = self._now_local()
        state = self._store.state
        active_ids = {a.alarm_id for a in state.active_alarms}
        candidates: list[tuple[datetime, str, str, str]] = []

        for alarm in state.oneoffs:
            if alarm.enabled and alarm.id not in active_ids and alarm.time > now_utc:
                candidates.append((alarm.time, alarm.id, alarm.label, "oneoff"))

        for alarm in state.recurring:
            if not alarm.enabled or alarm.id in active_ids:
                continue
            nt = self._next_recurring_time(alarm, now_local, now_utc)
            if nt is not None:
                candidates.append((nt, alarm.id, alarm.label, "recurring"))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        t, aid, label, kind = candidates[0]
        dt = self._dt_payload(t)
        return {
            "time": t.isoformat(),
            "time_utc": dt["utc"],
            "time_local": dt["local"],
            "time_friendly": dt["friendly_local"],
            "timezone": dt["timezone"],
            "alarm_id": aid,
            "label": label,
            "kind": kind,
        }

    def _next_recurring_time(
        self,
        alarm: AlarmRecurring,
        now_local: datetime,
        now_utc: datetime,
    ) -> Optional[datetime]:
        h, m = self._parse_hour_minute(alarm.time)
        for day_offset in range(8):
            target_date = now_local.date() + timedelta(days=day_offset)
            if target_date.weekday() not in alarm.weekdays:
                continue
            target_dt = datetime(
                target_date.year, target_date.month, target_date.day,
                h, m, 0, tzinfo=self._tz,
            )
            if target_dt.astimezone(timezone.utc) > now_utc:
                return target_dt.astimezone(timezone.utc)
        return None

    def full_state(self) -> dict:
        with self._lock:
            state = self._store.state
            now_utc = self._now_utc()
            return {
                "alarms": self._alarms_payload(state),
                "timers": self._timers_payload(state, now_utc),
                "active_alarm": self._active_alarm_payload(state),
                "next_alarm": self._next_alarm_unlocked(),
            }

    # ------------------------------------------------------------------ payload helpers

    def _to_utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=self._tz).astimezone(timezone.utc)
        return dt.astimezone(timezone.utc)

    def _dt_payload(self, dt: datetime) -> dict:
        utc_dt = self._to_utc(dt)
        local_dt = utc_dt.astimezone(self._tz)
        return {
            "utc": utc_dt.isoformat(),
            "local": local_dt.isoformat(),
            "friendly_local": local_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "timezone": str(self._tz),
        }

    @staticmethod
    def _format_duration(total_seconds: int) -> str:
        total_seconds = max(0, int(total_seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts: list[str] = []
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds or not parts:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        return " ".join(parts)

    def _alarms_payload(self, state: AppState) -> list:
        out = []
        for a in state.oneoffs:
            dt = self._dt_payload(a.time)
            out.append({
                "id": a.id, "kind": "oneoff",
                "time": a.time.isoformat(),
                "time_utc": dt["utc"],
                "time_local": dt["local"],
                "time_friendly": dt["friendly_local"],
                "timezone": dt["timezone"],
                "label": a.label,
                "enabled": a.enabled,
            })
        for a in state.recurring:
            out.append({
                "id": a.id, "kind": "recurring",
                "time": a.time, "weekdays": a.weekdays,
                "label": a.label, "enabled": a.enabled,
                "timezone": str(self._tz),
            })
        return out

    def _timers_payload(self, state: AppState, now_utc: datetime) -> list:
        return [
            {
                "id": t.id,
                "label": t.label,
                "status": t.status,
                "duration_seconds": t.duration_seconds,
                "duration_friendly": self._format_duration(t.duration_seconds),
                "remaining_seconds": max(0, int((t.expires_at - now_utc).total_seconds())),
                "remaining_friendly": self._format_duration(max(0, int((t.expires_at - now_utc).total_seconds()))),
                "expires_at": t.expires_at.isoformat(),
                "expires_at_utc": self._dt_payload(t.expires_at)["utc"],
                "expires_at_local": self._dt_payload(t.expires_at)["local"],
                "expires_at_friendly": self._dt_payload(t.expires_at)["friendly_local"],
                "timezone": str(self._tz),
            }
            for t in state.timers
        ]

    def _active_alarm_payload(self, state: AppState) -> dict:
        ringing = []
        snoozed = []
        for a in state.active_alarms:
            triggered = self._dt_payload(a.triggered_at)
            entry: dict = {
                "alarm_id": a.alarm_id,
                "triggered_at": a.triggered_at.isoformat(),
                "triggered_at_utc": triggered["utc"],
                "triggered_at_local": triggered["local"],
                "triggered_at_friendly": triggered["friendly_local"],
                "timezone": triggered["timezone"],
            }
            if a.snoozed_until:
                snoozed_until = self._dt_payload(a.snoozed_until)
                entry["snoozed_until"] = a.snoozed_until.isoformat()
                entry["snoozed_until_utc"] = snoozed_until["utc"]
                entry["snoozed_until_local"] = snoozed_until["local"]
                entry["snoozed_until_friendly"] = snoozed_until["friendly_local"]
                snoozed.append(entry)
            else:
                ringing.append(entry)
        if ringing:
            status = "ringing"
        elif snoozed:
            status = "snoozed"
        else:
            status = "idle"
        return {"status": status, "ringing": ringing, "snoozed": snoozed, "timezone": str(self._tz)}
