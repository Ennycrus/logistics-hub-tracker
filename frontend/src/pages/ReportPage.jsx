import { useCallback, useEffect, useState } from 'react'
import { reports } from '../api/client'
import ConfirmDialog from '../components/ConfirmDialog'
import CopyRow from '../components/CopyRow'
import TypeSwitch, { typeLabel, useShipmentType } from '../components/TypeSwitch'

function today() {
  return new Date().toLocaleDateString('en-CA')
}

// The company sheet's columns, in order. `key` is where each value lives.
const COLUMNS = [
  { label: 'HUBS', key: 'hub_name' },
  { label: 'Inbound', key: 'inbound' },
  { label: 'Old Pending', key: 'old_pending' },
  { label: 'Total Available', key: 'total_available' },
  { label: 'Delivered', key: 'delivered' },
  { label: 'Current Day', key: 'current_day' },
  { label: 'Return', key: 'return' },
  { label: 'No of Vans', key: 'vans' },
  { label: 'No of Bike', key: 'bikes' },
  { label: 'No of 3PL', key: 'third_party' },
  { label: 'Reasons', key: 'reasons_text' },
]

// Figures you may override by hand (same list as ADJUSTABLE in Django).
const ADJUSTABLE = [
  { key: 'inbound', label: 'Inbound' },
  { key: 'old_pending', label: 'Old Pending' },
  { key: 'delivered', label: 'Delivered' },
  { key: 'current_day', label: 'Current Day' },
  { key: 'return', label: 'Return' },
]

/*
 * The daily report for one date and one type (TEMU or Base).
 * The two types are separate reports with separate figures.
 *   Draft      -> live figures, transport inputs, adjustments, warnings, Finalize.
 *   Finalized  -> the frozen figures, Download, and Start correction.
 */
export default function ReportPage() {
  const [date, setDate] = useState(today())
  const [type, setType] = useShipmentType()
  const [data, setData] = useState(null)   // { state, report, preview }
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setData(await reports.get(date, type))
    } catch (err) {
      setData(null)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [date, type])

  useEffect(() => {
    setMessage('')
    load()
  }, [load])

  return (
    <>
      <div className="card">
        <div className="title-row">
          <h2>Daily report · {typeLabel(type)}</h2>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <TypeSwitch value={type} onChange={setType} />
            <label className="inline-date">
              Date
              <input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} />
            </label>
          </div>
        </div>
        {loading && <p className="muted">Loading…</p>}
        {error && <p className="error">{error}</p>}
        {message && <p className="success">{message}</p>}
      </div>

      {!loading && data?.state === 'draft' && (
        <DraftReport
          key={`${date}-${type}-${data.report.version}`}
          date={date}
          type={type}
          data={data}
          onChange={setData}
          onFinalized={(result) => {
            setData(result)
            setMessage(`${typeLabel(type)} report finalized. These figures are now frozen.`)
          }}
        />
      )}

      {!loading && data?.state === 'finalized' && (
        <FinalizedReport
          date={date}
          type={type}
          report={data.report}
          onCorrectionStarted={(result) => {
            setData(result)
            setMessage(`Correction started (version ${result.report.version}). Fix the figures, then finalize again.`)
          }}
        />
      )}
    </>
  )
}

