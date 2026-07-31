"""Parse free-text schedules and compute time-window overlaps."""

from __future__ import annotations

import re
from dataclasses import dataclass

ALL_DAYS = frozenset(range(7))

DAY_ALIASES: dict[str, int] = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# Default tutoring-day bounds when only a weekday is given.
DEFAULT_DAY_START = 8 * 60
DEFAULT_DAY_END = 22 * 60
DEFAULT_AFTER_END = 22 * 60
DEFAULT_POINT_WINDOW = 60

PERIOD_RANGES: dict[str, tuple[int, int]] = {
    "morning": (8 * 60, 12 * 60),
    "afternoon": (12 * 60, 17 * 60),
    "evening": (17 * 60, 21 * 60),
}


@dataclass(frozen=True)
class TimeRange:
    """Closed interval of minutes from midnight (0-1440)."""

    start_minutes: int
    end_minutes: int

    def __post_init__(self) -> None:
        if self.start_minutes < 0 or self.end_minutes > 24 * 60:
            raise ValueError("time range must stay within one day")
        if self.start_minutes >= self.end_minutes:
            raise ValueError("time range start must be before end")

    def overlaps(self, other: TimeRange) -> bool:
        return self.start_minutes < other.end_minutes and other.start_minutes < self.end_minutes

    def intersection(self, other: TimeRange) -> TimeRange | None:
        start = max(self.start_minutes, other.start_minutes)
        end = min(self.end_minutes, other.end_minutes)
        if start < end:
            return TimeRange(start, end)
        return None

    def duration_minutes(self) -> int:
        return self.end_minutes - self.start_minutes


@dataclass(frozen=True)
class ScheduleSlot:
    """One availability window on one or more weekdays."""

    days: frozenset[int]
    time_range: TimeRange
    source: str

    def overlaps(self, other: ScheduleSlot) -> TimeRange | None:
        shared_days = self.days & other.days
        if not shared_days:
            return None
        return self.time_range.intersection(other.time_range)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _parse_hour_token(token: str, assume_pm: bool = True) -> int | None:
    """Convert strings like 6, 6pm, 6:30, or 18:00 into minutes from midnight."""

    cleaned = token.strip().lower().replace(".", "")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", cleaned)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)

    if meridiem == "am":
        if hour == 12:
            hour = 0
    elif meridiem == "pm":
        if hour != 12:
            hour += 12
    elif assume_pm and hour <= 11:
        # Parent messages usually mean evening tutoring when they omit am/pm.
        hour += 12

    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _has_meridiem(token: str) -> bool:
    """Return whether a time token explicitly says am or pm."""

    return re.search(r"(?:am|pm)\b", token.strip().lower().replace(".", "")) is not None


def _raw_hour(token: str) -> int | None:
    """Return the written hour number before am/pm inference."""

    match = re.search(r"\b(\d{1,2})", token)
    return int(match.group(1)) if match else None


def _parse_range_tokens(start_token: str, end_token: str) -> TimeRange | None:
    """Parse a written range while preserving useful morning ranges like 10-12."""

    start = _parse_hour_token(start_token)
    end = _parse_hour_token(end_token)
    if start is not None and end is not None and start < end:
        return TimeRange(start, end)

    if not _has_meridiem(start_token) and not _has_meridiem(end_token):
        start_hour = _raw_hour(start_token)
        end_hour = _raw_hour(end_token)
        should_try_morning = (
            start_hour is not None
            and end_hour is not None
            and 7 <= start_hour <= 11
            and 10 <= end_hour <= 12
        )
        if should_try_morning:
            morning_start = _parse_hour_token(start_token, assume_pm=False)
            morning_end = _parse_hour_token(end_token, assume_pm=False)
            if morning_start is not None and morning_end is not None and morning_start < morning_end:
                return TimeRange(morning_start, morning_end)

    return None


def _point_window(minutes: int) -> TimeRange:
    half = DEFAULT_POINT_WINDOW // 2
    start = max(0, minutes - half)
    end = min(24 * 60, minutes + half)
    if end <= start:
        end = min(24 * 60, start + DEFAULT_POINT_WINDOW)
    return TimeRange(start, end)


