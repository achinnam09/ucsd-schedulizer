"""Build an iCalendar (.ics) document from a parsed Schedule."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from icalendar import Alarm, Calendar, Event

from .parse import Course, Schedule, ScheduleError

PACIFIC = ZoneInfo("America/Los_Angeles")


def _first_meeting(course: Course, term_start: date) -> date:
    """Earliest date on/after term_start that the course meets."""
    candidates = []
    for weekday in course.weekdays():
        delta = (weekday - term_start.weekday()) % 7
        candidates.append(term_start + timedelta(days=delta))
    return min(candidates)


def _uid(course: Course, first: date) -> str:
    seed = f"{course.code}|{course.start}|{first.isoformat()}"
    digest = hashlib.sha1(seed.encode()).hexdigest()[:12]
    return f"{digest}-{course.code.lower().replace(' ', '')}@ucsd-schedulizer"


def _holiday_exdates(course: Course, holidays: list[date]) -> list[datetime]:
    meeting_weekdays = set(course.weekdays())
    exdates = []
    for day in holidays:
        if day.weekday() in meeting_weekdays:
            exdates.append(datetime.combine(day, course.start, PACIFIC))
    return exdates


def build_event(
    course: Course,
    term_start: date,
    term_end: date,
    holidays: list[date],
    reminder_minutes: int | None = None,
) -> Event:
    first = _first_meeting(course, term_start)
    start_dt = datetime.combine(first, course.start, PACIFIC)
    end_dt = datetime.combine(first, course.end, PACIFIC)
    if end_dt <= start_dt:
        raise ScheduleError(
            f"{course.code}: end time {course.end} is not after "
            f"start {course.start}"
        )

    event = Event()
    event.add("summary", f"{course.code} - {course.title}")
    event.add("dtstart", start_dt)
    event.add("dtend", end_dt)
    if course.location:
        event.add("location", course.location)
    event.add("uid", _uid(course, first))
    event.add("dtstamp", datetime.now(tz=timezone.utc))

    # Recur weekly on every meeting day until the last instant of the term
    until = datetime.combine(
        term_end, time(23, 59, 59), PACIFIC
    ).astimezone(timezone.utc)
    event.add(
        "rrule",
        {"freq": "weekly", "byday": course.days, "until": until},
    )

    exdates = _holiday_exdates(course, holidays)
    if exdates:
        event.add("exdate", exdates)

    if reminder_minutes:
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", f"{course.code} starting soon")
        alarm.add("trigger", timedelta(minutes=-reminder_minutes))
        event.add_component(alarm)

    return event


def build_final_exam_event(
    course_code: str,
    course_title: str,
    exam_date: date,
    start: time,
    end: time,
    location: str = "",
) -> Event:
    """Build a single (non-recurring) event for a final exam."""
    start_dt = datetime.combine(exam_date, start, PACIFIC)
    end_dt = datetime.combine(exam_date, end, PACIFIC)

    event = Event()
    event.add("summary", f"FINAL - {course_code} {course_title}")
    event.add("dtstart", start_dt)
    event.add("dtend", end_dt)
    if location:
        event.add("location", location)
    seed = f"final|{course_code}|{exam_date.isoformat()}"
    digest = hashlib.sha1(seed.encode()).hexdigest()[:12]
    event.add("uid", f"{digest}-final@ucsd-schedulizer")
    event.add("dtstamp", datetime.now(tz=timezone.utc))

    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", f"FINAL EXAM: {course_code} today")
    alarm.add("trigger", timedelta(minutes=-30))
    event.add_component(alarm)

    return event


def build_calendar(
    schedule: Schedule,
    term_start: date,
    term_end: date,
    reminder_minutes: int | None = None,
) -> Calendar:
    if term_end < term_start:
        raise ScheduleError("term end date is before term start date")
    if not schedule.courses:
        raise ScheduleError("no courses to add to the calendar")

    cal = Calendar()
    cal.add("prodid", "-//ucsd-schedulizer//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "UCSD Schedule")
    cal.add("x-wr-timezone", "America/Los_Angeles")

    for course in schedule.courses:
        cal.add_component(
            build_event(
                course, term_start, term_end,
                schedule.holidays, reminder_minutes,
            )
        )

    add_tz = getattr(cal, "add_missing_timezones", None)
    if callable(add_tz):
        add_tz()

    return cal


def calendar_to_bytes(cal: Calendar) -> bytes:
    return cal.to_ical()