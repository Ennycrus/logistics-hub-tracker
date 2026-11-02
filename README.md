# Logistics Hub Tracker

[![Tests](https://github.com/Ennycrus/logistics-hub-tracker/actions/workflows/tests.yml/badge.svg)](https://github.com/Ennycrus/logistics-hub-tracker/actions/workflows/tests.yml)

A web app for running one logistics hub's day: import gun-scanner files, track the delivery status of every shipment, and produce two accurate daily reports (**TEMU** and **Base**) in the company's 11-column format, plus a weekly delivery summary.

Built with **Django REST Framework**, **React (Vite)**, **SQLite** and **openpyxl**.

## Features

- **Scanner import with preview** - finds the waybill column automatically, flags duplicates, invalid rows and already-closed shipments. The same file can never be imported twice.
- **Undo a wrong import** - removes the import and only the shipments it created. Refused if any of them already has a status update, is in a finalized report, or appears in a later import.
- **Two shipment types, sorted by waybill prefix** - `3034...` = TEMU, `1...` = Base. Waybills with any other prefix make the import ask: Base, TEMU or Skip.
- **Status tracking
hub-tracker/
backend/ Django project
config/ settings and URLs
core/ hub settings, statuses, failure reasons, login and passwords
shipments/ shipments, status history, scanner imports and undo
reports/ reporting days, calculations, reports, weekly summary, Excel export
.env.example template for your private .env file
requirements.txt
frontend/ React app (Vite)
src/api/client.js the one file that talks to Django
src/pages/ Dashboard, Import, Shipments, Pending, Daily Report, Weekly, History, Settings
src/components/ layout, status editor, dialogs, Base/TEMU switch
docs/
DAILY_ROUTINE.md step-by-step daily guide

The business rules live in `services/` folders (for example `shipments/services/status_service.py`, `shipments/services/import_service.py`, `reports/services/calculations.py` and `reports/services/weekly.py`), so the API views stay thin.

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

See **[docs/DAILY_ROUTINE.md](docs/DAILY_ROUTINE.md)**: import the files, update statuses, check Pending, finalize the TEMU and Base reports, back up, and check the weekly delivery on Saturday.

## Useful commands

Run these in `backend` with the venv active.

| Command | What it does |
| --- | --- |
| `python manage.py backup_db` | Safe copy of the database into `backend/backups/` (keeps the newest 30) |
| `python manage.py reset_data` | Deletes all shipments, imports and reports after a backup; keeps users and settings |
| `python manage.py test` | Runs the test suite (254 tests) |

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
| `DELETE /api/imports/<id>/` | Undo an import (refused if its shipments were worked on) |
| `GET/PATCH /api/reports/<date>/` | The day's draft or finalized report |
| `POST /api/reports/<date>/finalize/` | Freeze the report |
| `POST /api/reports/<date>/correct/` | Start a corrected version |
| `GET /api/reports/<date>/download/` | Excel file |
| `GET /api/reports/` | Report history |
| `GET /api/reports/weekly/?date=` | The Monday-Saturday week containing that date |
| `GET /api/reports/weekly/download/?date=` | The week as an Excel file |
| `POST /api/auth/change-password/` | Change your password (needs the current one) |

## Security notes

- The secret key lives in `backend/.env`, which is never committed. Only `.env.example` is in the repository.
- The database (`*.sqlite3`), backups and scanner files (`*.xlsx`) are ignored by Git, so real shipment data never leaves your computer.
- `DEBUG` is off unless `.env` turns it on.
- Only the website's login session can reach the API, and Excel files are read with `defusedxml` protection.
- After **15 minutes without activity** you are logged out, both on the website and on the server. Logging out also ends the session on the server. Change `IDLE_TIMEOUT_MINUTES` in `settings.py` to adjust it.
- After **5 wrong passwords**, login for that username is locked for **5 minutes**, even with the right password. Adjust with `LOGIN_MAX_ATTEMPTS` and `LOGIN_LOCKOUT_MINUTES` in `settings.py`. Restarting Django also clears the lock.
- Passwords can be changed from **Settings**; new passwords must pass Django's password rules (length, not common, not only numbers, not like the username).
- The app is meant to run on your own computer. `runserver` is a development server, not for the public internet.

## License

All rights reserved - see [LICENSE](LICENSE). You may view the code, but not use, copy or sell it without permission.
