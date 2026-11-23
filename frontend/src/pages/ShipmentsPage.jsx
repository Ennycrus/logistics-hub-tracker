import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { options, settings, shipments } from '../api/client'
import ShipmentDetails from '../components/ShipmentDetails'
import StatusEditor from '../components/StatusEditor'
import TrackLink from '../components/TrackLink'
import { TYPES, typeLabel } from '../components/TypeSwitch'

// Matches the status categories in Django (core/models.py).
const CATEGORY_FILTERS = [
  { value: '', label: 'All statuses' },
  { value: 'unchecked', label: 'Not yet checked' },
  { value: 'outstanding', label: 'Outstanding' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'returned', label: 'Returned to hub' },
  { value: 'left_hub', label: 'Left the hub' },
  // Checks for the Saturday report (not status categories):
  { value: 'delivered_none', label: 'Delivered, nobody recorded' },
  { value: 'stale', label: 'Stuck: no update for 7+ days' },
  { value: 'ready_return', label: 'Ready for return (3+ failed attempts)' },
]

// What each filter asks Django for.
function filterParams(filter) {
  if (filter === 'delivered_none') return { delivered_by: 'none' }
  if (filter === 'stale') return { stale_days: 7 }
  if (filter === 'ready_return') return { ready_for_return: 1 }
  return { category: filter }
}

const DELIVERED_BY_LABELS = { rider: 'Rider', captain: 'Captain', '3pl': '3PL' }

const PAGE_SIZE = 50 // must match PAGE_SIZE in Django's settings.py

/*
 * The shipments table: search by waybill, filter by status and type, 50 rows per page.
 * Typing exactly 4 digits finds waybills ENDING with them (the last four).
 * The status filter lives in the address (?filter=stale, ?filter=delivered_none...),
 * so the Saturday report can link to a list, and clicking Shipments in the menu
 * always starts again with All statuses.
 * Delivered shipments are hidden until you tick "Show delivered", pick the
 * Delivered filter, or search for a waybill (a search always finds it).
 * Click a waybill number to see its details, notes and history.
 * Click "Track" to open the company's tracking page for that waybill (set the address in Settings).
 * Click "Update" on a row to change its status, or tick several rows and
 * use "Update selected" to change them all at once.
 */
