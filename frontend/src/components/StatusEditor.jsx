import { useEffect, useState } from 'react'
import { shipments } from '../api/client'
import ConfirmDialog from './ConfirmDialog'

// Who delivered a shipment (for the Saturday report).
const DELIVERED_BY = [['rider', 'Rider'], ['captain', 'Captain'], ['3pl', '3PL']]

// Fallback threshold if the backend setting hasn't loaded yet; the real value
// (RETURN_AFTER_ATTEMPTS in settings.py) arrives as the returnAfter prop.
const DEFAULT_RETURN_AFTER = 3

// Today's date as YYYY-MM-DD in your own time zone.
function today() {
  return new Date().toLocaleDateString('en-CA')
}

// The last "Date this happened" you picked is remembered until you close the
// tab, so recording yesterday's results this morning needs one change, not one per shipment.
const DATE_KEY = 'hub:status-date'

function rememberedDate() {
  try {
    const saved = sessionStorage.getItem(DATE_KEY)
    return saved && saved <= today() ? saved : today()
  } catch {
    return today()
  }
}

function rememberDate(value) {
  try {
    sessionStorage.setItem(DATE_KEY, value)
  } catch {
    // storage blocked: the date simply isn't remembered
  }
}

function dayLabel(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
}

/*
 * A pop-up panel for changing the status of ONE shipment, or of SEVERAL
 * selected shipments at once (pass `selected`, a list of shipments).
 */
