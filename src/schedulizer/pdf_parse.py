"""Parse a UCSD WebReg 'print schedule' PDF into a Schedule object.

The WebReg PDF contains a table with these columns (0-indexed):
    0:  Subject/Course  e.g. "DSC 152", "MATH 171B"
    1:  Title
    2:  Section Code    e.g. "B00", "C01"
    3:  Type            "LE" = lecture, "DI" = discussion, "FI" = final exam
    4:  Instructor
    5:  Grade Option
    6:  Units
    7:  Days            e.g. "TuTh", "MWF", "Sa 06/06/2026"
    8:  Time            e.g. "9:30a-10:50a"
    9:  BLDG
    10: Room
    11: Status          e.g. "Enrolled"

We only extract rows where Type == "LE" (lectures) for recurring events,
and Type == "FI" (finals) as one-time events.
Rows where Type == "DI" (discussion) are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path

from .parse import Course, Schedule, ScheduleError, parse_days, parse_time

# Column indices in the WebReg table
COL_COURSE = 0
COL_TITLE = 1
COL_SECTION = 2
COL_TYPE = 3
COL_DAYS = 7
COL_TIME = 8
COL_BLDG = 9
COL_ROOM = 10

# WebReg table header text — used to find and skip the header row
HEADER_MARKER = "Subject"

# Quarter name -> (term_start, term_end) for auto-detection from PDF title.
# Update these each year as UCSD posts its academic calendar.
QUARTER_DATES: dict[str, tuple[str, str]] = {
    "fall 2024":   ("2024-09-26", "2024-12-06"),
    "winter 2025": ("2025-01-06", "2025-03-14"),
    "spring 2025": ("2025-03-31", "2025-06-07"),
    "fall 2025":   ("2025-09-25", "2025-12-05"),
    "winter 2026": ("2026-01-05", "2026-03-13"),
    "spring 2026": ("2026-03-30", "2026-06-06"),
    "fall 2026":   ("2026-09-24", "2026-12-04"),
}


def _parse_webreg_time(raw: str) -> tuple[time, time]:
    """Parse a WebReg time range like '9:30a-10:50a' or '11:00a-11:50a'."""
    raw = raw.strip()
    m = re.match(r"(.+?)\s*-\s*(.+)", raw)
    if not m:
        raise ScheduleError(f"cannot parse time range {raw!r}")
    return parse_time(m.group(1)), parse_time(m.group(2))


def _parse_final_day_time(days_raw: str, time_raw: str) -> tuple[date, time, time]:
    """Parse a final exam row's day/time fields.

    days_raw looks like 'Sa 06/06/2026' or 'F 06/12/2026' or 'W 06/10/2026'.
    time_raw looks like '3:00p-5:59p'.
    """
    # Extract the date portion MM/DD/YYYY
    m = re.search(r"(\d{2}/\d{2}/\d{4})", days_raw)
    if not m:
        raise ScheduleError(f"cannot parse final exam date from {days_raw!r}")
    exam_date = date.fromisoformat(
        # convert MM/DD/YYYY -> YYYY-MM-DD
        "{2}-{0}-{1}".format(*m.group(1).split("/"))
    )
    start, end = _parse_webreg_time(time_raw)
    return exam_date, start, end


def _detect_quarter(title_text: str) -> tuple[date, date] | tuple[None, None]:
    """Try to infer term dates from the PDF title line."""
    lower = title_text.lower()
    for quarter, (start, end) in QUARTER_DATES.items():
        if quarter in lower:
            return date.fromisoformat(start), date.fromisoformat(end)
    return None, None


def _extract_table(pdf_path: Path) -> list[list[str | None]]:
    """Use pdfplumber to pull the schedule table from the PDF."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise ScheduleError(
            "pdfplumber is required for PDF parsing. "
            "Install it with: uv add pdfplumber"
        ) from exc

    rows: list[list[str | None]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            # The schedule table is the last one on the page (index -1).
            # The first table is a single-cell block containing the full
            # page text; we skip it.
            if len(tables) >= 2:
                rows.extend(tables[-1])
            elif len(tables) == 1 and len(tables[0]) > 2:
                rows.extend(tables[0])
    return rows


@dataclass
class _PdfSchedule(Schedule):
    """Schedule subclass that also carries parsed final exam data."""
    finals: list[dict] = field(default_factory=list)


def parse_pdf_schedule(pdf_path: Path) -> _PdfSchedule:
    """Parse a WebReg PDF into a Schedule (with finals attached)."""
    rows = _extract_table(pdf_path)
    schedule = _PdfSchedule()

    # Try to detect term dates from the title row
    if rows:
        first_cell = (rows[0][0] or "") if rows[0] else ""
        schedule.term_start, schedule.term_end = _detect_quarter(first_cell)

    # Track the current course code/title across continuation rows
    current_code: str = ""
    current_title: str = ""

    for row in rows:
        # Pad short rows so index access is always safe
        row = list(row) + [None] * (11 - len(row))

        def cell(i: int) -> str:
            val = row[i]
            return val.strip().replace("\n", " ") if val else ""

        # Skip header row
        if cell(COL_COURSE).startswith(HEADER_MARKER):
            continue

        row_type = cell(COL_TYPE).upper()

        # Update running course code/title when a new course starts
        if cell(COL_COURSE):
            current_code = cell(COL_COURSE)
        if cell(COL_TITLE) and row_type == "LE":
            current_title = cell(COL_TITLE)

        # Only process lecture and final exam rows
        if row_type not in ("LE", "FI"):
            continue

        days_raw = cell(COL_DAYS)
        time_raw = cell(COL_TIME)

        if not days_raw or not time_raw:
            continue

        # --- Final exam row ---
        if row_type == "FI":
            try:
                exam_date, start, end = _parse_final_day_time(days_raw, time_raw)
                location = (cell(COL_BLDG) + " " + cell(COL_ROOM)).strip()
                schedule.finals.append({
                    "course_code": current_code,
                    "course_title": current_title,
                    "exam_date": exam_date,
                    "start": start,
                    "end": end,
                    "location": location,
                })
            except ScheduleError:
                # If we can't parse a final, skip it rather than crashing
                continue
            continue

        # --- Lecture row ---
        try:
            start, end = _parse_webreg_time(time_raw)
            days = parse_days(days_raw)
            location = (cell(COL_BLDG) + " " + cell(COL_ROOM)).strip()
            course = Course(
                code=current_code,
                title=current_title,
                days=days,
                start=start,
                end=end,
                location=location,
            )
            schedule.courses.append(course)
        except ScheduleError:
            continue

    if not schedule.courses:
        raise ScheduleError(
            "no lecture courses found in the PDF. "
            "Make sure you are using the WebReg 'print schedule' view."
        )

    return schedule