from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional
from zoneinfo import ZoneInfo

from .models import Alarm, Timer
from .store import AppState, Store


_AUTO_DISMISS_RINGING_SECONDS = 5 * 60


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
        alarm_trigger_grace_seconds: int,
        on_alarm_triggered: Callable[[str, str], None],
        on_timer_finished: Callable[[str, str], None],
        on_state_changed: Callable[[], None],
    ) -> None:
        self._store = store
        self._tz = tz
        self._on_alarm_triggered = on_alarm_triggered
        self._on_timer_finished = on_timer_finished
        self._on_state_changed = on_state_changed
        self._alarm_trigger_grace_seconds = max(0, int(alarm_trigger_grace_seconds))
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

    @staticmethod
    def _normalize_weekdays(weekdays: List[int]) -> List[int]:
        return sorted({int(day) for day in weekdays if 0 <= int(day) <= 6})

    def _next_alarm_time(self, alarm: Alarm, now_local: datetime, now_utc: datetime) -> Optional[datetime]:
        hour, minute = self._parse_hour_minute(alarm.time)

        if alarm.recurring:
            weekdays = self._normalize_weekdays(alarm.weekdays)
            if not weekdays:
                return None
            for day_offset in range(8):
                target_date = now_local.date() + timedelta(days=day_offset)
                if target_date.weekday() not in weekdays:
                    continue
                if day_offset == 0 and alarm.last_triggered_date == target_date.isoformat():
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

        if alarm.last_triggered_date is not None:
            return None

        target_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target_local <= now_local:
            target_local += timedelta(days=1)
        return target_local.astimezone(timezone.utc)

    # ------------------------------------------------------------------ tick

    def tick(self) -> None:
        triggered: list[tuple[str, str]] = []
        finished: list[tuple[str, str]] = []
        state_changed = False

        with self._lock:
            now_utc = self._now_utc()
            now_local = self._now_local()
            today_local = now_local.date().isoformat()
            state = self._store.state

            for alarm in state.alarms:
                if not alarm.enabled or alarm.status != "active":
                    continue

                hour, minute = self._parse_hour_minute(alarm.time)
                if alarm.recurring:
                    weekdays = self._normalize_weekdays(alarm.weekdays)
                    if not weekdays:
                        continue
                    if now_local.weekday() not in weekdays:
                        continue
                    if alarm.last_triggered_date == today_local:
                        continue
                else:
                    if alarm.last_triggered_date == today_local:
                        continue

                # Alarms fire during their scheduled minute, optionally
                # extended by a post-minute grace window.
                scheduled_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)

                # Base window is HH:MM:00..HH:MM:59. Grace extends beyond that.
                trigger_deadline = scheduled_local + timedelta(seconds=59 + self._alarm_trigger_grace_seconds)
                should_trigger = scheduled_local <= now_local <= trigger_deadline

                if should_trigger:
                    alarm.status = "ringing"
                    alarm.triggered_at = now_utc
                    alarm.snoozed_until = None
                    alarm.last_triggered_date = today_local
                    state_changed = True
                    triggered.append((alarm.id, alarm.label))

            # Snoozed alarms becoming ringing again
            for alarm in state.alarms:
                if alarm.status == "snoozed" and alarm.snoozed_until is not None and now_utc >= alarm.snoozed_until:
                    alarm.status = "ringing"
                    alarm.triggered_at = now_utc
                    alarm.snoozed_until = None
                    state_changed = True

            # Expired timers
            for timer in state.timers:
                if timer.status in {"active", "snoozed"} and now_utc >= timer.expires_at:
                    timer.status = "ringing"
                    state_changed = True
                    finished.append((timer.id, timer.label))

            # Ringing alarms auto-dismiss after grace period if user takes no action.
            for alarm in list(state.alarms):
                if alarm.status != "ringing":
                    continue

                if alarm.triggered_at is None:
                    alarm.triggered_at = now_utc
                    state_changed = True
                    continue

                ringing_seconds = int((now_utc - alarm.triggered_at).total_seconds())
                if ringing_seconds < _AUTO_DISMISS_RINGING_SECONDS:
                    continue

                if alarm.temporary:
                    state.alarms.remove(alarm)
                elif alarm.recurring:
                    alarm.status = "active"
                    alarm.enabled = True
                    alarm.last_triggered_date = today_local
                    alarm.triggered_at = None
                    alarm.snoozed_until = None
                else:
                    alarm.status = "inactive"
                    alarm.enabled = False
                    alarm.triggered_at = None
                    alarm.snoozed_until = None
                state_changed = True

            # Ringing timers auto-dismiss after grace period if user takes no action.
            for timer in list(state.timers):
                if timer.status != "ringing":
                    continue

                ringing_seconds = int((now_utc - timer.expires_at).total_seconds())
                if ringing_seconds < _AUTO_DISMISS_RINGING_SECONDS:
                    continue

                if timer.temporary:
                    state.timers.remove(timer)
                else:
                    timer.status = "inactive"
                    timer.expires_at = now_utc
                state_changed = True

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

    def add_alarm(
        self,
        time_str: str,
        label: str,
        *,
        enabled: bool = True,
        temporary: bool = False,
        recurring: bool = False,
        weekdays: Optional[List[int]] = None,
    ) -> Alarm:
        normalized_time = self._normalize_time_str(time_str)
        if weekdays is None:
            normalized_weekdays = [0, 1, 2, 3, 4, 5, 6]
        else:
            normalized_weekdays = self._normalize_weekdays(weekdays)

        with self._lock:
            alarm = Alarm(
                id=self._store.next_alarm_id(),
                time=normalized_time,
                label=label,
                enabled=enabled,
                temporary=temporary,
                recurring=bool(recurring),
                weekdays=normalized_weekdays,
                last_triggered_date=None,
                status=("active" if enabled else "inactive"),
            )
            self._store.state.alarms.append(alarm)
            self._store.save()

        self._on_state_changed()
        return alarm

    def add_oneoff(self, time: datetime, label: str) -> Alarm:
        time_local = self._to_utc(time).astimezone(self._tz).strftime("%H:%M")
        return self.add_alarm(time_local, label, recurring=False)

    def add_oneoff_time(
        self,
        time_str: str,
        label: str,
        *,
        enabled: bool = True,
        temporary: bool = False,
    ) -> Alarm:
        return self.add_alarm(
            time_str,
            label,
            enabled=enabled,
            temporary=temporary,
            recurring=False,
        )

    def add_recurring(
        self,
        time: str,
        weekdays: List[int],
        label: str,
        *,
        enabled: bool = True,
        temporary: bool = False,
    ) -> Alarm:
        return self.add_alarm(
            time,
            label,
            enabled=enabled,
            temporary=temporary,
            recurring=True,
            weekdays=weekdays,
        )

    def _normalize_time_str(self, raw: str) -> str:
        text = str(raw)
        if "T" in text:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=self._tz)
            return dt.astimezone(self._tz).strftime("%H:%M")

        hour, minute = self._parse_hour_minute(text)
        return f"{hour:02d}:{minute:02d}"

    def update_alarm(self, alarm_id: str, **kwargs) -> bool:
        with self._lock:
            for alarm in self._store.state.alarms:
                if alarm.id != alarm_id:
                    continue

                if "time" in kwargs and kwargs["time"] is not None:
                    alarm.time = self._normalize_time_str(str(kwargs["time"]))
                    alarm.last_triggered_date = None

                if "label" in kwargs and kwargs["label"] is not None:
                    alarm.label = str(kwargs["label"])

                if "enabled" in kwargs and kwargs["enabled"] is not None:
                    enabled = bool(kwargs["enabled"])
                    if enabled and not alarm.enabled:
                        alarm.last_triggered_date = None
                    alarm.enabled = enabled
                    if enabled and alarm.status == "inactive":
                        alarm.status = "active"
                    if not enabled:
                        alarm.status = "inactive"
                        alarm.triggered_at = None
                        alarm.snoozed_until = None

                if "recurring" in kwargs and kwargs["recurring"] is not None:
                    recurring = bool(kwargs["recurring"])
                    if recurring != alarm.recurring:
                        alarm.recurring = recurring
                        alarm.last_triggered_date = None

                if "weekdays" in kwargs and kwargs["weekdays"] is not None:
                    alarm.weekdays = self._normalize_weekdays(list(kwargs["weekdays"]))

                self._store.save()
                found = True
                break
            else:
                found = False

        if found:
            self._on_state_changed()
        return found

    def set_alarm(
        self,
        alarm_id: str,
        *,
        time: Optional[str] = None,
        weekdays: Optional[List[int]] = None,
        label: Optional[str] = None,
        enabled: Optional[bool] = None,
        recurring: Optional[bool] = None,
    ) -> bool:
        updates: dict[str, object] = {}
        if time is not None:
            updates["time"] = time
        if weekdays is not None:
            updates["weekdays"] = weekdays
        if label is not None:
            updates["label"] = label
        if enabled is not None:
            updates["enabled"] = enabled
        if recurring is not None:
            updates["recurring"] = recurring
        if not updates:
            return False
        return self.update_alarm(alarm_id, **updates)

    def remove_alarm(self, alarm_id: str) -> bool:
        with self._lock:
            state = self._store.state
            for alarm in state.alarms:
                if alarm.id == alarm_id:
                    state.alarms.remove(alarm)
                    self._store.save()
                    found = True
                    break
            else:
                found = False
        if found:
            self._on_state_changed()
        return found

    def snooze(self, minutes: int, alarm_id: Optional[str] = None) -> List[str]:
        """Snooze ringing alarms. Optionally target one alarm by ID."""
        snoozed: List[str] = []
        with self._lock:
            now_utc = self._now_utc()
            for alarm in self._store.state.alarms:
                if alarm.status == "ringing" and (alarm_id is None or alarm.id == alarm_id):
                    alarm.status = "snoozed"
                    alarm.snoozed_until = now_utc + timedelta(minutes=minutes)
                    snoozed.append(alarm.id)
            if snoozed:
                self._store.save()
        if snoozed:
            self._on_state_changed()
        return snoozed

    def dismiss(self, alarm_id: Optional[str] = None) -> List[str]:
        """
        Dismiss alarm(s).

        Ringing/snoozed behavior:
        - Recurring alarm: marks current day as handled and stays enabled.
        - Non-recurring alarm: disables after dismiss to mimic one-off behavior.

        Fallback behavior when no ringing/snoozed alarm is matched:
        - If alarm_id is provided, dismiss that alarm by ID.
        - If alarm_id is omitted, dismiss the next scheduled alarm.
        """
        dismissed: List[str] = []
        with self._lock:
            state = self._store.state
            today = self._now_local().date().isoformat()

            to_dismiss = [
                a for a in state.alarms
                if a.status in {"ringing", "snoozed"} and (alarm_id is None or a.id == alarm_id)
            ]

            for alarm in to_dismiss:
                dismissed.append(alarm.id)
                if alarm.temporary:
                    state.alarms.remove(alarm)
                elif alarm.recurring:
                    alarm.status = "active"
                    alarm.enabled = True
                    alarm.last_triggered_date = today
                    alarm.triggered_at = None
                    alarm.snoozed_until = None
                else:
                    alarm.status = "inactive"
                    alarm.enabled = False
                    alarm.triggered_at = None
                    alarm.snoozed_until = None

            if not dismissed:
                target_alarm_id: Optional[str] = alarm_id
                if target_alarm_id is None:
                    next_alarm = self._next_alarm_unlocked()
                    if next_alarm is not None:
                        target_alarm_id = str(next_alarm.get("alarm_id") or "") or None

                if target_alarm_id is not None:
                    for alarm in state.alarms:
                        if alarm.id != target_alarm_id:
                            continue
                        if alarm.temporary:
                            state.alarms.remove(alarm)
                        elif alarm.recurring:
                            alarm.status = "active"
                            alarm.enabled = True
                            alarm.last_triggered_date = today
                            alarm.triggered_at = None
                            alarm.snoozed_until = None
                        else:
                            alarm.status = "inactive"
                            alarm.enabled = False
                            alarm.triggered_at = None
                            alarm.snoozed_until = None
                        dismissed.append(target_alarm_id)
                        break

            if dismissed:
                self._store.save()

        if dismissed:
            self._on_state_changed()
        return dismissed

    def add_timer(
        self,
        duration_seconds: int,
        label: str,
        *,
        initial_status: str = "active",
        temporary: bool = False,
    ) -> Timer:
        if duration_seconds < 1:
            raise ValueError("duration_seconds must be ≥ 1")
        if initial_status not in {"active", "inactive"}:
            raise ValueError("initial_status must be 'active' or 'inactive'")

        with self._lock:
            now_utc = self._now_utc()
            timer = Timer(
                id=self._store.next_timer_id(),
                label=label,
                duration_seconds=duration_seconds,
                started_at=now_utc,
                expires_at=(now_utc if initial_status == "inactive" else now_utc + timedelta(seconds=duration_seconds)),
                status=initial_status,
                temporary=temporary,
            )
            self._store.state.timers.append(timer)
            self._store.save()
        self._on_state_changed()
        return timer

    def purge_all(self) -> tuple[int, int]:
        with self._lock:
            state = self._store.state
            removed_alarms = len(state.alarms)
            removed_timers = len(state.timers)

            if removed_alarms == 0 and removed_timers == 0:
                return (0, 0)

            state.alarms.clear()
            state.timers.clear()
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
                    if timer.status == "inactive":
                        timer.started_at = now_utc
                        timer.expires_at = now_utc
                    else:
                        timer.started_at = now_utc
                        timer.expires_at = now_utc + timedelta(seconds=duration_seconds)
                        timer.status = "active"

                self._store.save()
                found = True
                break
            else:
                found = False
        if found:
            self._on_state_changed()
        return found

    def snooze_timer(self, timer_id: Optional[str] = None, seconds: int = 60) -> bool:
        with self._lock:
            now_utc = self._now_utc()
            changed = False
            for timer in self._store.state.timers:
                if (timer_id is None or timer.id == timer_id) and timer.status == "ringing":
                    timer.expires_at = now_utc + timedelta(seconds=seconds)
                    timer.status = "snoozed"
                    changed = True
                    if timer_id is not None:
                        break

            if changed:
                self._store.save()

        if changed:
            self._on_state_changed()
        return changed

    def dismiss_timer(self, timer_id: Optional[str] = None) -> bool:
        with self._lock:
            now_utc = self._now_utc()
            changed = False
            for timer in self._store.state.timers:
                if timer_id is not None and timer.id != timer_id:
                    continue

                if timer.status in {"active", "ringing", "snoozed"}:
                    if timer.temporary:
                        self._store.state.timers.remove(timer)
                    else:
                        timer.status = "inactive"
                        timer.expires_at = now_utc
                    changed = True
                    if timer_id is not None:
                        break
                    continue

            if changed:
                self._store.save()

        if changed:
            self._on_state_changed()
        return changed

    def activate_timer(self, timer_id: Optional[str] = None) -> bool:
        with self._lock:
            now_utc = self._now_utc()
            changed = False
            for timer in self._store.state.timers:
                if timer_id is not None and timer.id != timer_id:
                    continue

                if timer.status == "inactive":
                    timer.started_at = now_utc
                    timer.expires_at = now_utc + timedelta(seconds=timer.duration_seconds)
                    timer.status = "active"
                    changed = True
                    if timer_id is not None:
                        break

            if changed:
                self._store.save()

        if changed:
            self._on_state_changed()
        return changed

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
        candidates: list[tuple[datetime, Alarm]] = []

        for alarm in state.alarms:
            if not alarm.enabled or alarm.status != "active":
                continue
            next_trigger = self._next_alarm_time(alarm, now_local, now_utc)
            if next_trigger is not None:
                candidates.append((next_trigger, alarm))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        trigger_time, alarm = candidates[0]
        dt = self._dt_payload(trigger_time)
        return {
            "time": trigger_time.isoformat(),
            "time_utc": dt["utc"],
            "time_local": dt["local"],
            "time_friendly": dt["friendly_local"],
            "timezone": dt["timezone"],
            "alarm_id": alarm.id,
            "label": alarm.label,
            "recurring": alarm.recurring,
        }

    def full_state(self) -> dict:
        with self._lock:
            state = self._store.state
            now_utc = self._now_utc()
            return {
                "alarms": self._alarms_payload(state),
                "timers": self._timers_payload(state, now_utc),
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

    @staticmethod
    def _normalize_timer_status(status: str) -> tuple[str, str, str]:
        timer_status = str(status).strip().lower()
        if timer_status == "ringing":
            return ("ringing", "Ringing", "ringing")
        if timer_status == "snoozed":
            return ("snoozed", "Snoozed", "snoozed")
        if timer_status == "active":
            return ("active", "Active", "active")
        if timer_status == "inactive":
            return ("inactive", "Inactive", "inactive")
        return ("inactive", "Inactive", "unknown")

    def _normalize_alarm_status(
        self,
        alarm: Alarm,
        status: str,
        today_local_iso: str,
    ) -> tuple[str, str, str]:
        alarm_status = str(status).strip().lower()
        if alarm_status == "inactive":
            return ("inactive", "Inactive", "inactive")
        if alarm_status == "ringing":
            return ("ringing", "Ringing", "ringing")
        if alarm_status == "snoozed":
            return ("snoozed", "Snoozed", "snoozed")

        if not alarm.enabled:
            return ("inactive", "Inactive", "disabled")

        if alarm.recurring and alarm.last_triggered_date == today_local_iso:
            return ("active", "Active", "dismissed_for_today")

        return ("active", "Active", "scheduled")

    def _alarms_payload(self, state: AppState) -> list:
        out = []
        today_local_iso = self._now_local().date().isoformat()

        for alarm in state.alarms:
            current_status = str(alarm.status or ("active" if alarm.enabled else "inactive"))
            canonical_status, normalized_status, status_reason = self._normalize_alarm_status(
                alarm,
                current_status,
                today_local_iso,
            )
            out.append({
                "id": alarm.id,
                "time": alarm.time,
                "label": alarm.label,
                "enabled": alarm.enabled,
                "temporary": alarm.temporary,
                "recurring": alarm.recurring,
                "weekdays": alarm.weekdays,
                "last_triggered_date": alarm.last_triggered_date,
                "status": canonical_status,
                "status_normalized": normalized_status,
                "status_reason": status_reason,
                "triggered_at": alarm.triggered_at.isoformat() if alarm.triggered_at is not None else None,
                "snoozed_until": alarm.snoozed_until.isoformat() if alarm.snoozed_until is not None else None,
                "timezone": str(self._tz),
            })
        return out

    def _timers_payload(self, state: AppState, now_utc: datetime) -> list:
        payload: list[dict] = []
        for t in state.timers:
            canonical_status, normalized_status, status_reason = self._normalize_timer_status(str(t.status))
            remaining_seconds = max(0, int((t.expires_at - now_utc).total_seconds()))
            expires_payload = self._dt_payload(t.expires_at)
            payload.append({
                "id": t.id,
                "label": t.label,
                "status": canonical_status,
                "status_normalized": normalized_status,
                "status_reason": status_reason,
                "temporary": t.temporary,
                "duration_seconds": t.duration_seconds,
                "duration_friendly": self._format_duration(t.duration_seconds),
                "remaining": remaining_seconds,
                "remaining_friendly": self._format_duration(remaining_seconds),
                "expires_at": t.expires_at.isoformat(),
                "expires_at_utc": expires_payload["utc"],
                "expires_at_local": expires_payload["local"],
                "expires_at_friendly": expires_payload["friendly_local"],
                "timezone": str(self._tz),
            })
        return payload
