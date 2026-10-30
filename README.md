# Logistics Hub Tracker

[![Tests](https://github.com/Ennycrus/logistics-hub-tracker/actions/workflows/tests.yml/badge.svg)](https://github.com/Ennycrus/logistics-hub-tracker/actions/workflows/tests.yml)

A web app for running one logistics hub's day: import gun-scanner files, track the delivery status of every shipment, and produce two accurate daily reports (**TEMU** and **Base**) in the company's 11-column format.

Built with **Django REST Framework**, **React (Vite)**, **SQLite** and **openpyxl**.

## Features

- **Scanner import with preview** - finds the waybill column automatically, flags duplicates, invalid rows and already-closed shipments. The same file can never be imported twice.
- **Two shipment types, sorted by waybill prefix** - `3034...` = TEMU, `1...` = Base. Waybills with any other prefix make the import ask: Base, TEMU or Skip.
- **Status tracking with full history** - every change is recorded with its date. Failed deliveries need a reason; "Other" needs an explanation; changing a delivered shipment needs a note.
- **Bulk updates, all or nothing** - if one selected shipment breaks a rule, nothing is saved.
- **Separate daily reports for TEMU and Base** - own figures, carry-forward, transport (vans, bikes, 3PL), reasons and finalize.
- **Reconciliation check** - Delivered + Current Day + Rerouted must equal Total Available.
- **Frozen reports** - a finalized report never changes. Corrections create a new version (v2, v3...) and keep the original.
- **Export** - download the report as Excel, or copy the row straight into a Google Sheet.
- **Dashboard, Pending list, Report history, Settings** - statuses and failure reasons are editable.
- **Backup and reset commands** for safe day-to-day use.

## How the report figures are calculated

Each report (TEMU or Base) only counts shipments of its own type.

| Figure | Meaning |
| --- | --- |
| Inbound | Shipments first scanned on this date |
| Old Pending | Shipments first scanned earlier and still at the hub at the end of the previous day |
| Total Available | Inbound + Old Pending |
| Delivered | Delivered on this date |
| Current Day | Still at the hub at the end of the day (not checked, outstanding or returned) |
| Return | Returned to the hub (also counted inside Current Day) |
| Reasons | Failure reasons grouped with counts, e.g. "Customer unavailable - 3" |

Rerouted shipments leave the hub and are not carried forward. Statuses are worked out from the history using the date each change happened, so past dates stay correct.

## Project structure
hub-tracker/
backend/ Django project
config/ settings and URLs
core/ hub settings, statuses, failure reasons, login
shipments/ shipments, status history, scanner imports
reports/ reporting days, calculations, reports, Excel export
.env.example template for your private .env file
requirements.txt
frontend/ React app (Vite)
src/api/client.js the one file that talks to Django
src/pages/ Dashboard, Import, Shipments, Pending, Daily Report, History, Settings
src/components/ layout, status editor, dialogs, Base/TEMU switch
docs/
DAILY_ROUTINE.md step-by-step daily guide


The business rules live in `services/` folders (for example `shipments/services/status_service.py` and `reports/services/calculations.py`), so the API views stay thin.

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

See **[docs/DAILY_ROUTINE.md](docs/DAILY_ROUTINE.md)**: import the files, update statuses, check Pending, finalize the TEMU and Base reports, back up.

## Useful commands

Run these in `backend` with the venv active.

| Command | What it does |
| --- | --- |
| `python manage.py backup_db` | Safe copy of the database into `backend/backups/` (keeps the newest 30) |
| `python manage.py reset_data` | Deletes all shipments, imports and reports after a backup; keeps users and settings |
| `python manage.py test` | Runs the test suite (221 tests) |

Older command-line report tools (`open_day`, `day_summary`, `finalize_report`, `export_report`...) also exist and work on the TEMU report.

## API overview

All endpoints need a logged-in user. Report endpoints take `?type=temu` or `?type=base` (TEMU if left out).

| Endpoint | Purpose |
| --- | --- |
| `GET /api/shipments/` | List shipments (`search`, `category`, `type`, `page`) |
| `POST /api/shipments/<id>/status/` | Change one status |
| `POST /api/shipments/bulk-status/` | Change many, all or nothing |
| `POST /api/imports/preview/` | Read a scanner file, save nothing |
| `POST /api/imports/confirm/` | Import it (`unknown_type`: base, temu or skip) |
| `GET/PATCH /api/reports/<date>/` | The day's draft or finalized report |
| `POST /api/reports/<date>/finalize/` | Freeze the report |
| `POST /api/reports/<date>/correct/` | Start a corrected version |
| `GET /api/reports/<date>/download/` | Excel file |
| `GET /api/reports/` | Report history |

## Security notes

- The secret key lives in `backend/.env`, which is never committed. Only `.env.example` is in the repository.
- The database (`*.sqlite3`), backups and scanner files (`*.xlsx`) are ignored by Git, so real shipment data never leaves your computer.
- `DEBUG` is off unless `.env` turns it on.
- The app is meant to run on your own computer. `runserver` is a development server, not for the public internet.

## License

[MIT](LICENSE) - free to use and adapt, with credit.
