# PGP Practice Session Tracker

A lightweight desktop app (Tkinter) for viewing a **single Speedhive session** and ranking drivers by best lap.

## What's changed

This app is now intentionally simplified:
- No event-level multi-day aggregation.
- No minimum-practice cutoff logic.
- One URL in, one session leaderboard out.

## Features

- Paste one Speedhive session URL (example: `https://speedhive.mylaps.com/Sessions/14572181`).
- Pulls official session CSV data from the Speedhive event-results API.
- Ranks drivers by fastest lap (then laps, then name).
- Displays:
  - Position
  - Driver
  - Kart number
  - Best lap
  - Laps
- Export current session leaderboard to CSV.
- Purdue-inspired black and gold UI styling.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

## Quick terminal smoke test

```bash
python - <<'PY'
from scraper import collect_session_results

sample = "https://speedhive.mylaps.com/Sessions/14572181"
result = collect_session_results(sample)

print("Session:", result["session_name"])
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
