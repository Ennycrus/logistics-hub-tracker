# Daily Routine

Every day ends with two finalized reports, TEMU and Base, sent to the company sheet, the day's fuel and incidents entered, and a fresh backup. Plan about 15 minutes after the scans are done.

## 1. Start the app

The app needs two terminals open in VS Code: one for Django, one for the website.

1. **Terminal 1, Django** (in the `backend` folder):

    ```
    venv\Scripts\activate
    python manage.py runserver
    ```

2. **Terminal 2, website** (click **+** in the terminal panel, then go to the `frontend` folder):

    ```
    npm run dev
    ```

3. Open **http://localhost:5173** and log in with your username and password.

## 2. Import the scanner files

Import every gun-scanner file for the day; each waybill is sorted by its prefix: **3034... = TEMU**, **1... = Base**.

1. Go to **Import** and set the **Reporting date** (today, unless you are catching up).
2. Choose the file and click **Preview**. Nothing is saved yet.
3. Check **New shipments by type** (TEMU and Base counts) and any **Closed - review** rows.
4. If the yellow box appears, choose what to do with waybills starting with neither 1 nor 3034: **Base**, **TEMU** or **Skip**.
5. Click **Confirm import**, check the summary box, then **Import**.
6. Repeat for the next file (for example the Base file after the TEMU file).

**Scans in Google Sheets?** Open **Or paste from Google Sheets**, copy the waybill column (Ctrl+C), paste it in the box, then click **Preview pasted list**. Everything else is the same.

Before confirming, check the line under **Waybill column**: the number of rows and waybills found should match your scan count. The preview also warns you if:

- **waybill numbers are in other columns**: click **Import waybills from all columns**;
- **cells contain a formula with no saved result**: download the sheet again, or paste the column instead;
- **other sheets have data**: only the first sheet is read, so import the others separately.

A **Closed - review** row is a delivered or departed shipment that was scanned again. Click **Update status** on it if it is really back in the hub.

The same file can never be imported twice, and a waybill already in the system is never created again. Imported the wrong file or chose the wrong date? Click **Undo** on that row in **Import history** straight away, before updating any statuses. **Import history** shows one week at a time; use **Previous week** to find older imports.

## 3. Update statuses

Every shipment starts as **Not Yet Checked**; record its real result from the company website before finalizing.

1. Go to **Shipments** and set the filter to **Not yet checked**. Use **TEMU only** or **Base only** to work one report at a time. Delivered shipments are hidden; tick **Show delivered** to see them.
2. One shipment: click **Update**, choose the status, then save.
3. Many with the same result: tick their boxes, click **Update selected**. If one breaks a rule, nothing is saved and the failures are listed.
4. Click a waybill number to see its history and add your own notes.

Rules the app enforces:

