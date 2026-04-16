# PGP Practice Participation Tracker

A lightweight desktop app (Tkinter) that pulls **all practice sessions in a Speedhive event** and summarizes driver participation.

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

- Paste one Speedhive **event** URL (example: `https://speedhive.mylaps.com/Events/3453310`).
- Set minimum required practices (default `4`).
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
from scraper import collect_event_participation

sample = "https://speedhive.mylaps.com/Events/3453310"
result = collect_event_participation(sample, minimum_sessions=4)

print("Event:", result["event_name"])
print("Practice sessions:", result["total_practice_sessions"])
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