export default function ShipmentsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const wanted = searchParams.get('filter') || ''
  const category = CATEGORY_FILTERS.some((f) => f.value === wanted) ? wanted : ''
  function setCategory(value) {
    setSearchParams(value ? { filter: value } : {})
  }
  const [search, setSearch] = useState(searchParams.get('search') || '')
  const [type, setType] = useState('') // '' = TEMU and Base
  const [showDelivered, setShowDelivered] = useState(false)
  // Hide delivered unless you asked for them: the box, a delivered filter, or a search.
  const hideDelivered =
    !showDelivered && search.trim() === '' && !['delivered', 'delivered_none'].includes(category)
  const [page, setPage] = useState(1)

  const [data, setData] = useState({ count: 0, results: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [statuses, setStatuses] = useState([])
  const [reasons, setReasons] = useState([])
  const [trackingUrl, setTrackingUrl] = useState('') // from Settings; empty = no Track buttons
  const [returnAfter, setReturnAfter] = useState(3) // failed attempts before the return reminder
  const [editing, setEditing] = useState(null)     // the shipment being updated, or null
  const [selectedIds, setSelectedIds] = useState([]) // ticked rows (this page only)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [detailsId, setDetailsId] = useState(null) // shipment whose details panel is open
  const [detailsVersion, setDetailsVersion] = useState(0) // change it to reload the panel
  const [message, setMessage] = useState('')       // "Saved" confirmation
  const [reloadKey, setReloadKey] = useState(0)    // change it to reload the table

  // Load the dropdown options and the tracking page address once.
  useEffect(() => {
    Promise.all([options.statuses(), options.reasons(), settings.hub()])
      .then(([s, r, hub]) => {
        setStatuses(s)
        setReasons(r)
        setTrackingUrl(hub.tracking_url)
        if (hub.return_after_attempts) setReturnAfter(hub.return_after_attempts)
      })
      .catch((err) => setError(err.message))
  }, [])

  // A different filter (also from a link or the menu) starts on page 1.
  useEffect(() => setPage(1), [category])

  // Reload the table whenever the search, filter or page changes.
  useEffect(() => {
    let ignore = false   // stops an old, slow request overwriting a newer one
    setSelectedIds([])   // never keep ticks on rows you can no longer see

    // Wait 300 ms after the last key press, so we don't call Django on every letter.
    const timer = setTimeout(async () => {
      setLoading(true)
      setError('')
      try {
        const result = await shipments.list({
          search: search.trim(), ...filterParams(category), type, page,
          hide_delivered: hideDelivered ? 1 : undefined,
        })
        if (!ignore) setData(result)
      } catch (err) {
        if (!ignore) setError(err.message)
      } finally {
        if (!ignore) setLoading(false)
      }
    }, 300)

    return () => {
      ignore = true
      clearTimeout(timer)
    }
  }, [search, category, type, page, reloadKey, hideDelivered])

  // Arrived from a quick lookup (?search=...&open=1): open the editor only for an
  // EXACT waybill match, so a loose partial match never flings open the wrong
  // parcel. If nothing matches at all, say so plainly. Then drop the 'open' flag
  // so closing the editor doesn't reopen it.
  useEffect(() => {
    if (loading || searchParams.get('open') !== '1') return
    const term = (searchParams.get('search') || '').trim()
    const exact = data.results.find((s) => s.waybill_number === term)
    if (exact && !editing) {
      setEditing(exact)
    } else if (data.results.length === 0) {
      setMessage(`No shipment found for "${term}".`)
    }
    const next = new URLSearchParams(searchParams)
    next.delete('open')
    setSearchParams(next, { replace: true })
  }, [loading, data, editing, searchParams, setSearchParams])

  function handleBulkSaved(result) {
    setBulkOpen(false)
    setMessage(
      `${result.changed} shipment(s) updated` +
        (result.unchanged ? `, ${result.unchanged} already had that status.` : '.'),
    )
    setReloadKey((k) => k + 1)
  }

  const pageIds = data.results.map((s) => s.id)
  const allTicked = pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id))
  const selectedRows = data.results.filter((s) => selectedIds.includes(s.id))

  function toggle(id) {
    setSelectedIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]))
  }

  function handleSaved(result) {
    setEditing(null)
    setDetailsVersion((v) => v + 1) // an open details panel shows the new history
    setMessage(
      result.changed
        ? `${result.shipment.waybill_number} is now "${result.shipment.status_name}".`
        : 'Nothing changed.',
    )
    setReloadKey((k) => k + 1) // reload so the row (and the filter) are up to date
  }

  const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE))

  return (
    <div className="card">
      <h2>Shipments</h2>

      <div className="toolbar">
        <input
          type="search"
          placeholder="Search waybill number… (4 digits = last four)"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1) // a new search starts on page 1
          }}
        />
        <select
          value={category}
          onChange={(e) => {
            setCategory(e.target.value)
            setPage(1)
          }}
        >
          {CATEGORY_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
        <select
          value={type}
          onChange={(e) => {
            setType(e.target.value)
            setPage(1)
          }}
        >
          <option value="">TEMU and Base</option>
          {TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label} only</option>
          ))}
        </select>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={showDelivered}
            onChange={(e) => {
              setShowDelivered(e.target.checked)
              setPage(1)
            }}
          />
          Show delivered
        </label>
      </div>

      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      <p className="muted">
        {loading ? 'Loading…' : `${data.count} shipment${data.count === 1 ? '' : 's'}`}
        {!loading && hideDelivered && ' (delivered hidden)'}
      </p>

      {selectedIds.length > 0 && (
        <div className="bulk-bar">
          <strong>{selectedIds.length} selected</strong>
          <button className="small-button" onClick={() => { setMessage(''); setBulkOpen(true) }}>
            Update selected
          </button>
          <button className="secondary small-button" onClick={() => setSelectedIds([])}>Clear</button>
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="check-col">
                <input
                  type="checkbox"
                  aria-label="Select all on this page"
                  checked={allTicked}
                  onChange={() => setSelectedIds(allTicked ? [] : pageIds)}
                  disabled={pageIds.length === 0}
                />
              </th>
              <th>Waybill Number</th>
              <th>Shipment Type</th>
              <th>Delivery Status</th>
              <th>Reason</th>
              <th>Notes</th>
              <th>Last Updated</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((s) => (
              <tr key={s.id} className={selectedIds.includes(s.id) ? 'selected' : ''}>
                <td className="check-col">
                  <input
                    type="checkbox"
                    aria-label={`Select ${s.waybill_number}`}
                    checked={selectedIds.includes(s.id)}
                    onChange={() => toggle(s.id)}
                  />
                </td>
                <td>
                  <button className="link-button mono" onClick={() => setDetailsId(s.id)}>
                    {s.waybill_number}
                  </button>
                </td>
                <td>{typeLabel(s.shipment_type)}</td>
                <td>
                  <span className={`badge badge-${s.status_category}`}>{s.status_name}</span>
                  {s.status_category === 'delivered' && (
                    <div className="muted small">
                      {s.delivered_by ? `by ${DELIVERED_BY_LABELS[s.delivered_by]}` : 'nobody recorded'}
                    </div>
                  )}
                  {s.ready_for_return && (
                    <div className="small" style={{ color: '#b45309', fontWeight: 600, marginTop: 4 }}>
                      ⚠ {s.attempt_count} attempts — initiate return
                    </div>
                  )}
                </td>
                <td>
                  {s.failure_reason_name || '—'}
                  {s.reason_note && <div className="muted small">{s.reason_note}</div>}
                </td>
                <td>{s.notes || '—'}</td>
                <td className="small">{new Date(s.updated_at).toLocaleString()}</td>
                <td className="row-actions">
                  <TrackLink template={trackingUrl} waybill={s.waybill_number} />
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
            ))}
            {!loading && data.results.length === 0 && (
              <tr>
                <td colSpan="8" className="muted">No shipments match.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pager">
        <button className="secondary" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}>
          ← Previous
        </button>
        <span className="muted">Page {page} of {totalPages}</span>
        <button className="secondary" disabled={page >= totalPages || loading} onClick={() => setPage(page + 1)}>
          Next →
        </button>
      </div>

      {editing && (
        <StatusEditor
          shipment={editing}
          statuses={statuses}
          reasons={reasons}
          returnAfter={returnAfter}
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

      {bulkOpen && (
        <StatusEditor
          selected={selectedRows}
          statuses={statuses}
          reasons={reasons}
          onSaved={handleBulkSaved}
          onClose={() => setBulkOpen(false)}
        />
      )}
    </div>
  )
}