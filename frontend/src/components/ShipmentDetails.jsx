import { useEffect, useState } from 'react'
import { shipments } from '../api/client'
import ConfirmDialog from './ConfirmDialog'

function formatDate(value) {
  return new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

/*
 * A panel that slides in from the right with one shipment's details:
 * current status, your notes (editable), and its full status history.
 *
 * onChanged() tells the Shipments page to reload its table after notes are saved.
 * onUpdateStatus(shipment) opens the normal "Update status" panel.
 */
export default function ShipmentDetails({ shipmentId, onClose, onChanged, onUpdateStatus }) {
  const [shipment, setShipment] = useState(null)
  const [error, setError] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [confirmingClose, setConfirmingClose] = useState(false) // "Discard notes?" box is open

  useEffect(() => {
    let ignore = false
    shipments
      .get(shipmentId)
      .then((data) => {
        if (ignore) return
        setShipment(data)
        setNotes(data.notes)
      })
      .catch((err) => !ignore && setError(err.message))
    return () => {
      ignore = true
    }
  }, [shipmentId])

  const dirty = shipment !== null && notes.trim() !== shipment.notes

  function close() {
    if (saving) return
    if (dirty) {
      setConfirmingClose(true)
      return
    }
    onClose()
  }

  // Close with the Escape key (unless the "Discard notes?" box is open: Esc closes that box).
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape' && !confirmingClose) close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  async function saveNotes(event) {
    event.preventDefault()
    if (saving || !dirty) return
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      const updated = await shipments.saveNotes(shipment.id, notes)
      setShipment({ ...shipment, notes: updated.notes })
      setNotes(updated.notes)
      setSaved(true)
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // Newest change first is easier to read.
  const history = shipment ? [...shipment.history].reverse() : []

  return (
    <>
      <div className="drawer-backdrop" onMouseDown={(e) => e.target === e.currentTarget && close()}>
        <aside className="drawer" role="dialog" aria-label="Shipment details">
          <div className="drawer-header">
            <div>
              <div className="breadcrumb">Shipment</div>
              <h2 className="mono">{shipment?.waybill_number ?? '…'}</h2>
            </div>
            <button className="secondary small-button" onClick={close}>Close</button>
          </div>

          {error && <p className="error">{error}</p>}
          {!shipment && !error && <p className="muted">Loading…</p>}

          {shipment && (
            <>
              <dl className="facts">
                <dt>Status</dt>
                <dd><span className={`badge badge-${shipment.status_category}`}>{shipment.status_name}</span></dd>
                <dt>Reason</dt>
                <dd>
                  {shipment.failure_reason_name || '—'}
                  {shipment.reason_note && <span className="muted"> ({shipment.reason_note})</span>}
                </dd>
                <dt>First scanned</dt>
                <dd>{formatDate(shipment.first_seen_date)}</dd>
                <dt>Last updated</dt>
                <dd>{new Date(shipment.updated_at).toLocaleString()}</dd>
              </dl>

              <div className="actions">
                <button className="small-button" onClick={() => onUpdateStatus(shipment)} disabled={dirty}>
                  Update status
                </button>
              </div>

              <form onSubmit={saveNotes}>
                <h3>Notes</h3>
                <textarea
                  rows="3"
                  maxLength={1000}
                  placeholder="Your own reminders, e.g. customer asked for evening delivery"
                  value={notes}
                  onChange={(e) => {
                    setNotes(e.target.value)
                    setSaved(false)
                  }}
                />
                <div className="actions">
                  {saved && <span className="success-text">Saved</span>}
                  {dirty && <span className="muted small">Unsaved changes</span>}
                  <button type="submit" className="small-button" disabled={!dirty || saving}>
                    {saving ? 'Saving…' : 'Save notes'}
                  </button>
                </div>
              </form>

              <h3>History</h3>
              <ol className="timeline">
                {history.map((h) => (
                  <li key={h.id}>
                    <div className="timeline-date">
                      {formatDate(h.effective_date)}
                      <span className="muted small"> · recorded {new Date(h.changed_at).toLocaleString()}</span>
                    </div>
                    <div>
                      {h.old_status ? <>{h.old_status} → </> : null}
                      <strong>{h.new_status}</strong>
                    </div>
                    {h.failure_reason && (
                      <div className="small">
                        Reason: {h.failure_reason}{h.reason_note && ` (${h.reason_note})`}
                      </div>
                    )}
                    {h.note && <div className="small muted">“{h.note}”</div>}
                  </li>
                ))}
              </ol>
            </>
          )}
        </aside>
      </div>

      {confirmingClose && (
        <ConfirmDialog
          title="Discard your notes?"
          message="Your changes to the notes have not been saved. If you close now, they will be lost."
          confirmLabel="Discard"
          onConfirm={onClose}
          onCancel={() => setConfirmingClose(false)}
        />
      )}
    </>
  )
}