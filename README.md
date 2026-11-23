# Logistics Hub Tracker

[![Tests](https://github.com/Ennycrus/logistics-hub-tracker/actions/workflows/tests.yml/badge.svg)](https://github.com/Ennycrus/logistics-hub-tracker/actions/workflows/tests.yml)

A web app for running one logistics hub's day: import gun-scanner files, track the delivery status of every shipment, and produce two accurate daily reports (**TEMU** and **Base**) in the company's 11-column format, a weekly delivery summary, and the manager's Saturday hub report.

Built with **Django REST Framework**, **React (Vite)**, **SQLite** and **openpyxl**.

## Features

- **Scanner import with preview** - finds the waybill column automatically, flags duplicates, invalid rows and already-closed shipments. The same file can never be imported twice.
- **Paste from Google Sheets** - copy the waybill column and paste it on the Import page; it goes through the same preview and checks as a file.
- **No waybill skipped silently** - a cell holding several waybills is split, waybills found in other columns are reported (with an option to import all columns), and the preview warns about formula cells with no saved value and about other sheets that were not read.
- **Import history by week** - one Monday-Sunday week at a time, with that week's totals.
- **Stock count** - scan every parcel on the shelves and compare with the app: missing from shelves, scanned but delivered or left the hub, and scanned but never imported. Nothing is saved; fix each row and check again.
- **Undo a wrong import** - removes the import and only the shipments it created. Refused if any of them already has a status update, is in a finalized report, or appears in a later import.
- **Two shipment types, sorted by waybill prefix** - `3034...` = TEMU, `1...` = Base. Waybills with any other prefix make the import ask: Base, TEMU or Skip.
- **Status tracking with full history** - every change is recorded with its date. Failed deliveries need a reason; "Other" needs an explanation; changing a delivered shipment needs a note. A date before the shipment arrived is refused, and recording a change on a day whose report is already finalized asks first.
- **Remembered date** - the date you record results for is kept while you work, with a clear "Recording for ..." notice and a **Use today** button.
- **Who delivered it** - marking a shipment Delivered asks for Rider, Captain or 3PL. It can be filled in later for older deliveries without a note; the delivery keeps its original date.
- **Search by the last four digits** - typing exactly 4 digits finds waybills that end with them.
- **Check filters on Shipments** - "Delivered, nobody recorded" and "Stuck: no update for 7+ days", linked from the Saturday report warnings. Delivered shipments are hidden unless you tick **Show delivered**, choose a delivered filter or search.
- **Track button** - opens the shipment on the courier's public tracking page (the address is set in Settings).
- **Bulk updates, all or nothing** - if one selected shipment breaks a rule, nothing is saved.
- **Separate daily reports for TEMU and Base** - own figures, carry-forward, transport (vans, bikes, 3PL), reasons and finalize.
- **Reconciliation check** - Delivered + Current Day + Left hub (rerouted / initiated return) must equal Total Available.
- **Frozen reports** - a finalized report never changes. Corrections create a new version (v2, v3...) and keep the original.
- **Weekly delivery (Monday to Saturday)** - delivered per day, daily rates, and the week's delivery rate for TEMU and Base, with an Excel download.
- **Saturday hub report** - the manager's six items (TEMU pending, Base pending, delivered by riders/captains/3PLs, not in hub, fuel, incidents), ready to copy into WhatsApp or email and download as Excel. Fuel and incidents are entered each day on the Daily Report page, and every change to them is kept. Every save of the report is kept as a version.
- **Dashboard** - today's figures, this week's delivery rate and what still needs attention.
- **Export** - download the report as Excel, or copy the row straight into a Google Sheet.
- **Pending list, Report history, Settings** - statuses and failure reasons are editable.
- **Login protection** - automatic log-out after 15 minutes without activity, login locked for 5 minutes after 5 wrong passwords, and a Change password form in Settings.
- **Backups** - a daily automatic backup, a second copy in another folder (e.g. Google Drive), and a `check_backup` command that proves a backup can be restored.
- **Reset command** for starting over safely.

## How the report figures are calculated

Each report (TEMU or Base) only counts shipments of its own type.

| Figure | Meaning |
| --- | --- |
| Inbound | Shipments first scanned on this date |
| Old Pending | Shipments first scanned earlier and still at the hub at the end of the previous day |
| Total Available | Inbound + Old Pending |
| Delivered | Delivered on this date |
| Current Day | Still at the hub at the end of the day (not checked, outstanding or returned) |
| Return | Delivery Unsuccessful or Returned to Hub recorded on this date (also counted inside Current Day) |
| Reasons | Failure reasons of this day's unsuccessful deliveries, grouped with counts, e.g. "Customer unavailable - 3" |

Shipments that left the hub (Rerouted, Initiated Return, or any status in the **Left hub** category) are not carried forward. Statuses are worked out from the history using the date each change happened, so past dates stay correct.

## How the weekly delivery rate is calculated

The delivery week runs **Monday to Saturday**, and only **finalized** reports are used, so the week always matches what was sent to the company.

| Figure | Meaning |
| --- | --- |
| Daily rate | Delivered / Total Available for that day |
| Delivered this week | Monday + ... + Saturday delivered |
| Available this week | Monday's Old Pending + every Inbound from Monday to Saturday |
| Weekly delivery rate | Delivered this week / Available this week |

The daily Total Available figures are not added up: a shipment that waits three days appears in three of them, so the sum would count it three times. Days that are not finalized are shown as missing, and without Monday there is no weekly rate.

## How the Saturday hub report is calculated

One report for the whole hub (TEMU and Base together), for the Monday-Saturday week.

| Item | Meaning |
| --- | --- |
| 1. TEMU pending in hub | TEMU shipments not delivered yet (Not Yet Checked, Pending/Unsuccessful, Returned) at the time of the report |
| 2. Base pending in hub | The same for Base |
| 3. Delivered | Shipments delivered Monday to Saturday (and still delivered), split into Riders, Captains and 3PLs |
| 4. Not in hub (awaiting update) | Shipments out with riders with no result yet (Not Yet Checked). These are also inside items 1 and 2 |
| 5. Fuel used | Litres for riders and captains, added up from the daily entries |
| 6. Incidents | Every day's incident note, plus any extra notes added on Saturday |

**Save** freezes all the figures; saving again adds a new version and keeps the earlier ones. Before sending, the page warns you if a day has no fuel entered, if delivered shipments have nobody recorded, if shipments have had no update for 7 days or more (they may be inflating items 1, 2 and 4), or if item 3 does not match the Delivered total of your finalized daily reports. Saving while a warning is open asks you to confirm first.

**Sundays:** the report goes out on Saturday evening, so anything dated on a Sunday (deliveries, fuel, incidents) is counted in the next week's report. Nothing done on a Sunday is left out.

## Project structure

```
hub-tracker/
  backend/                 Django project
    config/                settings and URLs
    core/                  hub settings, statuses, failure reasons, login and passwords
    shipments/             shipments, status history, scanner imports and undo
    reports/               reporting days, calculations, reports, weekly summary, Saturday report, Excel export
    .env.example           template for your private .env file
    requirements.txt
  frontend/                React app (Vite)
    src/api/client.js      the one file that talks to Django
    src/pages/             Dashboard, Import, Shipments, Pending, Stock Count, Daily Report, Weekly, Saturday Report, History, Settings
    src/components/        layout, status editor, dialogs, Base/TEMU switch
  docs/
    DAILY_ROUTINE.md       step-by-step daily guide
```

The business rules live in `services/` folders (for example `shipments/services/status_service.py`, `shipments/services/import_service.py`, `shipments/services/stock_count.py`, `reports/services/calculations.py`, `reports/services/weekly.py` and `reports/services/weekly_hub.py`), so the API views stay thin.

## Setup (Windows)

You need **Python 3.12+**, **Node.js 20+** and **Git**.

### 1. Backend

```powershell
git clone https://github.com/Ennycrus/logistics-hub-tracker.git
cd logistics-hub-tracker\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Make a secret key and paste it into `.env` (between the single quotes):

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Then create the database and your login:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### 2. Frontend (in a second terminal)

```powershell
cd logistics-hub-tracker\frontend
npm install
npm run dev
```

Open **http://localhost:5173** and log in.

## Daily use

See **[docs/DAILY_ROUTINE.md](docs/DAILY_ROUTINE.md)**: import the files, update statuses, check Pending, finalize the TEMU and Base reports, enter the day's fuel and incidents, back up, and on Saturday count the shelves and send the Saturday report.

## Useful commands

Run these in `backend` with the venv active.

| Command | What it does |
| --- | --- |
| `python manage.py backup_db` | Safe copy of the database into `backend/backups/` (keeps the newest 30), plus a second copy in `BACKUP_COPY_DIR` if it is set in `.env` |
| `python manage.py check_backup` | Opens the newest backup read-only, checks it is healthy and compares its counts with the app (`--dir` for another folder, or give a file) |
| `python manage.py restore_db` | Restores a backup (the newest by default, or give a file). Saves the current database to `backups/pre_restore_...` first, so a restore can itself be undone. Stop Django before running it; `--yes` skips the confirmation |
| `python manage.py reset_data` | Deletes all shipments, imports, reports, fuel logs and Saturday reports after a backup; keeps users and settings |
| `python manage.py test` | Runs the test suite (363 tests, under a minute) |

Older command-line report tools (`open_day`, `day_summary`, `finalize_report`, `export_report`...) also exist and work on the TEMU report.

## API overview

All endpoints need a logged-in user. Report endpoints take `?type=temu` or `?type=base` (TEMU if left out).

| Endpoint | Purpose |
| --- | --- |
| `GET /api/shipments/` | List shipments (`search`, `category`, `type`, `delivered_by`, `stale_days`, `hide_delivered`, `page`) |
| `POST /api/shipments/<id>/status/` | Change one status |
| `POST /api/shipments/bulk-status/` | Change many, all or nothing |
| `POST /api/imports/preview/` | Read a scanner file (.xlsx, .csv or a pasted list), save nothing (`all_columns` to read every column) |
| `POST /api/imports/confirm/` | Import it (`unknown_type`: base, temu or skip; `all_columns`) |
| `GET /api/imports/?week=` | Import history for the Monday-Sunday week containing that date |
| `POST /api/stock-count/` | Compare a shelf scan with the app, save nothing (`shipment_type`: temu or base) |
| `DELETE /api/imports/<id>/` | Undo an import (refused if its shipments were worked on) |
| `GET/PATCH /api/reports/<date>/` | The day's draft or finalized report |
| `POST /api/reports/<date>/finalize/` | Freeze the report |
| `POST /api/reports/<date>/correct/` | Start a corrected version |
| `GET /api/reports/<date>/download/` | Excel file |
| `GET /api/reports/` | Report history |
| `GET /api/reports/weekly/?date=` | The Monday-Saturday week containing that date |
| `GET /api/reports/weekly/download/?date=` | The week as an Excel file |
| `GET/POST /api/reports/daily-log/?date=` | One day's fuel (litres) and incidents, with every earlier save |
| `GET/POST /api/reports/weekly-hub/?date=` | The Saturday report; POST saves a new version (`&version=` to open an older one) |
| `GET /api/reports/weekly-hub/download/?date=` | The Saturday report as an Excel file |
| `GET /api/reports/weekly-hub/history/` | Every saved Saturday report version |
| `POST /api/auth/change-password/` | Change your password (needs the current one) |

## Security notes

- The secret key lives in `backend/.env`, which is never committed. Only `.env.example` is in the repository.
- The database (`*.sqlite3`), backups and scanner files (`*.xlsx`) are ignored by Git, so real shipment data never goes to GitHub. The only copy that leaves the laptop is the backup copy in your own `BACKUP_COPY_DIR` folder, if you set one.
- `DEBUG` is off unless `.env` turns it on.
- Only the website's login session can reach the API, and Excel files are read with `defusedxml` protection.
- After **15 minutes without activity** you are logged out, both on the website and on the server. Logging out also ends the session on the server. Change `IDLE_TIMEOUT_MINUTES` in `settings.py` to adjust it.
- After **5 wrong passwords**, login for that username is locked for **5 minutes**, even with the right password. Adjust with `LOGIN_MAX_ATTEMPTS` and `LOGIN_LOCKOUT_MINUTES` in `settings.py`. Restarting Django also clears the lock.
- Passwords can be changed from **Settings**; new passwords must pass Django's password rules (length, not common, not only numbers, not like the username).
- The app is meant to run on your own computer. `runserver` is a development server, not for the public internet.

## License

All rights reserved - see [LICENSE](LICENSE). You may view the code, but not use, copy or sell it without permission.

### If something goes wrong (restore a backup)

1. Stop Django (Ctrl+C in the backend window).
2. In `backend` with the venv active, run `python manage.py restore_db` to put back the newest backup, or `python manage.py restore_db "path\to\hub_....sqlite3"` for a specific one. Your current database is saved to `backups\pre_restore_...` first, so this step can itself be undone.
3. Start Django again (`python manage.py runserver`).

To check a backup before restoring, run `python manage.py check_backup`.