- **Delivery Unsuccessful** needs a failure reason; reason **Other** needs a written explanation.
- **Delivered** needs **Delivered by**: **Rider**, **Captain** or **3PL**. With **Update selected**, tick only the shipments one group delivered (for example all the riders' ones), then choose once.
- Changing a shipment that is already **Delivered** needs a note saying why.
- **Date this happened** defaults to today; set it to yesterday when recording yesterday's result this morning. The app remembers the date you chose and shows **Recording for ...** until you click **Use today**, so check it before saving.
- A date before the shipment arrived is refused.
- If that day's report is already finalized, the app asks first, because the frozen report would not show the change. If that report was wrong, start a correction for that day so the two stay in step.
- A parcel sent back to the sender: choose **Initiated Return**. It leaves the hub and is no longer pending.

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

## 6. Enter today's fuel and incidents

One entry per day for the whole hub (TEMU and Base together). The Saturday report adds them up.

1. On **Daily Report**, scroll to **Today's fuel and incidents** at the bottom.
2. Enter the litres used by **riders** and by **captains**. Type **0** if none was used; leaving a box empty means "not entered".
3. Write any incidents, escalations, challenges or difficulties. Leave it empty if nothing happened.
4. Click **Save fuel and incidents**.

Forgot a day? Change the date at the top of **Daily Report** to that day and fill it in. Changed a figure later? The earlier value is kept; click **Show changes** to see every save. Anything entered on a **Sunday** counts in the next week's Saturday report.

## 7. Back up and shut down

A backup runs by itself every evening at 7 pm (and catches up when the laptop is next turned on). To make an extra one by hand:

1. Open a third terminal in the `backend` folder, run `venv\Scripts\activate`, then:

    ```
    python manage.py backup_db
    ```

2. Check it prints **Backup saved: ...** and **Copy saved: ...** (the copy in Google Drive).
3. Stop both servers with **Ctrl+C** in each terminal.

Once a week, check that the newest backup can really be restored:

```
python manage.py check_backup
```

It should say **File is healthy** and **This backup can be restored**, with counts close to the app's.

## 8. Saturday: check the weekly delivery

The delivery week runs Monday to Saturday, and its figures come only from finalized reports. The **Dashboard** shows this week's rate every day; the **Weekly** page has the full detail.

1. After finalizing Saturday's TEMU and Base reports, go to **Weekly**.
2. Pick **TEMU** or **Base** with the switch; use **Previous week** / **Next week** to move between weeks.
3. Read **Delivered this week**, **Available this week** and **Weekly delivery rate**. If it says **Incomplete week**, finalize the missing days first.
4. Click **Download weekly Excel** for each type if the company asks for it.

Available = Monday's Old Pending + every Inbound from Monday to Saturday, so each shipment is counted once however many days it waited.

## 9. Saturday: count the shelves

A stock count checks that the app matches what is really in the hub, so the Saturday report is right.

1. Scan every parcel on the shelves into one file (or a Google Sheet).
2. Go to **Stock Count**, choose **TEMU and Base** (or one type if they are on separate shelves), and upload or paste the scan, then click **Check scan**.
3. Work through each list:
    - **Missing from shelves**: the app says it is in the hub, but it was not scanned. Find it, or click **Update status** (delivered without an update, initiated return...).
    - **Scanned but delivered / left hub**: it is on the shelf, so the status is wrong. Click **Update status**.
    - **Scanned but not in the app**: never imported. Click **Copy waybills**, then paste them on **Import** with the day they arrived as the reporting date.
4. Click **Check again** until it says **Everything matches**.

Nothing is saved by the check itself; only the status updates and imports you make are.

## 10. Saturday evening: send the Saturday report

The manager's weekly report, for TEMU and Base together. Do it after steps 8 and 9.

1. Go to **Saturday Report**.
2. Read the warnings and fix them first:
    - **No fuel entered for ...**: fill in those days (step 6).
    - **... delivered shipment(s) have no Rider, Captain or 3PL recorded**: click **Show them**, then **Update** on each and choose who delivered it.
    - **... shipment(s) have had no status update for 7 days or more**: click **Show them** and record what happened to each, so items 1, 2 and 4 are not too high.
    - **Check before sending**: the delivered number differs from your finalized daily reports. Find out why before sending.
3. Add anything else under **Extra notes for item 6** (optional).
4. Click **Save report**. If a warning is still open, the app lists it and asks **Save anyway?**. The figures are now frozen as they are at that moment.
5. Click **Copy report** and paste it into WhatsApp or your email, or click **Download Excel**.

Item 4 (not in hub) is already included in items 1 and 2, because pending means "not delivered yet". Saving again creates a new version; earlier versions stay under **Saved Saturday reports**.

## Occasional tasks

**Undo a wrong import.** In **Import history**, click **Undo** on that row and confirm. Only the shipments that import created are removed; shipments that were already in the system stay. It is refused if any of its shipments already has a status update, is in a finalized report, or appears in a later import (undo the later one first).

**Correct a finalized report.** Open **Daily Report** on that date and type, write a reason under **Need to correct this report?**, click **Start correction**, fix the figures, then finalize again. The original stays in **History** as *Replaced*; send the new version (`_v2`) to the company.

**Add who delivered an older shipment.** On **Shipments**, set the filter to **Delivered, nobody recorded**, click **Update** on the shipment, keep **Delivered**, choose **Rider**, **Captain** or **3PL**, then save. No note is needed, and the delivery keeps its original date.

**Clear stuck shipments.** On **Shipments**, set the filter to **Stuck: no update for 7+ days** and record what happened to each one (delivered, returned, rerouted...).

**Catch up on a missed day.** Import that day's files with its own **Reporting date**, record results with **Date this happened** set to that day, and finalize that date before the next one, so Old Pending carries forward correctly.

**Restore a backup.**

1. Check the backup first: `python manage.py check_backup "<path to the backup file>"`.
2. Stop Django (**Ctrl+C**).
3. Rename `backend\db.sqlite3` to `db_broken.sqlite3`. If `db.sqlite3-wal` or `db.sqlite3-shm` are there too, rename them the same way (`db_broken.sqlite3-wal`, `db_broken.sqlite3-shm`).
4. Copy the backup from `backend\backups` (or Google Drive) next to `manage.py` and rename it `db.sqlite3`.
5. Start Django again. If `check_backup` said the structure is different, run `python manage.py migrate` first.

## Troubleshooting

| Message or problem | Fix |
| --- | --- |
| "Cannot reach the server. Is Django running?" | Start Terminal 1 (`python manage.py runserver`). |
| "Security check failed. Refresh the page..." | Press **F5** and try again. |
| Page looks old after an update | Press **Ctrl+Shift+R**. |
| "This exact file was already imported..." | The file is already in; check **Import history**. To pick up waybills from other columns, use **Import waybills from all columns** (allowed once for the same file). |
| Import shows fewer rows than you scanned | Read the warnings under **Waybill column** (other columns, formula cells, other sheets), or paste the column from Google Sheets instead. |
| "This shipment only arrived on ..." | The date is before its arrival; check **Date this happened** (the remembered date may be an old one). |
| Backup prints no **Copy saved** line | `BACKUP_COPY_DIR` is not set in `backend\.env`, or Google Drive is not running. |
| "This import cannot be undone..." | Its shipments were already worked on or reported. Fix them one by one on **Shipments**, or start a correction if the report is finalized. |
| "Unknown command" or "No module named django" | Activate the venv first: `venv\Scripts\activate` in the `backend` folder. |
| Check line says **Difference** instead of Balanced | Look for shipments without a result on **Pending**; do not finalize until it balances or you know why. |
| "... report is finalized" when editing | Use **Start correction** instead. |
| Weekly page says **Incomplete week** | Finalize the missing days on **Daily Report**, then refresh. |
| **Save** stays grey when marking Delivered | Choose **Rider**, **Captain** or **3PL** first. |
| Saturday report says fuel "entered for 4 of 6 days" | Fill in the missing days on **Daily Report**, then **Save again** on **Saturday Report**. |
| Saturday report: **Check before sending** | A daily report was adjusted, or a delivery was recorded after its day was finalized. Compare with **Weekly** before sending. |