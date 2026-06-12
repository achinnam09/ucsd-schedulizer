"""Parse a plain-text UCSD schedule into structured course data.

Input format (one course per line):

    CODE | Title | Days | Start | End | Location

Fields are separated by | (preferred) or commas. Location is optional.
Lines beginning with # are comments, except for recognized directives:

    # term-start: 2026-03-31
    # term-end:   2026-06-13
    # holiday:    2026-05-25   (repeatable)

Example:
    DSC190 | Tools of the Trade | MWF | 11:00a | 11:50a | PODEM 1A18
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time


# RFC 5545 BYDAY codes indexed by Python weekday() (Mon=0 .. Sun=6)
_WEEKDAY_TO_BYDAY = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
_BYDAY_TO_WEEKDAY = {code: i for i, code in enumerate(_WEEKDAY_TO_BYDAY)}

# Greedy day tokenizer: try two-letter forms first, then single letters
_TWO_LETTER = {
    "mo": "MO", "tu": "TU", "we": "WE", "th": "TH",
    "fr": "FR", "sa": "SA", "su": "SU",
}
_ONE_LETTER = {
    "m": "MO", "t": "TU", "w": "WE", "r": "TH",
    "f": "FR", "s": "SA", "u": "SU",
}


class ScheduleError(ValueError):
    """Raised when a schedule line or directive cannot be parsed."""


@dataclass
class Course:
    code: str
    title: str
    days: list[str]       # BYDAY codes e.g. ["MO", "WE", "FR"]
    start: time
    end: time
    location: str = ""

    def weekdays(self) -> list[int]:
        """Return meeting days as Python weekday ints (Mon=0)."""
        return sorted(_BYDAY_TO_WEEKDAY[d] for d in self.days)


@dataclass
class Schedule:
    courses: list[Course] = field(default_factory=list)
    term_start: date | None = None
    term_end: date | None = None
    holidays: list[date] = field(default_factory=list)


def parse_days(raw: str) -> list[str]:
    """Turn a day string like 'MWF' or 'TuTh' into BYDAY codes."""
    s = re.sub(r"[\s/,.\-]", "", raw).lower()
    if not s:
        raise ScheduleError(f"no meeting days found in {raw!r}")
    out: list[str] = []
    i = 0
    while i < len(s):
        pair = s[i: i + 2]
        if pair in _TWO_LETTER:
            code = _TWO_LETTER[pair]
            i += 2
        elif s[i] in _ONE_LETTER:
            code = _ONE_LETTER[s[i]]
            i += 1
        else:
            raise ScheduleError(
                f"unrecognized day token in {raw!r} near {s[i:]!r}"
            )
        if code not in out:
            out.append(code)
    return out


def parse_time(raw: str) -> time:
    """Parse times like '10:00', '10:00am', '2:15p', '9:30a'."""
    s = raw.strip().lower().replace(" ", "")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(am|pm|a|p)?", s)
    if not m:
        raise ScheduleError(f"could not parse time {raw!r}")
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = m.group(3)
    if meridiem in ("pm", "p") and hour != 12:
        hour += 12
    elif meridiem in ("am", "a") and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ScheduleError(f"time out of range: {raw!r}")
    return time(hour, minute)


def _parse_directive(body: str, schedule: Schedule) -> None:
    key, _, value = body.partition(":")
    key = key.strip().lower()
    value = value.strip()
    if key in ("term-start", "start"):
        schedule.term_start = date.fromisoformat(value)
    elif key in ("term-end", "end"):
        schedule.term_end = date.fromisoformat(value)
    elif key in ("holiday", "skip", "no-class"):
        schedule.holidays.append(date.fromisoformat(value))


def _split_fields(line: str) -> list[str]:
    delimiter = "|" if "|" in line else ","
    return [part.strip() for part in line.split(delimiter)]


def parse_schedule(text: str) -> Schedule:
    """Parse full schedule text into a Schedule object."""
    schedule = Schedule()
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            _parse_directive(line[1:].strip(), schedule)
            continue
        fields = _split_fields(line)
        if len(fields) < 5:
            raise ScheduleError(
                f"line {lineno}: expected at least 5 fields "
                f"(code|title|days|start|end), got {len(fields)}: {raw_line!r}"
            )
        code, title, days, start, end, *rest = fields
        location = rest[0] if rest else ""
        try:
            course = Course(
                code=code,
                title=title,
                days=parse_days(days),
                start=parse_time(start),
                end=parse_time(end),
                location=location,
            )
        except ScheduleError as exc:
            raise ScheduleError(f"line {lineno}: {exc}") from exc
        schedule.courses.append(course)
    return schedule