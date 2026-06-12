"""Command-line interface for ucsd-schedulizer."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .ics_build import build_calendar, calendar_to_bytes
from .parse import Schedule, ScheduleError, parse_schedule

SAMPLE_SCHEDULE = """\
# UCSD schedule for ucsd-schedulizer
# Format:  CODE | Title | Days | Start | End | Location
# Days: M Tu W Th F  e.g. MWF, TuTh, MW
# Times: 11:00a, 2:15p, 9:30a

# term-start: 2026-03-31
# term-end:   2026-06-13

# holiday: 2026-05-25

DSC190   | Tools of the Trade          | MWF  | 11:00a | 11:50a | PODEM 1A18
MATH171B | Intro Num Optimiz/Nonlinear | MWF  | 3:00p  | 3:50p  | CENTR 113
SYN100   | Engaging/Changing Planet    | MW   | 12:30p | 1:50p  | HSS 7077
DSC152   | Applied Stat. Data Analysis | TuTh | 9:30a  | 10:50a | HSS 1330
"""


def _resolve_dates(
    schedule: Schedule, start: str | None, end: str | None
) -> tuple[date, date]:
    term_start = date.fromisoformat(start) if start else schedule.term_start
    term_end = date.fromisoformat(end) if end else schedule.term_end
    if term_start is None or term_end is None:
        raise ScheduleError(
            "term start/end dates are required. Provide them with --start / "
            "--end, or via '# term-start:' / '# term-end:' lines in the file."
        )
    return term_start, term_end


def _load(path: str) -> Schedule:
    """Load a schedule from a .txt or .pdf file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if p.suffix.lower() == ".pdf":
        from .pdf_parse import parse_pdf_schedule
        return parse_pdf_schedule(p)
    return parse_schedule(p.read_text(encoding="utf-8"))


def cmd_build(args: argparse.Namespace) -> int:
    schedule = _load(args.input)
    term_start, term_end = _resolve_dates(schedule, args.start, args.end)
    cal = build_calendar(schedule, term_start, term_end, args.reminder)

    # Add final exam events if parsed from PDF
    if hasattr(schedule, "finals") and schedule.finals:
        from .ics_build import build_final_exam_event
        for f in schedule.finals:
            cal.add_component(build_final_exam_event(**f))

    out_path = (
        Path(args.output) if args.output
        else Path(args.input).with_suffix(".ics")
    )
    out_path.write_bytes(calendar_to_bytes(cal))
    n = len(schedule.courses)
    print(
        f"Wrote {out_path}  ({n} course{'s' if n != 1 else ''}, "
        f"{term_start} to {term_end})"
    )
    print("Import: Google Calendar -> Settings -> Import & export -> Import.")
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    schedule = _load(args.input)
    try:
        term_start, term_end = _resolve_dates(schedule, args.start, args.end)
        term_line = f"Term: {term_start} to {term_end}"
    except ScheduleError:
        term_line = "Term: (dates not set — use --start and --end)"
    print(term_line)
    if schedule.holidays:
        print("No class:", ", ".join(d.isoformat() for d in schedule.holidays))
    print("-" * 52)
    for c in schedule.courses:
        days = "".join(c.days)
        loc = f"  @ {c.location}" if c.location else ""
        print(
            f"{c.code:<12} {days:<12} "
            f"{c.start.strftime('%H:%M')}-{c.end.strftime('%H:%M')}{loc}"
        )
        print(f"             {c.title}")
    if hasattr(schedule, "finals") and schedule.finals:
        print("\nFinals:")
        for f in schedule.finals:
            print(
                f"  {f['course_code']:<10} {f['exam_date']}  "
                f"{f['start'].strftime('%H:%M')}-{f['end'].strftime('%H:%M')}"
                + (f"  @ {f['location']}" if f.get('location') else "")
            )
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    out_path = Path(args.output)
    if out_path.exists() and not args.force:
        print(
            f"{out_path} already exists (use --force to overwrite).",
            file=sys.stderr,
        )
        return 1
    out_path.write_text(SAMPLE_SCHEDULE, encoding="utf-8")
    print(
        f"Wrote example schedule to {out_path}.\n"
        f"Edit it, then run:  schedulize build {out_path}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schedulize",
        description=(
            "Turn a UCSD WebReg schedule (PDF or plain text) "
            "into a Google Calendar .ics file."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- build ---
    b = sub.add_parser("build", help="generate an .ics file")
    b.add_argument("input", help="path to schedule (.pdf or .txt)")
    b.add_argument("-o", "--output", help="output .ics path (default: <input>.ics)")
    b.add_argument("--start", help="term start date YYYY-MM-DD (overrides file)")
    b.add_argument("--end",   help="term end date YYYY-MM-DD (overrides file)")
    b.add_argument(
        "--reminder", type=int, metavar="MIN",
        help="popup reminder MIN minutes before each class",
    )
    b.set_defaults(func=cmd_build)

    # --- preview ---
    p = sub.add_parser("preview", help="print parsed courses without writing a file")
    p.add_argument("input", help="path to schedule (.pdf or .txt)")
    p.add_argument("--start", help="term start date YYYY-MM-DD")
    p.add_argument("--end",   help="term end date YYYY-MM-DD")
    p.set_defaults(func=cmd_preview)

    # --- sample ---
    s = sub.add_parser("sample", help="write an example .txt schedule to edit")
    s.add_argument("-o", "--output", default="schedule.txt")
    s.add_argument("--force", action="store_true", help="overwrite if exists")
    s.set_defaults(func=cmd_sample)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ScheduleError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())