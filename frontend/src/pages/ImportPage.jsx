import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { imports } from '../api/client'
import ConfirmDialog from '../components/ConfirmDialog'
import { typeLabel } from '../components/TypeSwitch'

function today() {
  return new Date().toLocaleDateString('en-CA')
}

// How each row result is shown. Matches ImportRow.RESULT_* in Django.
const RESULTS = {
  new: { label: 'New', badge: 'delivered' },
  existing_outstanding: { label: 'Already at hub', badge: 'returned' },
  existing_closed: { label: 'Closed — review', badge: 'outstanding' },
  duplicate_in_file: { label: 'Duplicate in file', badge: 'left_hub' },
  invalid: { label: 'Invalid', badge: 'unchecked' },
}

const ROWS_PER_PAGE = 50

/*
 * Import a gun-scanner file in two steps:
 *   1. Preview  – Django reads the file and classifies every row. Nothing is saved.
 *   2. Confirm  – Django saves the batch and creates the new shipments.
 * Each new waybill becomes TEMU (starts with 3034) or Base (starts with 1).
 * If some start with neither, you choose Base, TEMU or Skip before confirming.
 * Below that: the history of past imports.
 */
export default function ImportPage() {
  const [file, setFile] = useState(null)
  const [date, setDate] = useState(today())
  const [column, setColumn] = useState('')   // '' = let Django detect it
  const [inputKey, setInputKey] = useState(0) // change it to clear the file box
  const [unknownType, setUnknownType] = useState('') // 'base' | 'temu' | 'skip' | '' (not chosen)

  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState('')        // 'preview' | 'confirm' | ''
  const [error, setError] = useState('')
  const [done, setDone] = useState(null)      // the saved batch after confirming
  const [asking, setAsking] = useState(false) // the "Import this file?" box is open

  const [history, setHistory] = useState([])

  function loadHistory() {
    imports.list().then((data) => setHistory(data.results)).catch(() => {})
  }
  useEffect(loadHistory, [])

  async function runPreview(chosenColumn = column) {
    if (!file || busy) return
    setBusy('preview')
    setError('')
    setDone(null)
    setUnknownType('')
    try {
      const result = await imports.preview(file, chosenColumn)
      setPreview(result)
      if (result.selected_column !== null) setColumn(String(result.selected_column))
    } catch (err) {
      setPreview(null)
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  // What the "Import this file?" box lists.
  function summaryItems() {
    const c = preview.counts
    const t = preview.new_by_type
    const items = [
      { label: 'New TEMU shipments', value: t.temu },
      { label: 'New Base shipments', value: t.base },
    ]
    if (t.unknown) {
      items.push(
        unknownType === 'skip'
          ? { label: 'Unknown prefix: skipped', value: t.unknown, muted: true }
          : { label: `Unknown prefix: created as ${typeLabel(unknownType)}`, value: t.unknown },
      )
    }
    items.push(
      { label: 'Already in the system (not created again)', value: c.existing_outstanding + c.existing_closed, muted: true },
      { label: 'Duplicate or invalid rows (skipped)', value: c.duplicate_in_file + c.invalid, muted: true },
    )
    return items
  }

  async function confirm() {
    if (busy) return
    setBusy('confirm')
    setError('')
    try {
      const batch = await imports.confirm(file, date, column, unknownType)
      setDone(batch)
      reset()
      loadHistory()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
      setAsking(false)
    }
  }

  function reset() {
    setFile(null)
    setPreview(null)
    setColumn('')
    setUnknownType('')
    setInputKey((k) => k + 1)
  }

  const needsUnknownChoice = (preview?.new_by_type?.unknown ?? 0) > 0
  const canConfirm =
    preview && preview.selected_column !== null && !preview.already_imported && !busy &&
    (!needsUnknownChoice || unknownType !== '')

  return (
    <>
      <div className="card">
        <h2>Import scanner file</h2>
        <p className="muted">Choose the gun-scanner Excel file and the date it belongs to, then preview it.</p>

        <div className="form-row">
          <label>
            Reporting date
            <input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label className="grow">
            Scanner file (.xlsx)
            <input
              key={inputKey}
              type="file"
              accept=".xlsx"
              onChange={(e) => {
                setFile(e.target.files[0] || null)
                setPreview(null)
                setColumn('')
                setDone(null)
              }}
            />
          </label>
        </div>

        <div className="actions">
          <button onClick={() => runPreview('')} disabled={!file || busy !== ''}>
            {busy === 'preview' ? 'Reading file…' : 'Preview'}
          </button>
        </div>

        {error && <p className="error">{error}</p>}
        {done && (
          <p className="success">
            Imported {done.file_name} for {done.reporting_date}: {done.new_count} new shipment(s) created
            ({done.temu_new_count} TEMU, {done.base_new_count} Base).{' '}
            <Link to="/shipments">Go to Shipments →</Link>
          </p>
        )}
      </div>

      {preview && (
        <PreviewPanel
          preview={preview}
          column={column}
          onColumnChange={(value) => {
            setColumn(value)
            runPreview(value)
          }}
          unknownType={unknownType}
          onUnknownTypeChange={setUnknownType}
          busy={busy}
          canConfirm={canConfirm}
          onConfirm={() => setAsking(true)}
          onCancel={reset}
        />
      )}

      {asking && preview && (
        <ConfirmDialog
          title="Import this file?"
          message={`${preview.file_name} · reporting date ${date}`}
          items={summaryItems()}
          confirmLabel="Import"
          busy={busy === 'confirm'}
          onConfirm={confirm}
          onCancel={() => setAsking(false)}
        />
      )}

      <div className="card">
        <h2>Import history</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Reporting date</th>
                <th>File</th>
                <th>Rows</th>
                <th>New TEMU</th>
                <th>New Base</th>
                <th>Already at hub</th>
                <th>Closed</th>
                <th>Duplicate</th>
                <th>Invalid</th>
                <th>Imported at</th>
              </tr>
            </thead>
            <tbody>
              {history.map((b) => (
                <tr key={b.id}>
                  <td>{b.reporting_date}</td>
                  <td>{b.file_name}</td>
                  <td>{b.total_rows}</td>
                  <td>{b.temu_new_count}</td>
                  <td>{b.base_new_count}</td>
                  <td>{b.existing_outstanding_count}</td>
                  <td>{b.existing_closed_count}</td>
                  <td>{b.duplicate_in_file_count}</td>
                  <td>{b.invalid_count}</td>
                  <td className="small">{new Date(b.imported_at).toLocaleString()}</td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr><td colSpan="10" className="muted">No imports yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

/* The preview: summary counts, column choice, and a searchable table of every row. */
function PreviewPanel({
  preview, column, onColumnChange, unknownType, onUnknownTypeChange, busy, canConfirm, onConfirm, onCancel,
}) {
  const [search, setSearch] = useState('')
  const [resultFilter, setResultFilter] = useState('')
  const [page, setPage] = useState(1)

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase()
    return preview.rows.filter(
      (r) => (!term || r.waybill.toLowerCase().includes(term)) && (!resultFilter || r.result === resultFilter),
    )
  }, [preview, search, resultFilter])

  const totalPages = Math.max(1, Math.ceil(rows.length / ROWS_PER_PAGE))
  const shown = rows.slice((page - 1) * ROWS_PER_PAGE, page * ROWS_PER_PAGE)

  return (
    <div className="card">
      <h2>Preview: {preview.file_name}</h2>

      {preview.already_imported && (
        <p className="error">
          This exact file was already imported for {preview.already_imported.reporting_date}. It can't be imported again.
        </p>
      )}

      <label className="inline-label">
        Waybill column
        <select value={column} onChange={(e) => onColumnChange(e.target.value)} disabled={busy !== ''}>
          {preview.selected_column === null && <option value="">Choose the column…</option>}
          {preview.columns.map((c) => (
            <option key={c.index} value={c.index}>{c.label}</option>
          ))}
        </select>
      </label>

      {preview.selected_column === null ? (
        <p className="error">{preview.message}</p>
      ) : (
        <>
          <p className="muted">
            {preview.total_rows} row(s) read{preview.has_header ? ' (first row is a header)' : ''}.
          </p>

          <div className="stats">
            {Object.entries(RESULTS).map(([key, info]) => (
              <button
                key={key}
                className={`stat ${resultFilter === key ? 'active' : ''}`}
                onClick={() => {
                  setResultFilter(resultFilter === key ? '' : key)
                  setPage(1)
                }}
              >
                <span className="stat-value">{preview.counts[key]}</span>
                <span className="stat-label">{info.label}</span>
              </button>
            ))}
          </div>

          <p>
            <strong>New shipments by type:</strong> {preview.new_by_type.temu} TEMU · {preview.new_by_type.base} Base
            {preview.new_by_type.unknown > 0 && ` · ${preview.new_by_type.unknown} unknown`}
          </p>

          {preview.new_by_type.unknown > 0 && (
            <div className="warning">
              <strong>
                {preview.new_by_type.unknown} new waybill(s) start with neither 1 (Base) nor 3034 (TEMU).
              </strong>{' '}
              They are marked "?" in the table below. What should happen to them?
              <label className="inline-label">
                Unknown waybills
                <select value={unknownType} onChange={(e) => onUnknownTypeChange(e.target.value)} disabled={busy !== ''}>
                  <option value="">Choose…</option>
                  <option value="base">Create them as Base</option>
                  <option value="temu">Create them as TEMU</option>
                  <option value="skip">Skip them (don't import)</option>
                </select>
              </label>
            </div>
          )}

          <div className="toolbar">
            <input
              type="search"
              placeholder="Search waybill…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
            />
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Row</th><th>Waybill</th><th>Type</th><th>Result</th><th>Details</th></tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.row_number}>
                    <td>{r.row_number}</td>
                    <td className="mono">{r.waybill || '(empty)'}</td>
                    <td>{r.shipment_type ? typeLabel(r.shipment_type) : r.result === 'new' ? <strong>?</strong> : '—'}</td>
                    <td><span className={`badge badge-${RESULTS[r.result].badge}`}>{RESULTS[r.result].label}</span></td>
                    <td className="small">{r.message}</td>
                  </tr>
                ))}
                {shown.length === 0 && <tr><td colSpan="5" className="muted">No rows match.</td></tr>}
              </tbody>
            </table>
          </div>

          <div className="pager">
            <button className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Previous</button>
            <span className="muted">Page {page} of {totalPages}</span>
            <button className="secondary" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next →</button>
          </div>
        </>
      )}

      <div className="actions">
        <button className="secondary" onClick={onCancel} disabled={busy !== ''}>Cancel</button>
        <button onClick={onConfirm} disabled={!canConfirm}>
          {busy === 'confirm' ? 'Importing…' : 'Confirm import'}
        </button>
      </div>
    </div>
  )
}