# ucsd-schedulizer

A command-line tool that converts a UCSD WebReg schedule into a `.ics` calendar
file you can import directly into Google Calendar. Feed it either your WebReg
PDF (downloaded from the "print schedule" view) or a plain-text file you fill
out manually — it handles recurring weekly events, correct Pacific timezone,
and final exam one-time events automatically.

## Usage

Install with `uv`:

```
uv add "git+https://github.com/<your-username>/ucsd-schedulizer.git"
```

### Option A: Use your WebReg PDF (recommended)

Download your schedule PDF from WebReg's print view, then run:

```
schedulize build webregMain.pdf --start 2026-03-30 --end 2026-06-06
```

Add a popup reminder before every class:

```
schedulize build webregMain.pdf --start 2026-03-30 --end 2026-06-06 --reminder 10
```

Preview what was parsed before generating the file:

```
schedulize preview webregMain.pdf --start 2026-03-30 --end 2026-06-06
```

### Option B: Use a plain-text file

Generate a starter file to edit:

```
schedulize sample -o schedule.txt
```

Each course is one line in this format:

```
CODE | Title | Days | Start | End | Location
```

Days use `M Tu W Th F` (e.g. `MWF`, `TuTh`, `MW`). Times accept `9:30a`,
`2:15p`, or `14:00`. Set your term dates and holidays at the top:

```
# term-start: 2026-03-30
# term-end:   2026-06-06
# holiday:    2026-05-25
```

Then build:

```
schedulize build schedule.txt
```

### Importing into Google Calendar

Once you have the `.ics` file, import it via:
**Google Calendar → Settings → Import & export → Import**

### All commands

```
schedulize build FILE [-o OUT] [--start D] [--end D] [--reminder MIN]
schedulize preview FILE [--start D] [--end D]
schedulize sample [-o FILE]
```