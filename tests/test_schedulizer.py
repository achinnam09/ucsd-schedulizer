"""Tests for ucsd-schedulizer. Run with: pytest"""

from datetime import date, time
from pathlib import Path

import pytest

from schedulizer.ics_build import _first_meeting, build_calendar
from schedulizer.parse import (
    Course,
    ScheduleError,
    parse_days,
    parse_schedule,
    parse_time,
)


# ---------------------------------------------------------------------------
# parse_days
# ---------------------------------------------------------------------------

def test_parse_days_mwf():
    assert parse_days("MWF") == ["MO", "WE", "FR"]


def test_parse_days_tuth():
    assert parse_days("TuTh") == ["TU", "TH"]


def test_parse_days_mw():
    assert parse_days("MW") == ["MO", "WE"]


def test_parse_days_dedup():
    assert parse_days("MM") == ["MO"]


def test_parse_days_separators():
    assert parse_days("M/W/F") == ["MO", "WE", "FR"]


def test_parse_days_invalid():
    with pytest.raises(ScheduleError):
        parse_days("xyz")


# ---------------------------------------------------------------------------
# parse_time
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("10:00",   time(10, 0)),
    ("10:00am", time(10, 0)),
    ("9:30a",   time(9, 30)),
    ("2:15p",   time(14, 15)),
    ("3:00p",   time(15, 0)),
    ("12:00am", time(0, 0)),
    ("12:30pm", time(12, 30)),
])
def test_parse_time(raw, expected):
    assert parse_time(raw) == expected


def test_parse_time_invalid():
    with pytest.raises(ScheduleError):
        parse_time("99:00")


# ---------------------------------------------------------------------------
# parse_schedule (plain text)
# ---------------------------------------------------------------------------

def test_parse_schedule_basic():
    text = """
    # term-start: 2026-03-30
    # term-end:   2026-06-06
    DSC190 | Tools of the Trade | MWF | 11:00a | 11:50a | PODEM 1A18
    """
    sched = parse_schedule(text)
    assert sched.term_start == date(2026, 3, 30)
    assert sched.term_end == date(2026, 6, 6)
    assert len(sched.courses) == 1
    assert sched.courses[0].code == "DSC190"
    assert sched.courses[0].location == "PODEM 1A18"


def test_parse_schedule_holiday():
    text = """
    # term-start: 2026-03-30
    # term-end:   2026-06-06
    # holiday: 2026-05-25
    DSC190 | Tools of the Trade | MWF | 11:00a | 11:50a
    """
    sched = parse_schedule(text)
    assert date(2026, 5, 25) in sched.holidays


def test_parse_schedule_no_location():
    text = "DSC190 | Tools | MWF | 11:00a | 11:50a"
    sched = parse_schedule(text)
    assert sched.courses[0].location == ""


def test_parse_schedule_too_few_fields():
    with pytest.raises(ScheduleError):
        parse_schedule("DSC190 | Tools | MWF")


# ---------------------------------------------------------------------------
# _first_meeting
# ---------------------------------------------------------------------------

def test_first_meeting_mwf():
    # 2026-03-30 is a Monday — first MWF meeting should be that same day
    course = Course("X", "x", ["MO", "WE", "FR"], time(11), time(12))
    assert _first_meeting(course, date(2026, 3, 30)) == date(2026, 3, 30)


def test_first_meeting_tuth():
    # 2026-03-30 is a Monday — first TuTh meeting should be Tuesday Mar 31
    course = Course("Y", "y", ["TU", "TH"], time(9, 30), time(10, 50))
    assert _first_meeting(course, date(2026, 3, 30)) == date(2026, 3, 31)


# ---------------------------------------------------------------------------
# build_calendar
# ---------------------------------------------------------------------------

def test_build_calendar_event_count():
    sched = parse_schedule(
        "# term-start: 2026-03-30\n"
        "# term-end:   2026-06-06\n"
        "DSC190 | Tools | MWF | 11:00a | 11:50a | PODEM 1A18\n"
        "DSC152 | Stats | TuTh | 9:30a | 10:50a | HSS 1330\n"
    )
    cal = build_calendar(sched, sched.term_start, sched.term_end)
    events = [c for c in cal.subcomponents if c.name == "VEVENT"]
    assert len(events) == 2


def test_build_calendar_rrule_present():
    sched = parse_schedule(
        "# term-start: 2026-03-30\n"
        "# term-end:   2026-06-06\n"
        "DSC190 | Tools | MWF | 11:00a | 11:50a\n"
    )
    cal = build_calendar(sched, sched.term_start, sched.term_end)
    ical_text = cal.to_ical().decode()
    assert "FREQ=WEEKLY" in ical_text
    assert "BYDAY=MO,WE,FR" in ical_text


def test_build_calendar_timezone():
    sched = parse_schedule(
        "# term-start: 2026-03-30\n"
        "# term-end:   2026-06-06\n"
        "DSC190 | Tools | MWF | 11:00a | 11:50a\n"
    )
    cal = build_calendar(sched, sched.term_start, sched.term_end)
    ical_text = cal.to_ical().decode()
    assert "America/Los_Angeles" in ical_text


def test_build_calendar_bad_times():
    sched = parse_schedule(
        "# term-start: 2026-03-30\n"
        "# term-end:   2026-06-06\n"
        "BAD | x | MWF | 11:00a | 10:00a\n"
    )
    with pytest.raises(ScheduleError):
        build_calendar(sched, sched.term_start, sched.term_end)