# Daily Routine

Every day ends with two finalized reports, TEMU and Base, sent to the company sheet, and a fresh backup. Plan about 15 minutes after the scans are done.

## 1. Start the app

The app needs two terminals open in VS Code: one for Django, one for the website.

1. **Terminal 1, Django** (in the `backend` folder):

    ````
    venv\Scripts\activate
    python manage.py runserver
    ````

2. **Terminal 2, website** (click **+** in the terminal panel, then go to the `frontend` folder):

    ````
    npm run dev
    ````

3. Open **http://localhost:5173** and log in with your username and password.

## 2. Import the scanner files

Import every gun-scanner file for the day; each waybill is sorted by its prefix: **3034... = TEMU**, **1... = Base**.

1. Go to **Import** and set the **Reporting date** (today, unless you are catching up).
2. Choose the file and click **Preview**. Nothing is saved yet.
3. Check **New shipments by type** (TEMU and Base counts) and any **Closed - review** rows.
4. If the yellow box appears, choose what to do with waybills starting with neither 1 nor 3034: **Base**, **TEMU** or **Skip**.
5. Click **Confirm import**, check the summary box, then **Import**.
6. Repeat for the next file (for example the Base file after the TEMU file).

The same file can never be imported twice, and a waybill already in the system is never created again. Imported the wrong file or chose the wrong date? Click **Undo** on that row in **Import history** straight away, before updating any statuses.

## 3. Update statuses

Every shipment starts as **Not Yet Checked**; record its real result from the company website before finalizing.

1. Go to **Shipments** and set the filter to **Not yet checked**. Use **TEMU only** or **Base only** to work one report at a time.
2. One shipment: click **Update**, choose the status, then save.
3. Many with the same result: tick their boxes, click **Update selected**. If one breaks a rule, nothing is saved and the failures are listed.
4. Click a waybill number to see its history and add your own notes.

Rules the app enforces:

- **Delivery Unsuccessful** needs a failure reason; reason **Other** needs a written explanation.
- Changing a shipment that is already **Delivered** needs a note saying why.
- **Date this happened** defaults to today; set it to yesterday when recording yesterday's result this morning.

## 4. Review Pending

Pending shows exactly the shipments in the day's report, so you can catch anything left behind.

1. Go to **Pending** and pick **TEMU** or **Base** with the switch.
2. **Old Pending** is listed longest-waiting first; red days (3 or more) need chasing.
3. Filter by **Not yet checked** to see what still has no result, and update from here with **Update**.

## 5. Finalize both reports

Finalize TEMU first, then Base; each has its own figures, transport and Excel file.

1. Go to **Daily Report**, check the date, and click **TEMU** on the switch.
2. Check the line under **Check**: it should say **Balanced**.
3. Enter **No of Vans**, **No of Bike** and **No of 3PL** for TEMU, then **Save figures**.
4. Read any **Warnings**, tick **I have reviewed these warnings**, then **Finalize report**, then **Finalize**.
5. Send it: **Copy figures** (or **Copy whole row**) and paste into the company Google Sheet, or **Download TEMU Excel**.
6. Click **Base** on the switch and repeat steps 2-5 with the Base transport figures.

A manual adjustment is only for a calculated figure you know is wrong; it needs a note and shows as a warning.

## 6. Back up and shut down

A backup runs by itself every evening at 7 pm (and catches up when the laptop is next turned on). To make an extra one by hand:

1. Open a third terminal in the `backend` folder, run `venv\Scripts\activate`, then:

    ````
    python manage.py backup_db
    ````

2. Check it prints **Backup saved: ...**.
3. Stop both servers with **Ctrl+C** in each terminal.
4. Once a week, copy the `backend\backups` folder to Google Drive or a flash drive.

## 7. Saturday: check the weekly delivery

The delivery week runs Monday to Saturday, and its figures come only from finalized reports. The **Dashboard** shows this week's rate every day; the **Weekly** page has the full detail.

1. After finalizing Saturday's TEMU and Base reports, go to **Weekly**.
2. Pick **TEMU** or **Base** with the switch; use **Previous week** / **Next week** to move between weeks.
3. Read **Delivered this week**, **Available this week** and **Weekly delivery rate**. If it says **Incomplete week**, finalize the missing days first.
4. Click **Download weekly Excel** for each type if the company asks for it.

Available = Monday's Old Pending + every Inbound from Monday to Saturday, so each shipment is counted once however many days it waited.

## Occasional tasks

**Undo a wrong import.** In **Import history**, click **Undo** on that row and confirm. Only the shipments that import created are removed; shipments that were already in the system stay. It is refused if any of its shipments already has a status update, is in a finalized report, or appears in a later import (undo the later one first).

**Correct a finalized report.** Open **Daily Report** on that date and type, write a reason under **Need to correct this report?**, click **Start correction**, fix the figures, then finalize again. The original stays in **History** as *Replaced*; send the new version (`_v2`) to the company.

**Catch up on a missed day.** Import that day's files with its own **Reporting date**, record results with **Date this happened** set to that day, and finalize that date before the next one, so Old Pending carries forward correctly.

**Restore a backup.**

1. Stop Django (**Ctrl+C**).
2. Rename `backend\db.sqlite3` to `db_broken.sqlite3`.
3. Copy the backup from `backend\backups` next to `manage.py` and rename it `db.sqlite3`.
4. Start Django again.

## Troubleshooting

| Message or problem | Fix |
| --- | --- |
| "Cannot reach the server. Is Django running?" | Start Terminal 1 (`python manage.py runserver`). |
| "Security check failed. Refresh the page..." | Press **F5** and try again. |
| Page looks old after an update | Press **Ctrl+Shift+R**. |
| "This exact file was already imported..." | The file is already in; check **Import history**. |
| "This import cannot be undone..." | Its shipments were already worked on or reported. Fix them one by one on **Shipments**, or start a correction if the report is finalized. |
| "Unknown command" or "No module named django" | Activate the venv first: `venv\Scripts\activate` in the `backend` folder. |
| Check line says **Difference** instead of Balanced | Look for shipments without a result on **Pending**; do not finalize until it balances or you know why. |
| "... report is finalized" when editing | Use **Start correction** instead. |
| Weekly page says **Incomplete week** | Finalize the missing days on **Daily Report**, then refresh. |
