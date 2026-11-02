import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { options, reports } from '../api/client'
import ShipmentDetails from '../components/ShipmentDetails'
import StatusEditor from '../components/StatusEditor'
import TypeSwitch, { typeLabel, useShipmentType } from '../components/TypeSwitch'

function today() {
  return new Date().toLocaleDateString('en-CA')
}

const TABS = [
  { value: 'old_pending', label: 'Old Pending' },
  { value: 'inbound', label: 'Inbound' },
  { value: '', label: 'All' },
]

const CATEGORY_FILTERS = [
  { value: '', label: 'All statuses' },
  { value: 'unchecked', label: 'Not yet checked' },
  { value: 'outstanding', label: 'Outstanding' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'returned', label: 'Returned to hub' },
  { value: 'left_hub', label: 'Left the hub' },
]

const PAGE_SIZE = 50 // must match PAGE_SIZE in Django's settings.py

/*
 * The shipments in one day's report (TEMU or Base), to review before finalizing.
 * Old Pending is listed longest-waiting first.
 * Status shown is each shipment's CURRENT status.
 */
export default function PendingPage() {
  const [date, setDate] = useState(today())
  const [type, setType] = useShipmentType()
  const [kind, setKind] = useState('old_pending')
  const [category, setCategory] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const [data, setData] = useState({ count: 0, results: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const [statuses, setStatuses] = useState([])
  const [reasons, setReasons] = useState([])
  const [editing, setEditing] = useState(null)
  const [detailsId, setDetailsId] = useState(null)
  const [detailsVersion, setDetailsVersion] = useState(0)

  useEffect(() => {
    Promise.all([options.statuses(), options.reasons()])
      .then(([s, r]) => {
        setStatuses(s)
        setReasons(r)
      })
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    let ignore = false
    const timer = setTimeout(async () => {
      setLoading(true)
      setError('')
      try {
        const result = await reports.shipments(date, { type, kind, category, search: search.trim(), page })
        if (!ignore) setData(result)
      } catch (err) {
        if (!ignore) {
          setData({ count: 0, results: [] })
          setError(err.message)
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    }, 300)
    return () => {
      ignore = true
      clearTimeout(timer)
    }
  }, [date, type, kind, category, search, page, reloadKey])

  // Any filter change starts again on page 1.
  function change(setter) {
    return (value) => {
      setter(value)
      setPage(1)
      setMessage('')
    }
  }

  function handleSaved(result) {
    setEditing(null)
    setDetailsVersion((v) => v + 1)
    setMessage(
      result.changed
        ? `${result.shipment.waybill_number} is now "${result.shipment.status_name}".`
        : 'Nothing changed.',
    )
    setReloadKey((k) => k + 1)
  }

  const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE))

  return (
    <div className="card">
      <div className="title-row">
        <h2>Pending · {typeLabel(type)}</h2>
        <TypeSwitch value={type} onChange={change(setType)} />
      </div>

      <div className="title-row">
        <div className="tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.value}
              role="tab"
              aria-selected={kind === t.value}
              className={`tab ${kind === t.value ? 'active' : ''}`}
              onClick={() => change(setKind)(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <label className="inline-date">
          Report date
          <input type="date" value={date} max={today()} onChange={(e) => change(setDate)(e.target.value)} />
        </label>
      </div>

      <div className="toolbar">
        <input
          type="search"
          placeholder="Search waybill number… (4 digits = last four)"
          value={search}
          onChange={(e) => change(setSearch)(e.target.value)}
        />
        <select value={category} onChange={(e) => change(setCategory)(e.target.value)}>
          {CATEGORY_FILTERS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
      </div>

      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      <p className="muted">
        {loading ? 'Loading…' : `${data.count} shipment(s) in the ${date} ${typeLabel(type)} report`}
        {' · '}<Link to="/report">Open the daily report →</Link>
      </p>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Waybill Number</th>
              <th>Counted as</th>
              <th>Days at hub</th>
              <th>Current status</th>
              <th>Reason</th>
              <th>Notes</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((r) => {
              const s = r.shipment
              return (
                <tr key={r.id}>
                  <td>
                    <button className="link-button mono" onClick={() => setDetailsId(s.id)}>
                      {s.waybill_number}
                    </button>
                  </td>
                  <td>{r.kind === 'inbound' ? 'Inbound' : 'Old Pending'}</td>
                  <td>
                    <span className={r.days_at_hub >= 3 ? 'days-old' : ''}>
                      {r.days_at_hub === 0 ? 'Today' : `${r.days_at_hub} day${r.days_at_hub === 1 ? '' : 's'}`}
                    </span>
                  </td>
                  <td><span className={`badge badge-${s.status_category}`}>{s.status_name}</span></td>
                  <td>
                    {s.failure_reason_name || '—'}
                    {s.reason_note && <div className="muted small">{s.reason_note}</div>}
                  </td>
                  <td>{s.notes || '—'}</td>
                  <td>
                    <button
                      className="secondary small-button"
                      onClick={() => {
                        setMessage('')
                        setEditing(s)
                      }}
                      disabled={statuses.length === 0}
                    >
                      Update
                    </button>
                  </td>
                </tr>
              )
            })}
            {!loading && data.results.length === 0 && (
              <tr><td colSpan="7" className="muted">No shipments match.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pager">
        <button className="secondary" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}>← Previous</button>
        <span className="muted">Page {page} of {totalPages}</span>
        <button className="secondary" disabled={page >= totalPages || loading} onClick={() => setPage(page + 1)}>Next →</button>
      </div>

      {editing && (
        <StatusEditor
          shipment={editing}
          statuses={statuses}
          reasons={reasons}
          onSaved={handleSaved}
          onClose={() => setEditing(null)}
        />
      )}

      {detailsId && (
        <ShipmentDetails
          key={`${detailsId}-${detailsVersion}`}
          shipmentId={detailsId}
          onClose={() => setDetailsId(null)}
          onChanged={() => setReloadKey((k) => k + 1)}
          onUpdateStatus={(shipment) => {
            setMessage('')
            setEditing(shipment)
          }}
        />
      )}
    </div>
  )
}
