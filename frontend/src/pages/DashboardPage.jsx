import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { imports, reports } from '../api/client'
import TypeSwitch, { typeLabel, useShipmentType } from '../components/TypeSwitch'

function today() {
  return new Date().toLocaleDateString('en-CA')
}

/*
 * Today at a glance for one type (TEMU or Base): the day's figures, this week's
 * delivery rate, what still needs attention, and quick links to the pages you use every day.
 * All figures come from Django; nothing is calculated here.
 */
export default function DashboardPage() {
  const date = today()
  const [type, setType] = useShipmentType()
  const [report, setReport] = useState(null)
  const [lastImport, setLastImport] = useState(null)
  const [week, setWeek] = useState(null) // this Monday-Saturday week, from finalized reports
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    Promise.all([reports.get(date, type), imports.list(), reports.weekly(date, type)])
      .then(([r, i, w]) => {
        setReport(r)
        setLastImport(i.results[0] ?? null)
        setWeek(w)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [date, type])

  // The switch stays visible while loading, so you can always change type.
  const header = (
    <div className="card">
      <div className="title-row">
        <h2>Today · {typeLabel(type)}</h2>
        <TypeSwitch value={type} onChange={setType} />
      </div>
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}
    </div>
  )
  if (loading || error || !report) return header

  const finalized = report.state === 'finalized'
  // A finalized day shows its frozen figures; an open day shows live ones.
  const f = finalized ? report.report.figures : report.preview.figures
  const warnings = finalized ? [] : report.preview.warnings
  const importedToday = lastImport?.reporting_date === date

  const cards = [
    { label: 'New inbound', value: f.inbound },
    { label: 'Old pending', value: f.old_pending },
    { label: 'Total available', value: f.total_available },
    { label: 'Delivered', value: f.delivered },
    { label: 'Unsuccessful', value: f.unsuccessful },
    { label: 'Returned to hub', value: f.return },
    { label: 'Remaining (Current Day)', value: f.current_day },
    { label: 'Not yet checked', value: f.unchecked },
  ]

  return (
    <>
      <div className="card">
        <div className="title-row">
          <div>
            <h2>Today · {typeLabel(type)}</h2>
            <TypeSwitch value={type} onChange={setType} />
            <p className="muted">
              {new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            </p>
          </div>
          <span className={`badge ${finalized ? 'badge-delivered' : 'badge-outstanding'}`}>
            {finalized
              ? `${typeLabel(type)} report finalized (v${report.report.version})`
              : `${typeLabel(type)} report not finalized yet`}
          </span>
        </div>

        <div className="stats">
          {cards.map((c) => (
            <div key={c.label} className="stat">
              <span className="stat-value">{c.value}</span>
              <span className="stat-label">{c.label}</span>
            </div>
          ))}
        </div>
        {!finalized && f.unchecked > 0 && (
          <p className="muted small">
            "Not yet checked" shipments are counted in Remaining until you record their status.
          </p>
        )}
      </div>

      <div className="card">
        <div className="title-row">
          <h3>This week (Monday to Saturday)</h3>
          <Link to="/weekly">Open Weekly →</Link>
        </div>
        <div className="stats">
          <div className="stat">
            <span className="stat-value">{week.totals.rate === null ? '—' : `${week.totals.rate}%`}</span>
            <span className="stat-label">Weekly delivery rate</span>
          </div>
          <div className="stat">
            <span className="stat-value">{week.totals.delivered}</span>
            <span className="stat-label">Delivered so far</span>
          </div>
          <div className="stat">
            <span className="stat-value">{6 - week.missing.length} / 6</span>
            <span className="stat-label">Days finalized</span>
          </div>
        </div>
        <p className="muted small">
          {week.totals.rate === null
            ? "The weekly rate appears once Monday's report is finalized."
            : 'From finalized reports only, so today counts after you finalize it.'}
        </p>
      </div>

      <div className="card">
        <h3>Needs attention</h3>
        <ul className="plain-list">
          {!importedToday && (
            <li>📥 No scanner file imported for today yet. <Link to="/import">Import one →</Link></li>
          )}
          {!finalized && f.unchecked > 0 && (
            <li>🔍 {f.unchecked} shipment(s) still need checking on the company website. <Link to="/shipments">Update statuses →</Link></li>
          )}
          {warnings
            .filter((w) => w.code !== 'unchecked')
            .map((w) => <li key={w.message}>⚠️ {w.message}</li>)}
          {!finalized && (
            <li>📝 Today's {typeLabel(type)} report is still a draft. <Link to="/report">Open the daily report →</Link></li>
          )}
          {finalized && importedToday && <li>✅ Today's {typeLabel(type)} report is finalized.</li>}
        </ul>
      </div>

      <div className="card">
        <h3>Quick actions</h3>
        <div className="quick-actions">
          <Link className="button" to="/import">Import scanner file</Link>
          <Link className="button" to="/shipments">Update statuses</Link>
          <Link className="button" to="/report">Daily report</Link>
          <Link className="button secondary-link" to="/history">Report history</Link>
        </div>
        {lastImport && (
          <p className="muted small">
            Last import: {lastImport.file_name} for {lastImport.reporting_date} ({lastImport.new_count} new:{' '}
            {lastImport.temu_new_count} TEMU, {lastImport.base_new_count} Base).
          </p>
        )}
      </div>
    </>
  )
}