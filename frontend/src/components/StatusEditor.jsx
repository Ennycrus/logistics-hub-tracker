import { useEffect, useState } from 'react'
import { shipments } from '../api/client'

// Today's date as YYYY-MM-DD in your own time zone.
function today() {
  return new Date().toLocaleDateString('en-CA')
}

/*
 * A pop-up panel for changing the status of ONE shipment, or of SEVERAL
 * selected shipments at once (pass `selected`, a list of shipments).
 *
 * Shows only the fields that matter:
 *   - Reason          when the chosen status needs one (e.g. Delivery Unsuccessful)
 *   - Explanation     when the reason is "Other"
 *   - Reason for change (required) when the shipment is already Delivered (rule C)
 *
 * Django still checks every rule; any error it sends back is shown here.
 */
export default function StatusEditor({ shipment, selected, statuses, reasons, onSaved, onClose }) {
  const bulk = Boolean(selected)
  // In bulk mode there is no single "current" status, so start with empty choices.
  const start = bulk ? { status: '', failure_reason: null, reason_note: '' } : shipment

  const [statusId, setStatusId] = useState(start.status ? String(start.status) : '')
  const [reasonId, setReasonId] = useState(start.failure_reason ? String(start.failure_reason) : '')
  const [reasonNote, setReasonNote] = useState(start.reason_note || '')
  const [note, setNote] = useState('')
  const [date, setDate] = useState(today())

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [failures, setFailures] = useState([]) // bulk: which shipments broke a rule

  const status = statuses.find((s) => String(s.id) === statusId)
  const reason = reasons.find((r) => String(r.id) === reasonId)
  const needsReason = Boolean(status?.requires_reason)
  const needsReasonNote = needsReason && Boolean(reason?.is_other)
  const deliveredCount = bulk
    ? selected.filter((s) => s.status_category === 'delivered').length
    : shipment.status_category === 'delivered' ? 1 : 0
  const wasDelivered = deliveredCount > 0

  const dirty =
    statusId !== (start.status ? String(start.status) : '') ||
    reasonId !== (start.failure_reason ? String(start.failure_reason) : '') ||
    reasonNote !== (start.reason_note || '') ||
    note !== ''

  // Ask before throwing away changes you haven't saved.
  function close() {
    if (saving) return
    if (dirty && !window.confirm('Discard your unsaved changes?')) return
    onClose()
  }

  // Close with the Escape key.
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  async function handleSubmit(event) {
    event.preventDefault()
    if (saving) return

    setSaving(true)
    setError('')
    setFieldErrors({})
    setFailures([])
    const change = {
      status: Number(statusId),
      failure_reason: needsReason && reasonId ? Number(reasonId) : null,
      reason_note: needsReasonNote ? reasonNote : '',
      note,
      effective_date: date,
    }
    try {
      const result = bulk
        ? await shipments.bulkChangeStatus(selected.map((s) => s.id), change)
        : await shipments.changeStatus(shipment.id, change)
      onSaved(result)
    } catch (err) {
      setError(err.message)
      setFieldErrors(err.details || {})
      setFailures(err.details?.failures || [])
    } finally {
      setSaving(false)
    }
  }

  // Django sends field errors as lists: {"note": ["..."]}
  const fieldError = (name) => fieldErrors[name]?.[0]

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <form className="card dialog" onSubmit={handleSubmit}>
        <h2>{bulk ? `Update ${selected.length} shipments` : 'Update status'}</h2>
        {bulk ? (
          <p className="muted">
            All {selected.length} selected shipments get the same status. If any one of them breaks a rule,
            nothing is saved.
          </p>
        ) : (
          <p className="muted">
            Waybill <span className="mono">{shipment.waybill_number}</span> · currently{' '}
            <span className={`badge badge-${shipment.status_category}`}>{shipment.status_name}</span>
          </p>
        )}

        <label>
          New status
          <select value={statusId} onChange={(e) => setStatusId(e.target.value)} autoFocus required>
            {bulk && <option value="">Choose a status…</option>}
            {statuses.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </label>

        {needsReason && (
          <label>
            Reason
            <select value={reasonId} onChange={(e) => setReasonId(e.target.value)} required>
              <option value="">Choose a reason…</option>
              {reasons.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
            {fieldError('failure_reason') && <span className="field-error">{fieldError('failure_reason')}</span>}
          </label>
        )}

        {needsReasonNote && (
          <label>
            Explain "Other"
            <input value={reasonNote} onChange={(e) => setReasonNote(e.target.value)} required />
            {fieldError('reason_note') && <span className="field-error">{fieldError('reason_note')}</span>}
          </label>
        )}

        <label>
          {!wasDelivered
            ? 'Note (optional)'
            : bulk
              ? `Reason for change (required: ${deliveredCount} selected shipment(s) already delivered)`
              : 'Reason for change (required: this shipment is already delivered)'}
          <textarea
            rows="2"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            required={wasDelivered}
          />
          {fieldError('note') && <span className="field-error">{fieldError('note')}</span>}
        </label>

        <label>
          Date this happened
          <input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} required />
          {fieldError('effective_date') && <span className="field-error">{fieldError('effective_date')}</span>}
        </label>

        {error && <p className="error">{error}</p>}
        {failures.length > 0 && (
          <ul className="failure-list">
            {failures.map((f) => (
              <li key={f.id}><span className="mono">{f.waybill_number}</span>: {f.error}</li>
            ))}
          </ul>
        )}

        <div className="dialog-actions">
          <button type="button" className="secondary" onClick={close} disabled={saving}>Cancel</button>
          <button type="submit" disabled={saving || !dirty}>{saving ? 'Saving…' : bulk ? `Update ${selected.length}` : 'Save'}</button>
        </div>
      </form>
    </div>
  )
}