export default function StatusEditor({ shipment, selected, statuses, reasons, returnAfter = DEFAULT_RETURN_AFTER, onSaved, onClose }) {
  const bulk = Boolean(selected)
  // In bulk mode there is no single "current" status, so start with empty choices.
  const start = bulk ? { status: '', failure_reason: null, reason_note: '', delivered_by: '' } : shipment

  const [statusId, setStatusId] = useState(start.status ? String(start.status) : '')
  const [reasonId, setReasonId] = useState(start.failure_reason ? String(start.failure_reason) : '')
  const [reasonNote, setReasonNote] = useState(start.reason_note || '')
  const [deliveredBy, setDeliveredBy] = useState(start.delivered_by || '')
  const [returnWaybill, setReturnWaybill] = useState(start.return_waybill || '')
  const [note, setNote] = useState('')
  const [date, setDateState] = useState(rememberedDate)
  function setDate(value) {
    setDateState(value)
    rememberDate(value)
  }

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [failures, setFailures] = useState([]) // bulk: which shipments broke a rule
  const [confirmingClose, setConfirmingClose] = useState(false) // "Discard changes?" box is open
  const [finalizedWarning, setFinalizedWarning] = useState('') // "that day is finalized" message

  const status = statuses.find((s) => String(s.id) === statusId)
  const reason = reasons.find((r) => String(r.id) === reasonId)
  const needsReason = Boolean(status?.requires_reason)
  const needsReasonNote = needsReason && Boolean(reason?.is_other)
  const isDelivered = status?.category === 'delivered'
  const isLeftHub = status?.category === 'left_hub'  // e.g. Initiated Return: wants a new waybill
  const deliveredCount = bulk
    ? selected.filter((s) => s.status_category === 'delivered').length
    : shipment.status_category === 'delivered' ? 1 : 0
  const wasDelivered = deliveredCount > 0

  // Only adding who delivered a shipment that is already delivered: no note needed.
  const deliveredOnes = bulk
    ? selected.filter((s) => s.status_category === 'delivered')
    : wasDelivered ? [shipment] : []
  const onlyAddingWho =
    isDelivered &&
    deliveredBy !== '' &&
    deliveredOnes.every((s) => String(s.status) === statusId && !s.delivered_by)
  const noteRequired = wasDelivered && !onlyAddingWho

  // Reminder: a parcel with enough failed attempts that is still at the hub
  // should be sent back. Counting the attempt being recorded right now.
  const failedNow = needsReason && status?.category === 'outstanding'
  const attemptsAfter = (bulk ? 0 : shipment.attempt_count || 0) + (failedNow ? 1 : 0)
  const atHub = !bulk && ['unchecked', 'outstanding', 'returned'].includes(shipment.status_category)
  // Don't nag when you are actually resolving it (delivering, or sending it back).
  const leavingHub = status && !['unchecked', 'outstanding', 'returned'].includes(status.category)
  const remindReturn = atHub && !leavingHub && attemptsAfter >= returnAfter
  // An "Initiated Return" style status to offer as a one-click choice, if one exists.
  const returnStatus = statuses.find((s) => s.category === 'left_hub' && /return/i.test(s.name))

  // A repeat of the SAME failed status on a LATER day is a genuine new attempt,
  // so allow saving it even though nothing else changed (otherwise Save stays greyed out).
  const repeatAttempt =
    !bulk && failedNow && String(shipment.status) === statusId &&
    Boolean(shipment.last_update) && date > shipment.last_update

  const dirty =
    statusId !== (start.status ? String(start.status) : '') ||
    reasonId !== (start.failure_reason ? String(start.failure_reason) : '') ||
    reasonNote !== (start.reason_note || '') ||
    (isDelivered && deliveredBy !== (start.delivered_by || '')) ||
    (isLeftHub && returnWaybill !== (start.return_waybill || '')) ||
    note !== '' ||
    repeatAttempt

  // Ask before throwing away changes you haven't saved.
  function close() {
    if (saving) return
    if (dirty) {
      setConfirmingClose(true)
      return
    }
    onClose()
  }

  // Close with the Escape key (unless the "Discard changes?" box is open: Esc closes that box).
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape' && !confirmingClose && !finalizedWarning) close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  function handleSubmit(event) {
    event.preventDefault()
    submit(false)
  }

  async function submit(allowFinalizedDay) {
    if (saving) return
    setFinalizedWarning('')

    setSaving(true)
    setError('')
    setFieldErrors({})
    setFailures([])
    const change = {
      status: Number(statusId),
      failure_reason: needsReason && reasonId ? Number(reasonId) : null,
      reason_note: needsReasonNote ? reasonNote : '',
      delivered_by: isDelivered ? deliveredBy : '',
      return_waybill: isLeftHub ? returnWaybill.trim() : '',
      note,
      effective_date: date,
      allow_finalized_day: allowFinalizedDay,
    }
    try {
      const result = bulk
        ? await shipments.bulkChangeStatus(selected.map((s) => s.id), change)
        : await shipments.changeStatus(shipment.id, change)
      onSaved(result)
    } catch (err) {
      if (err.details?.code === 'finalized_day') {
        setFinalizedWarning(err.message) // ask first, then save with allow_finalized_day
      } else {
        setError(err.message)
        setFieldErrors(err.details || {})
        setFailures(err.details?.failures || [])
      }
    } finally {
      setSaving(false)
    }
  }

  // Django sends field errors as lists: {"note": ["..."]}
  const fieldError = (name) => fieldErrors[name]?.[0]

  return (
    <>
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

          {remindReturn && (
            <div className="notice" style={{ marginBottom: 16 }}>
              <strong>Reminder:</strong> this shipment has {attemptsAfter} failed delivery attempt(s).
              Hub policy is to initiate a return.
              {returnStatus && statusId !== String(returnStatus.id) && (
                <>
                  {' '}
                  <button type="button" className="link-button" onClick={() => setStatusId(String(returnStatus.id))}>
                    Set to {returnStatus.name}
                  </button>
                </>
              )}
            </div>
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

          {isDelivered && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>Delivered by</div>
              <div style={{ display: 'flex', gap: 8 }}>
                {DELIVERED_BY.map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={deliveredBy === value ? '' : 'secondary'}
                    style={{ flex: 1 }}
                    onClick={() => setDeliveredBy(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {fieldError('delivered_by') && <span className="field-error">{fieldError('delivered_by')}</span>}
            </div>
          )}

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

          {isLeftHub && (
            <label>
              New return waybill (optional)
              <input
                value={returnWaybill}
                onChange={(e) => setReturnWaybill(e.target.value)}
                placeholder="e.g. 1599000032"
              />
              <span className="muted small">The new waybill for the return. It goes in the TEMU return email.</span>
            </label>
          )}

          <label>
            {!noteRequired
              ? 'Note (optional)'
              : bulk
                ? `Reason for change (required: ${deliveredCount} selected shipment(s) already delivered)`
                : 'Reason for change (required: this shipment is already delivered)'}
            <textarea
              rows="2"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              required={noteRequired}
            />
            {fieldError('note') && <span className="field-error">{fieldError('note')}</span>}
          </label>

          <label>
            Date this happened
            <input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} required />
            {onlyAddingWho && <span className="muted small">Only adding who delivered it: the delivery keeps its original date.</span>}
            {date !== today() && !onlyAddingWho && (
              <span className="notice" style={{ display: 'block', marginTop: 8, fontWeight: 400 }}>
                Recording for <strong>{dayLabel(date)}</strong>, not today.{' '}
                <button type="button" className="link-button" onClick={() => setDate(today())}>Use today</button>
              </span>
            )}
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
            <button type="submit" disabled={saving || !dirty || (isDelivered && !deliveredBy)}>{saving ? 'Saving…' : bulk ? `Update ${selected.length}` : 'Save'}</button>
          </div>
        </form>
      </div>

      {finalizedWarning && (
        <ConfirmDialog
          title="That day's report is already finalized"
          message={finalizedWarning}
          confirmLabel="Save anyway"
          busy={saving}
          onConfirm={() => submit(true)}
          onCancel={() => setFinalizedWarning('')}
        />
      )}

      {confirmingClose && (
        <ConfirmDialog
          title="Discard your changes?"
          message="The status change you started has not been saved. If you close now, it will be lost."
          confirmLabel="Discard"
          onConfirm={onClose}
          onCancel={() => setConfirmingClose(false)}
        />
      )}
    </>
  )
}