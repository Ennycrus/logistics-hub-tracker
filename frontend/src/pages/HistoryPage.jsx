import { Fragment, useEffect, useState } from 'react'
import { reports } from '../api/client'
import { TYPES, typeLabel } from '../components/TypeSwitch'

const PAGE_SIZE = 50 // must match PAGE_SIZE in Django's settings.py

/*
 * Every finalized report, newest date first. Show both types, or only TEMU or Base.
 * Corrected reports keep all their versions; the newest one is marked "Current".
 * Click a row's "Details" to see reasons, warnings and notes; "Download" gets the Excel file.
 */
export default function HistoryPage() {
  const [page, setPage] = useState(1)
  const [type, setType] = useState('') // '' = both types
  const [data, setData] = useState({ count: 0, results: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [openId, setOpenId] = useState(null) // the row whose details are showing

  useEffect(() => {
    let ignore = false
    setLoading(true)
    setError('')
    reports
      .history({ page, type })
      .then((result) => !ignore && setData(result))
      .catch((err) => !ignore && setError(err.message))
      .finally(() => !ignore && setLoading(false))
    return () => {
      ignore = true
    }
  }, [page, type])

  // The highest version seen for each date AND type on this page is the current one.
  const latestVersion = {}
  for (const r of data.results) {
    const key = `${r.date}-${r.shipment_type}`
    latestVersion[key] = Math.max(latestVersion[key] ?? 0, r.version)
  }

  const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE))

  return (
    <div className="card">
      <div className="title-row">
        <h2>Report history</h2>
        <div className="tabs" role="group" aria-label="Report type">
          {[{ value: '', label: 'All' }, ...TYPES].map((t) => (
            <button
              key={t.value}
              type="button"
              className={`tab ${type === t.value ? 'active' : ''}`}
              aria-pressed={type === t.value}
              onClick={() => {
                setType(t.value)
                setPage(1)
                setOpenId(null)
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      <p className="muted">{loading ? 'Loading…' : `${data.count} finalized report(s)`}</p>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Type</th>
              <th>Hub</th>
              <th>Inbound</th>
              <th>Old Pending</th>
              <th>Total Available</th>
              <th>Delivered</th>
              <th>Current Day</th>
              <th>Return</th>
              <th>Vans / Bike / 3PL</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((r) => {
              const current = r.version === latestVersion[`${r.date}-${r.shipment_type}`]
              const f = r.figures
              return (
                <Fragment key={r.id}>
                  <tr className={current ? '' : 'replaced'}>
                    <td>{r.date}</td>
                    <td><strong>{typeLabel(r.shipment_type)}</strong></td>
                    <td>{r.hub_name}</td>
                    <td>{f.inbound}</td>
                    <td>{f.old_pending}</td>
                    <td>{f.total_available}</td>
                    <td>{f.delivered}</td>
                    <td>{f.current_day}</td>
                    <td>{f.return}</td>
                    <td>{r.vans} / {r.bikes} / {r.third_party}</td>
                    <td>
                      <span className={`badge ${current ? 'badge-delivered' : 'badge-unchecked'}`}>
                        {current ? 'Current' : 'Replaced'}
                      </span>
                      <div className="small muted">v{r.version}</div>
                    </td>
                    <td className="row-actions">
                      <button
                        className="secondary small-button"
                        onClick={() => setOpenId(openId === r.id ? null : r.id)}
                      >
                        {openId === r.id ? 'Hide' : 'Details'}
                      </button>
                      <a className="button small-button" href={reports.downloadUrl(r.date, r.version, r.shipment_type)}>
                        Download
                      </a>
                    </td>
                  </tr>
                  {openId === r.id && (
                    <tr className="details-row">
                      <td colSpan="12">
                        <Details report={r} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
            {!loading && data.results.length === 0 && (
              <tr><td colSpan="12" className="muted">No finalized reports yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pager">
        <button className="secondary" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}>← Previous</button>
        <span className="muted">Page {page} of {totalPages}</span>
        <button className="secondary" disabled={page >= totalPages || loading} onClick={() => setPage(page + 1)}>Next →</button>
      </div>
    </div>
  )
}

function Details({ report }) {
  const adjusted = Object.entries(report.adjustments)
  return (
    <div className="details">
      <p><strong>Finalized:</strong> {new Date(report.finalized_at).toLocaleString()}</p>
      {report.corrects_version && (
        <p><strong>Corrects version {report.corrects_version}:</strong> {report.correction_reason}</p>
      )}
      <p><strong>Reasons:</strong> {report.reasons_text || '—'}</p>
      <p>
        <strong>Also recorded:</strong> {report.figures.unsuccessful} unsuccessful,{' '}
        {report.figures.unchecked} not yet checked, {report.figures.rerouted} rerouted
      </p>
      {adjusted.length > 0 && (
        <p>
          <strong>Manual adjustments:</strong>{' '}
          {adjusted.map(([key, c]) => `${key} ${report.calculated[key]} → ${c.value} (${c.note})`).join('; ')}
        </p>
      )}
      {report.warnings.length > 0 && (
        <div>
          <strong>Warnings accepted:</strong>
          <ul>{report.warnings.map((w) => <li key={w.message}>{w.message}</li>)}</ul>
        </div>
      )}
      {report.notes && <p><strong>Notes:</strong> {report.notes}</p>}
    </div>
  )
}