import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { returns } from '../api/client'

/*
 * TEMU returns: shipments you've sent back to the sender that have a new
 * return waybill and haven't been emailed to the partner yet.
 *
 * Tick the ones to send, click "Open in Gmail" (it opens a Gmail compose tab,
 * filled in, for you to review and send), then "Mark as emailed" so they drop
 * off. Recipients and subject come from Settings. Nothing is emailed by the server.
 */
function buildBody(rows) {
  const lines = rows.map((r) => `${r.waybill_number}  \u2192  ${r.return_waybill}`).join('\n')
  return (
    'Dear Partner,\n\n' +
    `Please find below the details of ${rows.length} TEMU return shipment(s), along with their new waybill numbers.\n\n` +
    'OLD WAYBILL  \u2192  NEW WAYBILL\n' +
    `${lines}\n\n` +
    'Kindly acknowledge receipt upon delivery.\n\n' +
    'Thank you.'
  )
}

export default function ReturnsPage() {
  const [data, setData] = useState({ count: 0, results: [], email_to: '', email_subject: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [selectedIds, setSelectedIds] = useState([])
  const [copied, setCopied] = useState(false)

  function load() {
    setLoading(true)
    returns.pending('temu')
      .then((d) => {
        setData(d)
        setSelectedIds(d.results.map((r) => r.id)) // everything ticked by default
        setError('')
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const selectedRows = useMemo(
    () => data.results.filter((r) => selectedIds.includes(r.id)),
    [data, selectedIds],
  )
  const allTicked = data.results.length > 0 && selectedIds.length === data.results.length

  function toggle(id) {
    setSelectedIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]))
  }

  // Open Gmail's compose window in a new tab, with recipients, subject and body
  // filled in. Works with Gmail in the browser (no desktop mail app needed).
  function openEmail() {
    if (selectedRows.length === 0) return
    const to = encodeURIComponent(data.email_to || '')
    const su = encodeURIComponent(data.email_subject || 'Temu RETURN WAYBILL DETAILS')
    const body = encodeURIComponent(buildBody(selectedRows))
    const url = `https://mail.google.com/mail/?view=cm&fs=1&to=${to}&su=${su}&body=${body}`
    const win = window.open(url, '_blank', 'noopener')
    // If a pop-up blocker stops the new tab, fall back to the same tab.
    if (!win) window.location.href = url
  }

  async function copyText() {
    try {
      await navigator.clipboard.writeText(buildBody(selectedRows))
      setCopied(true)
    } catch {
      setError('Could not copy. Select the text in the preview and copy it yourself.')
    }
  }

  async function markEmailed() {
    if (selectedRows.length === 0) return
    setError('')
    try {
      const result = await returns.markEmailed(selectedRows.map((r) => r.id))
      setMessage(`${result.marked} shipment(s) marked as emailed.`)
      setCopied(false)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <div className="card">
        <h2>TEMU returns to send</h2>
        <p className="muted">
          Shipments sent back to the sender with a new return waybill, not yet emailed. Set a shipment to
          your return status and type its new waybill on the <Link to="/shipments">Shipments</Link> page to
          add it here. Recipients and subject are set in <Link to="/settings">Settings</Link>.
        </p>

        {error && <p className="error">{error}</p>}
        {message && <p className="success">{message}</p>}

        {!loading && data.count === 0 && <p className="muted">No TEMU returns waiting to be emailed.</p>}

        {data.count > 0 && (
          <>
            <p className="muted small">
              <strong>To:</strong> {data.email_to || '(set recipients in Settings)'}<br />
              <strong>Subject:</strong> {data.email_subject}
            </p>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th className="check-col">
                      <input
                        type="checkbox"
                        aria-label="Select all"
                        checked={allTicked}
                        onChange={() => setSelectedIds(allTicked ? [] : data.results.map((r) => r.id))}
                      />
                    </th>
                    <th>Old waybill</th>
                    <th>New (return) waybill</th>
                    <th>Status</th>
                    <th>Arrived</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((r) => (
                    <tr key={r.id} className={selectedIds.includes(r.id) ? 'selected' : ''}>
                      <td className="check-col">
                        <input
                          type="checkbox"
                          aria-label={`Select ${r.waybill_number}`}
                          checked={selectedIds.includes(r.id)}
                          onChange={() => toggle(r.id)}
                        />
                      </td>
                      <td className="mono">{r.waybill_number}</td>
                      <td className="mono">{r.return_waybill}</td>
                      <td>{r.status_name}</td>
                      <td>{r.arrived}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="actions" style={{ justifyContent: 'flex-start', flexWrap: 'wrap' }}>
              <button onClick={openEmail} disabled={selectedRows.length === 0}>
                Open in Gmail ({selectedRows.length})
              </button>
              <button className="secondary" onClick={copyText} disabled={selectedRows.length === 0}>
                {copied ? 'Copied ✓' : 'Copy email text'}
              </button>
              <button className="secondary" onClick={markEmailed} disabled={selectedRows.length === 0}>
                Mark as emailed
              </button>
            </div>

            <p className="muted small">
              After you've sent the email, click <strong>Mark as emailed</strong> so these don't show up again.
            </p>
          </>
        )}
      </div>
    </>
  )
}