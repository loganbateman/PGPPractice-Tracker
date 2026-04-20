# PGP Session Participation Tracker

A lightweight desktop app (Tkinter) that pulls Speedhive event sessions and optional individual session URLs, then summarizes driver participation.

## What it calculates

For each driver with a recorded lap time, the app shows:
- Kart Number
- Driver
- Fast Lap
- Total Laps
- Session Attendance
- Over Minimum? (Yes/No based on your required minimum, default 4)
- Sessions Attended

## Features

- Paste a Speedhive **event** URL (example: `https://speedhive.mylaps.com/events/2978694`) or a single **session** URL in the main URL field.
- Optionally paste more Speedhive **session** URLs or IDs to include in the comparison (examples: `https://speedhive.mylaps.com/sessions/11963004`, `https://speedhive.mylaps.com/sessions/11963214`).
- Event imports include practice, qualifying, race, and other timed session types.
- Set minimum required sessions (default `4`).
- Only counts attendance when a driver has a recorded time in a session.
- Sort any column in the results table.
- Export participation results to Excel (`.xlsx`) or CSV.
- Purdue-inspired black and gold UI styling.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

If you see `ModuleNotFoundError: No module named 'openpyxl'`, your active Python
environment does not have dependencies installed yet. Re-run:

```bash
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

## Quick terminal smoke test

```bash
python - <<'PY'
from scraper import collect_participation

event_url = "https://speedhive.mylaps.com/events/2978694"
session_urls = """
https://speedhive.mylaps.com/sessions/11963004
"""
result = collect_participation(event_url, minimum_sessions=4, session_urls=session_urls)

print("Event:", result["event_name"])
print("Sessions:", result["total_sessions"])
print("Drivers:", len(result["results"]))
print("Top 5:")
for row in result["results"][:5]:
    print(row)
PY
```

## Build a Windows executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed app.py
```
