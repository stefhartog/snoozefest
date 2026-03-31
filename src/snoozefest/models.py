from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Alarm:
    time: str                               # "HH:MM" in local timezone
    label: str
    id: str
    enabled: bool = True
    temporary: bool = False
    recurring: bool = False
    weekdays: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    last_triggered_date: Optional[str] = None   # "YYYY-MM-DD"; set on dismiss when recurring
    status: str = "active"
    triggered_at: Optional[datetime] = None     # UTC
    snoozed_until: Optional[datetime] = None    # UTC


@dataclass
class Timer:
    label: str
    duration_seconds: int
    started_at: datetime    # UTC
    expires_at: datetime    # UTC
    id: str
    status: str = "active"
    temporary: bool = False
    paused_remaining_seconds: Optional[int] = None
