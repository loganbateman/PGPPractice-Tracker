# PGP Practice Attendance Checker

A lightweight desktop app (Tkinter) that calculates who meets Purdue Grand Prix's minimum-practice requirement from Speedhive session results.

## What it does

- Accepts a Speedhive event URL (for example: `https://speedhive.mylaps.com/Events/3453310`).
- Finds session links under that event page.
- Parses each session table and counts a driver only if they posted a time.
- Shows a summary table with:
  - Driver name
  - Number of counted practices
  - Fastest recorded lap time across all processed sessions
  - Total laps completed across all processed sessions
  - Whether they meet the minimum required practices (default: 4)
  - Which sessions counted
- Exports:
  - `attendance_summary.csv`
  - `attendance_raw_records.csv` (includes per-session lap counts)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the app

```bash
python app.py
```

## How to test it first (recommended)

1. Open the app with `python app.py`.
2. Paste your Speedhive event URL (example: `https://speedhive.mylaps.com/Events/3453310`).
3. Leave minimum practices at `4` (or change if needed).
4. Click **Run Attendance Check**.
5. Confirm results:
   - A driver with no lap time should **not** be counted.
   - A driver with lap times in 4+ sessions should show **Meets Minimum = Yes**.
6. Export both CSVs and open them in Excel/Sheets to verify data looks right.

### Optional terminal smoke test (without UI)

```bash
python - <<'PY'
from scraper import collect_attendance

event_url = "https://speedhive.mylaps.com/Events/3453310"
result = collect_attendance(event_url=event_url, minimum_practices=4)

print("Sessions discovered:", len(result["session_links"]))
print("Drivers counted:", len(result["summary_rows"]))
print("Warnings:", len(result["errors"]))
print("Top 10 drivers by counted practices:")
for row in sorted(result["summary_rows"], key=lambda x: x["counted_practices"], reverse=True)[:10]:
    print(f"  {row['driver']}: {row['counted_practices']} ({row['meets_minimum']})")
PY
```

## Add this project to your GitHub

### Option A: push this existing folder to a new GitHub repo

1. Create a new empty repo on GitHub (no README/license).
2. In this folder, run:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

If you prefer SSH:

```bash
git remote add origin git@github.com:<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

### Option B: use GitHub Desktop

1. File → Add local repository (choose this folder).
2. Publish repository.
3. Choose public/private and click Publish.

## Build a Windows executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed app.py
```

The executable will be created in `dist/app.exe`.

## Notes about Speedhive parsing

Speedhive pages can vary by event/session layout. This app includes:

- automatic session discovery from an event page
- optional manual session links (paste one URL per line in the app)

If a session fails to parse due to a layout change, the app reports warnings and continues processing other sessions.
