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

## Setup (Windows PowerShell)

> If you cloned with `git clone ...`, you **must** `cd` into the repo folder before running `python app.py`.

```powershell
git clone https://github.com/<your-username>/PGPPractice-Tracker.git
cd PGPPractice-Tracker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Setup (macOS / Linux)

```bash
git clone https://github.com/<your-username>/PGPPractice-Tracker.git
cd PGPPractice-Tracker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run the app

```bash
python app.py
```

If the app opens, you're good. If it fails, check troubleshooting below.

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

- automatic session discovery from Speedhive's Event Results API
- optional manual session links (paste one URL per line in the app)

If a session fails to parse due to a layout change, the app reports warnings and continues processing other sessions.

## Troubleshooting

### `ModuleNotFoundError: No module named 'pandas'`

This usually means Python is running a **different `app.py`** than this repo's file.
Your screenshot shows `File "D:\\Downloads\\app.py"`, which is not the cloned repo path.

Fix:

```powershell
cd D:\Downloads\PGPPractice-Tracker
.\.venv\Scripts\Activate.ps1
python app.py
```

Optional sanity check to confirm you're in the right folder:

```powershell
pwd
dir app.py
```

The app in this repo does **not** require `pandas`.

### `ModuleNotFoundError` for another package

Reinstall deps from inside the repo and active venv:

```bash
python -m pip install -r requirements.txt
```

### PowerShell blocks activate script

Run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### `python` command not found

Try:

```powershell
py -3 -m venv .venv
py -3 app.py
```
