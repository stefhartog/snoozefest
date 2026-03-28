from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class AlarmOneOff:
    time: datetime          # timezone-aware UTC
    label: str
    id: str
    enabled: bool = True
    temporary: bool = False


@dataclass
class AlarmRecurring:
    time: str               # "HH:MM" in local timezone
    weekdays: List[int]     # 0 = Monday … 6 = Sunday
    label: str
    id: str
    enabled: bool = True
    temporary: bool = False
    last_triggered_date: Optional[str] = None   # "YYYY-MM-DD"; set on dismiss


@dataclass
class Timer:
    label: str
    duration_seconds: int
    started_at: datetime    # UTC
    expires_at: datetime    # UTC
    id: str
    status: str = "running"
    temporary: bool = False


@dataclass
class ActiveAlarm:
    alarm_id: str
    triggered_at: datetime              # UTC
    snoozed_until: Optional[datetime] = None    # UTC; None → currently ringing

    @property
    def is_ringing(self) -> bool:
        from datetime import timezone
        if self.snoozed_until is None:
            return True
        return datetime.now(timezone.utc) >= self.snoozed_until