/* The company row, exactly as it will appear in the Excel file. */
function ReportRow({ values, adjusted = {} }) {
  return (
    <div className="table-wrap">
      <table className="report-row">
        <thead>
          <tr>{COLUMNS.map((c) => <th key={c.key}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          <tr>
            {COLUMNS.map((c) => (
              <td key={c.key} className={adjusted[c.key] ? 'adjusted' : ''}>
                {values[c.key] ?? <span className="missing">not entered</span>}
                {adjusted[c.key] && <span className="small muted"> (adjusted)</span>}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function DraftReport({ date, type, data, onChange, onFinalized }) {
  const { report, preview } = data

  // The form starts with what is saved on the draft.
  const saved = {
    vans: report.vans ?? '',
    bikes: report.bikes ?? '',
    third_party: report.third_party ?? '',
    notes: report.notes,
    reasons_text: report.reasons_text,
  }
  const [form, setForm] = useState(saved)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [accepted, setAccepted] = useState(false)
  const [asking, setAsking] = useState(false) // the "Finalize?" box is open

  const dirty = Object.keys(saved).some((k) => String(form[k]) !== String(saved[k]))
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  // Warn before closing the tab with unsaved figures.
  useEffect(() => {
    if (!dirty) return
    const warn = (e) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  async function send(changes) {
    setSaving(true)
    setError('')
    try {
      const result = await reports.update(date, changes, type)
      onChange(result)
      return result
    } catch (err) {
      setError(err.message)
      return null
    } finally {
      setSaving(false)
    }
  }

  function saveInputs(event) {
    event.preventDefault()
    if (saving) return
    const changes = { notes: form.notes, reasons_text: form.reasons_text }
    for (const field of ['vans', 'bikes', 'third_party']) {
      if (form[field] !== '') changes[field] = Number(form[field])
    }
    send(changes)
  }

  async function finalize() {
    if (saving) return
    setSaving(true)
    setError('')
    try {
      onFinalized(await reports.finalize(date, accepted, type))
    } catch (err) {
      setError(err.message)
      setAsking(false)
    } finally {
      setSaving(false)
    }
  }

  const values = {
    ...preview.figures,
    hub_name: preview.hub_name,
    vans: report.vans,
    bikes: report.bikes,
    third_party: report.third_party,
    reasons_text: preview.reasons_text || '—',
  }
  const hasWarnings = preview.warnings.length > 0
  const canFinalize = !saving && !dirty && preview.problems.length === 0 && (!hasWarnings || accepted)
  const r = preview.reconciliation

  return (
    <>
      <div className="card">
        {report.corrects_version && (
          <p className="notice">
            Correction: version {report.version} replaces version {report.corrects_version}. Reason: {report.correction_reason}
          </p>
        )}
        <h3>{typeLabel(type)} report row (draft)</h3>
        <ReportRow values={values} adjusted={report.adjustments} />

        <div className="stats">
          <div className="stat"><span className="stat-value">{preview.figures.unsuccessful}</span><span className="stat-label">Unsuccessful</span></div>
          <div className="stat"><span className="stat-value">{preview.figures.unchecked}</span><span className="stat-label">Not yet checked</span></div>
          <div className="stat"><span className="stat-value">{preview.figures.rerouted}</span><span className="stat-label">Rerouted</span></div>
        </div>

        <h3>Check (from shipment records, before adjustments)</h3>
        <p className={r.balanced ? 'success' : 'error'}>
          Delivered {r.delivered} + Current Day {r.current_day} + Rerouted {r.rerouted} = {r.accounted_for}
          {' · '}Total Available {r.total_available}
          {' · '}{r.balanced ? 'Balanced ✓' : `Difference ${r.total_available - r.accounted_for}`}
        </p>
      </div>

      <form className="card" onSubmit={saveInputs}>
        <h3>Your figures</h3>
        <div className="form-row">
          <label>No of Vans<input type="number" min="0" value={form.vans} onChange={set('vans')} /></label>
          <label>No of Bike<input type="number" min="0" value={form.bikes} onChange={set('bikes')} /></label>
          <label>No of 3PL<input type="number" min="0" value={form.third_party} onChange={set('third_party')} /></label>
        </div>
        <label>
          Reasons (leave empty to use the automatic summary)
          <input value={form.reasons_text} onChange={set('reasons_text')} placeholder={preview.reasons_text || 'No failed deliveries'} />
        </label>
        <label>
          Notes (for you, not in the Excel file)
          <textarea rows="2" value={form.notes} onChange={set('notes')} />
        </label>
        <div className="actions">
          {dirty && <span className="muted">Unsaved changes</span>}
          <button type="submit" disabled={!dirty || saving}>{saving ? 'Saving…' : 'Save figures'}</button>
        </div>
      </form>

      <Adjustments
        adjustments={report.adjustments}
        calculated={preview.calculated}
        saving={saving}
        onAdjust={(field, value, note) => send({ adjust: { [field]: { value, note } } })}
        onClear={(field) => send({ clear_adjust: [field] })}
      />

      <div className="card">
        <h3>Finalize</h3>
        {preview.problems.length > 0 && (
          <div className="error">
            <strong>Must fix first:</strong>
            <ul>{preview.problems.map((p) => <li key={p}>{p}</li>)}</ul>
          </div>
        )}
        {hasWarnings && (
          <div className="warning">
            <strong>Warnings:</strong>
            <ul>{preview.warnings.map((w) => <li key={w.message}>{w.message}</li>)}</ul>
            <label className="checkbox">
              <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />
              I have reviewed these warnings
            </label>
          </div>
        )}
        {dirty && <p className="muted">Save your figures before finalizing.</p>}
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button onClick={() => setAsking(true)} disabled={!canFinalize}>Finalize report</button>
        </div>
      </div>

      {asking && (
        <ConfirmDialog
          title={`Finalize the ${typeLabel(type)} report?`}
          message={`Report date ${date}`}
          items={[
            { label: 'Total Available', value: values.total_available },
            { label: 'Delivered', value: values.delivered },
            { label: 'Current Day', value: values.current_day },
            { label: 'Return', value: values.return },
            { label: 'Vans / Bike / 3PL', value: `${report.vans} / ${report.bikes} / ${report.third_party}` },
          ]}
          note="Once finalized, these figures are frozen. To change them later you will need to start a correction."
          confirmLabel="Finalize"
          busy={saving}
          onConfirm={finalize}
          onCancel={() => setAsking(false)}
        />
      )}
    </>
  )
}

function Adjustments({ adjustments, calculated, saving, onAdjust, onClear }) {
  const [field, setField] = useState('delivered')
  const [value, setValue] = useState('')
  const [note, setNote] = useState('')

  async function submit(event) {
    event.preventDefault()
    if (value === '' || !note.trim()) return
    const result = await onAdjust(field, Number(value), note.trim())
    if (result) {
      setValue('')
      setNote('')
    }
  }

  const entries = Object.entries(adjustments)

  return (
    <form className="card" onSubmit={submit}>
      <h3>Manual adjustments</h3>
      <p className="muted small">
        Only if a calculated figure is wrong. Every adjustment needs a note and is shown as a warning.
      </p>
      {entries.length > 0 && (
        <ul className="plain-list">
          {entries.map(([key, change]) => (
            <li key={key}>
              <strong>{ADJUSTABLE.find((a) => a.key === key)?.label ?? key}</strong>: {calculated[key]} → {change.value}
              <span className="muted"> ({change.note})</span>{' '}
              <button type="button" className="secondary small-button" onClick={() => onClear(key)} disabled={saving}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="form-row">
        <label>
          Figure
          <select value={field} onChange={(e) => setField(e.target.value)}>
            {ADJUSTABLE.map((a) => <option key={a.key} value={a.key}>{a.label} (calculated {calculated[a.key]})</option>)}
          </select>
        </label>
        <label>New value<input type="number" min="0" value={value} onChange={(e) => setValue(e.target.value)} required /></label>
        <label className="grow">Why?<input value={note} onChange={(e) => setNote(e.target.value)} required /></label>
      </div>
      <div className="actions">
        <button type="submit" className="secondary" disabled={saving}>Apply adjustment</button>
      </div>
    </form>
  )
}

function FinalizedReport({ date, type, report, onCorrectionStarted }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function startCorrection(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      onCorrectionStarted(await reports.correct(date, reason.trim(), type))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const values = {
    ...report.figures,
    hub_name: report.hub_name,
    vans: report.vans,
    bikes: report.bikes,
    third_party: report.third_party,
    reasons_text: report.reasons_text || '—',
  }

  return (
    <>
      <div className="card">
        <p className="notice">
          Finalized {new Date(report.finalized_at).toLocaleString()} · version {report.version}
          {report.corrects_version && ` (corrects version ${report.corrects_version}: ${report.correction_reason})`}
        </p>
        <h3>{typeLabel(type)} report row (frozen)</h3>
        <ReportRow values={values} adjusted={report.adjustments} />

        {report.warnings.length > 0 && (
          <div className="warning">
            <strong>Warnings accepted when finalizing:</strong>
            <ul>{report.warnings.map((w) => <li key={w.message}>{w.message}</li>)}</ul>
          </div>
        )}
        {report.notes && <p><strong>Notes:</strong> {report.notes}</p>}

        <h3>Send to the company sheet</h3>
        <CopyRow values={{ ...values, reasons_text: report.reasons_text }} />

        <div className="actions">
          <a className="button" href={reports.downloadUrl(date, undefined, type)}>Download {typeLabel(type)} Excel</a>
        </div>
      </div>

      <form className="card" onSubmit={startCorrection}>
        <h3>Need to correct this report?</h3>
        <p className="muted small">The finalized version is kept unchanged. A new version is created for you to fix.</p>
        <label>
          Reason for the correction
          <input value={reason} onChange={(e) => setReason(e.target.value)} required />
        </label>
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button type="submit" className="secondary" disabled={busy}>{busy ? 'Starting…' : 'Start correction'}</button>
        </div>
      </form>
    </>
  )
}