import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { options, shipments, stockCount } from '../api/client'
import ConfirmDialog from '../components/ConfirmDialog'
import StatusEditor from '../components/StatusEditor'
import { typeLabel } from '../components/TypeSwitch'

// Your ticks are kept in this browser while you count, so a refresh loses nothing.
const STORAGE_KEY = 'hub:stock-checklist'

function today() {
  return new Date().toLocaleDateString('en-CA')
}

function loadTicks() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY))
    if (saved && Array.isArray(saved.ids)) return saved
  } catch {
    // nothing saved, or the browser blocks storage
  }
  return { started: today(), ids: [] }
}

function saveTicks(ticks) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ticks))
  } catch {
    // the ticks still work for this visit
  }
}

/*
 * Stock count from the pending list: walk the shelves and tick every parcel you
 * find (click it, or type / scan its waybill or last 4 digits). What is left
 * unticked is "Not found": find it, or update its status.
 *
 * Nothing is saved on the server by ticking. Only Update status changes a shipment.
 * Parcels on the shelf that were never imported can't be in this list: a full
 * scan on the Stock Count page finds those.
 */
export default function StockChecklistPage() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ticks, setTicks] = useState(loadTicks)
  const [type, setType] = useState('')          // '' = both
  const [show, setShow] = useState('unticked')  // 'unticked' | 'ticked' | 'all'
  const [entry, setEntry] = useState('')
  const [message, setMessage] = useState(null)  // { kind: 'success' | 'warning', text }
  const [narrow, setNarrow] = useState('')      // last 4 digits matching several parcels
  const [notPending, setNotPending] = useState([]) // typed waybills that are not in the list
  const [editing, setEditing] = useState(null)
  const [asking, setAsking] = useState(false)   // "Start a new count?" box
  const inputRef = useRef(null)

  function load() {
    setLoading(true)
    stockCount.pending()
      .then((data) => {
        setRows(data.results)
        setError('')
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  useEffect(() => saveTicks(ticks), [ticks])

  const ticked = useMemo(() => new Set(ticks.ids), [ticks])
  const ofType = rows.filter((r) => !type || r.shipment_type === type)
  const found = ofType.filter((r) => ticked.has(r.shipment_id)).length
  const shown = ofType.filter((r) => {
    if (narrow) return r.waybill.endsWith(narrow)
    if (show === 'unticked') return !ticked.has(r.shipment_id)
    if (show === 'ticked') return ticked.has(r.shipment_id)
    return true
  })

  function setTicked(id, on) {
    setTicks((t) => ({ ...t, ids: on ? [...new Set([...t.ids, id])] : t.ids.filter((x) => x !== id) }))
  }

  // Typed or scanned: a whole waybill, or its last 4 digits.
  function submitEntry(event) {
    event.preventDefault()
    const text = entry.trim()
    if (!text) return
    setEntry('')
    setNarrow('')
    const matches = /^\d{4}$/.test(text)
      ? rows.filter((r) => r.waybill.endsWith(text))
      : rows.filter((r) => r.waybill === text)

    if (matches.length === 1) {
      const row = matches[0]
      if (ticked.has(row.shipment_id)) {
        setMessage({ kind: 'warning', text: `${row.waybill} was already ticked.` })
      } else {
        setTicked(row.shipment_id, true)
        setMessage({ kind: 'success', text: `${row.waybill} found ✓` })
      }
    } else if (matches.length > 1) {
      setNarrow(text)
      setMessage({ kind: 'warning', text: `${matches.length} pending parcels end with ${text}. Tick the right one below.` })
    } else {
      setNotPending((list) => (list.includes(text) ? list : [...list, text]))
      setMessage({
        kind: 'warning',
        text: `${text} is not in the pending list: it may be delivered, left the hub, or never imported.`,
      })
    }
    inputRef.current?.focus()
  }

  async function openShipment(id) {
    setError('')
    try {
      const [shipment, statuses, reasons] = await Promise.all([
        shipments.get(id), options.statuses(), options.reasons(),
      ])
      setEditing({ shipment, statuses, reasons })
    } catch (err) {
      setError(err.message)
    }
  }

  function startNew() {
    setTicks({ started: today(), ids: [] })
    setNotPending([])
    setNarrow('')
    setMessage(null)
    setAsking(false)
    load()
  }

  return (
    <>
      <div className="card">
        <h2>Stock count from the pending list</h2>
        <p className="muted">
          Walk the shelves and tick every parcel you find: click its box, or type or scan its waybill
          (or the last 4 digits) below and press Enter. What is left is <strong>Not found</strong>.
          Prefer scanning everything into a file? <Link to="/stock-count">Use a shelf scan</Link>.
        </p>

        <div className="form-row">
          <label>
            Counting
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">TEMU and Base</option>
              <option value="temu">TEMU only</option>
              <option value="base">Base only</option>
            </select>
          </label>
          <form className="grow" onSubmit={submitEntry}>
            <label>
              Found a parcel? Type or scan it
              <input
                ref={inputRef}
                autoFocus
                value={entry}
                onChange={(e) => setEntry(e.target.value)}
                placeholder="Waybill, or last 4 digits, then Enter"
              />
            </label>
          </form>
        </div>

        {message && <p className={message.kind}>{message.text}</p>}
        {error && <p className="error">{error}</p>}

        <div className="stats">
          <div className="stat"><span className="stat-value">{ofType.length}</span><span className="stat-label">Pending in the app</span></div>
          <div className="stat"><span className="stat-value">{found}</span><span className="stat-label">Found on shelves ✓</span></div>
          <div className="stat"><span className="stat-value">{ofType.length - found}</span><span className="stat-label">Not found yet</span></div>
        </div>

        {!loading && ofType.length > 0 && found === ofType.length && (
          <p className="success">Every pending parcel was found: the shelves and the app agree.</p>
        )}

        <div className="actions" style={{ justifyContent: 'space-between' }}>
          <span className="muted small">
            Count started {ticks.started}. Ticks are kept in this browser until you start a new count.
          </span>
          <button className="secondary small-button" onClick={() => setAsking(true)}>Start a new count</button>
        </div>
      </div>

      <div className="card">
        <div className="toolbar">
          <select value={show} onChange={(e) => { setShow(e.target.value); setNarrow('') }} disabled={Boolean(narrow)}>
            <option value="unticked">Not found yet</option>
            <option value="ticked">Found</option>
            <option value="all">All pending</option>
          </select>
          {narrow && (
            <button className="link-button" onClick={() => setNarrow('')}>Show the full list again</button>
          )}
          <button className="secondary small-button" onClick={load} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh list'}
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Found</th><th>Waybill</th><th>Type</th><th>Status in app</th><th>Arrived</th><th>Last update</th><th></th></tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.shipment_id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={ticked.has(r.shipment_id)}
                      onChange={(e) => setTicked(r.shipment_id, e.target.checked)}
                      aria-label={`Found ${r.waybill}`}
                    />
                  </td>
                  <td className="mono">{r.waybill}</td>
                  <td>{typeLabel(r.shipment_type)}</td>
                  <td>{r.status}</td>
                  <td>{r.arrived}</td>
                  <td>
                    {r.last_update}
                    <span className="muted small"> ({r.days_since_update} day(s) ago)</span>
                  </td>
                  <td>
                    <button className="secondary small-button" onClick={() => openShipment(r.shipment_id)}>
                      Update status
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && shown.length === 0 && (
                <tr><td colSpan="7" className="muted">Nothing in this list.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {notPending.length > 0 && (
          <>
            <h3>Typed but not in the pending list ({notPending.length})</h3>
            <p className="muted small">
              These are on the shelf but the app does not count them as pending. Search them on{' '}
              <Link to="/shipments">Shipments</Link> (delivered or left the hub? correct the status), or
              import them if they were never imported.
            </p>
            <p className="mono">{notPending.join(', ')}</p>
          </>
        )}
      </div>

      {editing && (
        <StatusEditor
          shipment={editing.shipment}
          statuses={editing.statuses}
          reasons={editing.reasons}
          onSaved={() => {
            setEditing(null)
            load() // a shipment that left the hub drops out of the list
          }}
          onClose={() => setEditing(null)}
        />
      )}

      {asking && (
        <ConfirmDialog
          title="Start a new count?"
          message="All ticks are cleared and the list starts again from the beginning."
          items={[{ label: 'Ticks cleared', value: ticks.ids.length }]}
          confirmLabel="Start a new count"
          onConfirm={startNew}
          onCancel={() => setAsking(false)}
        />
      )}
    </>
  )
}