def _extract_days(text: str) -> tuple[frozenset[int], str]:
    days: set[int] = set()
    remainder = text

    if re.search(r"\b(every day|daily|each day)\b", remainder):
        return ALL_DAYS, re.sub(r"\b(every day|daily|each day)\b", " ", remainder).strip()

    if "weekday" in remainder:
        days.update(range(5))
        remainder = remainder.replace("weekday", " ").replace("weekdays", " ")

    if "weekend" in remainder:
        days.update({5, 6})
        remainder = remainder.replace("weekend", " ").replace("weekends", " ")

    for alias, index in sorted(DAY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = rf"\b{re.escape(alias)}\b"
        if re.search(pattern, remainder):
            days.add(index)
            remainder = re.sub(pattern, " ", remainder)

    remainder = re.sub(r"\s+", " ", remainder).strip()
    return frozenset(days), remainder


def _extract_time_range(text: str) -> TimeRange | None:
    cleaned = text.strip(" ,;")
    if not cleaned:
        return None

    for period, bounds in PERIOD_RANGES.items():
        if re.fullmatch(period, cleaned) or re.search(rf"\b{period}\b", cleaned):
            return TimeRange(*bounds)

    after_match = re.search(r"\bafter\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", cleaned)
    if after_match:
        start = _parse_hour_token(after_match.group(1))
        if start is not None:
            return TimeRange(start, DEFAULT_AFTER_END)

    before_match = re.search(r"\bbefore\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", cleaned)
    if before_match:
        end = _parse_hour_token(before_match.group(1))
        if end is not None:
            return TimeRange(DEFAULT_DAY_START, end)

    range_match = re.search(
        r"\b(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:-|to|until)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b",
        cleaned,
    )
    if range_match:
        parsed_range = _parse_range_tokens(range_match.group(1), range_match.group(2))
        if parsed_range:
            return parsed_range

    point_match = re.search(r"\b(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", cleaned)
    if point_match:
        point = _parse_hour_token(point_match.group(1))
        if point is not None:
            return _point_window(point)

    return None


def parse_availability_entry(text: str) -> list[ScheduleSlot]:
    """Turn one availability string into structured weekday/time slots."""

    normalized = _normalize_text(text)
    if not normalized or normalized in {"idk", "unknown", "tbd", "n/a"}:
        return []

    days, remainder = _extract_days(normalized)
    time_range = _extract_time_range(remainder)

    if days and time_range:
        return [ScheduleSlot(days=days, time_range=time_range, source=text)]

    if days and not time_range:
        return [
            ScheduleSlot(
                days=days,
                time_range=TimeRange(DEFAULT_DAY_START, DEFAULT_DAY_END),
                source=text,
            )
        ]

    if time_range and not days:
        return [ScheduleSlot(days=ALL_DAYS, time_range=time_range, source=text)]

    return []


def parse_availability(entries: list[str]) -> list[ScheduleSlot]:
    """Parse many availability strings, skipping anything unrecognizable."""

    slots: list[ScheduleSlot] = []
    for entry in entries:
        slots.extend(parse_availability_entry(entry))
    return slots


def _format_minutes(minutes: int) -> str:
    hour = minutes // 60
    minute = minutes % 60
    meridiem = "am" if hour < 12 else "pm"
    display_hour = hour % 12
    if display_hour == 0:
        display_hour = 12
    if minute:
        return f"{display_hour}:{minute:02d}{meridiem}"
    return f"{display_hour}{meridiem}"


def _format_overlap(day: int, overlap: TimeRange) -> str:
    day_name = DAY_NAMES[day]
    start = _format_minutes(overlap.start_minutes)
    end = _format_minutes(overlap.end_minutes)
    return f"{day_name} {start}-{end}"


def availability_overlap(wanted: list[str], offered: list[str]) -> list[str]:
    """Return human-readable shared windows between student and teacher schedules."""

    wanted_slots = parse_availability(wanted)
    offered_slots = parse_availability(offered)
    if not wanted_slots or not offered_slots:
        return []

    overlaps: set[str] = set()
    for want in wanted_slots:
        for offer in offered_slots:
            shared_days = want.days & offer.days
            intersection = want.time_range.intersection(offer.time_range)
            if not shared_days or intersection is None:
                continue
            for day in sorted(shared_days):
                overlaps.add(_format_overlap(day, intersection))

    return sorted(overlaps)


def overlap_minutes(wanted: list[str], offered: list[str]) -> int:
    """Total overlapping minutes across all shared day/time windows."""

    wanted_slots = parse_availability(wanted)
    offered_slots = parse_availability(offered)
    total = 0
    seen: set[tuple[int, int, int]] = set()

    for want in wanted_slots:
        for offer in offered_slots:
            shared_days = want.days & offer.days
            intersection = want.time_range.intersection(offer.time_range)
            if not shared_days or intersection is None:
                continue
            for day in shared_days:
                key = (day, intersection.start_minutes, intersection.end_minutes)
                if key in seen:
                    continue
                seen.add(key)
                total += intersection.duration_minutes()

    return total
