import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { reports } from '../api/client'
import ConfirmDialog from '../components/ConfirmDialog'

function today() {
  return new Date().toLocaleDateString('en-CA')
}

function shortDate(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

function savedTime(value) {
  return new Date(value).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function dayName(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
}

// Litres for display ('—' when nobody entered any).
function litres(value) {
  return value === null || value === undefined ? '—' : `${value} L`
}

/*
 * The Saturday report for the manager (TEMU and Base together):
 *   1-4 are counted from the shipments; 5 (fuel) and 6 (incidents) are added
 *   up from the daily entries on the Daily Report page.
 * Save freezes everything as it is now, so a saved report never changes.
 * Saving again adds a new version; earlier versions are kept and can be opened.
 * "Copy report" puts the text on the clipboard for WhatsApp or email.
 */
export default function HubReportPage() {
  const [date, setDate] = useState(today())
  const [version, setVersion] = useState(null) // null = the latest saved version
  const [data, setData] = useState(null)
  const [history, setHistory] = useState([])
  const [extraNotes, setExtraNotes] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [message, setMessage] = useState('')
  const [confirming, setConfirming] = useState(false) // "Save anyway?" box is open

  function show(result) {
    setData(result)
    setExtraNotes(result.extra_notes)
  }

  useEffect(() => {
    let ignore = false
    setLoading(true)
    setError('')
    setMessage('')
    setFieldErrors({})
    reports
      .weeklyHub(date, version)
      .then((result) => !ignore && show(result))
      .catch((err) => {
        if (!ignore) {
          setData(null)
          setError(err.message)
        }
      })
      .finally(() => !ignore && setLoading(false))
    return () => {
      ignore = true
    }
  }, [date, version])

  function loadHistory() {
    reports.weeklyHubHistory().then(setHistory).catch(() => {})
  }
  useEffect(loadHistory, [])

  function shiftWeek(days) {
    const d = new Date(`${date}T00:00:00`)
    d.setDate(d.getDate() + days)
    const next = d.toLocaleDateString('en-CA')
    setVersion(null)
    setDate(next > today() ? today() : next)
  }

  function openVersion(weekStart, number) {
    setDate(weekStart)
    setVersion(number)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const dirty = data !== null && extraNotes !== data.extra_notes

  // Things to fix before sending (shown again in the "Save anyway?" box).
  function problems() {
    const live = data.live_figures
    const list = []
    if (live.fuel.missing_days.length) list.push(`No fuel entered for ${live.fuel.missing_days.map(dayName).join(', ')}`)
    if (live.delivered.not_recorded) list.push(`${live.delivered.not_recorded} delivered shipment(s) with nobody recorded`)
    if (!live.daily_reports.matches) list.push(`Delivered (${live.delivered.total}) differs from your daily reports (${live.daily_reports.delivered})`)
    if (live.daily_reports.missing_reports) list.push(`${live.daily_reports.missing_reports} daily report(s) not finalized yet`)
    if (live.stale.count) list.push(`${live.stale.count} shipment(s) stuck with no update for ${live.stale.days}+ days`)
    return list
  }

  function askToSave(event) {
    event.preventDefault()
    if (saving) return
    if (problems().length) setConfirming(true)
    else save()
  }

  async function save() {
    setConfirming(false)
    if (saving) return
    setSaving(true)
    setError('')
    setFieldErrors({})
    setMessage('')
    try {
      const result = await reports.saveWeeklyHub(date, { extra_notes: extraNotes })
      setVersion(null)
      show(result)
      loadHistory()
      setMessage(`Saved as version ${result.version}. The figures are now frozen as they are right now.`)
    } catch (err) {
      setError(err.message)
      setFieldErrors(err.details || {})
    } finally {
      setSaving(false)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(data.text)
      setMessage('Report copied. Paste it into WhatsApp or your email.')
    } catch {
      setError('Could not copy. Select the text below and copy it yourself.')
    }
  }

  const fieldError = (name) => fieldErrors[name]?.[0]
  const f = data?.figures
  const live = data?.live_figures
  const viewingOld = data?.saved && data.version < data.versions
  const changedSinceSave =
    data?.saved && !viewingOld && JSON.stringify(data.figures) !== JSON.stringify(data.live_figures)
  const check = f?.daily_reports
  const missingFuel = f?.fuel.missing_days ?? []
  const stale = f?.stale

  return (
    <>
      <div className="card">
        <div className="title-row">
          <h2>Saturday report</h2>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <button className="secondary small-button" onClick={() => shiftWeek(-7)}>← Previous week</button>
            <label className="inline-date">
              Any day in the week
              <input type="date" value={date} max={today()} onChange={(e) => { setVersion(null); setDate(e.target.value) }} />
            </label>
            <button className="secondary small-button" onClick={() => shiftWeek(7)} disabled={data?.week_end >= today()}>
              Next week →
            </button>
          </div>
        </div>
        <p className="muted">
          {data ? `Week ${shortDate(data.week_start)} – ${shortDate(data.week_end)} (Monday to Saturday) · ` : ''}
          {data?.saved
            ? `Version ${data.version} of ${data.versions}, saved ${savedTime(data.saved_at)}`
            : 'Not saved yet: figures are live'}
        </p>
        {viewingOld && (
          <p className="notice">
            You are looking at an older version.{' '}
            <button type="button" className="secondary small-button" onClick={() => setVersion(null)}>Show the latest</button>
          </p>
        )}
        {loading && <p className="muted">Loading…</p>}
        {error && <p className="error">{error}</p>}
        {message && <p className="success">{message}</p>}
      </div>

      {data && !loading && (
        <>
          <div className="card">
            <h3>Counted by the app</h3>
            <div className="stats">
              <div className="stat"><span className="stat-value">{f.temu_pending}</span><span className="stat-label">1. TEMU pending in hub</span></div>
              <div className="stat"><span className="stat-value">{f.base_pending}</span><span className="stat-label">2. Base pending in hub</span></div>
              <div className="stat"><span className="stat-value">{f.delivered.total}</span><span className="stat-label">3. Delivered this week</span></div>
              <div className="stat"><span className="stat-value">{f.not_in_hub}</span><span className="stat-label">4. Not in hub (awaiting update)</span></div>
            </div>
            <p className="muted small">
              Delivered: Riders {f.delivered.riders} · Captains {f.delivered.captains} · 3PLs {f.delivered.third_party}
              {f.delivered.not_recorded > 0 && ` · not recorded ${f.delivered.not_recorded}`}
            </p>
            {check && !check.matches && (
              <p className="warning">
                Check before sending: delivered here is {f.delivered.total}, but your finalized daily reports
                (TEMU + Base) add up to {check.delivered}. A daily report may have been adjusted, or a delivery
                recorded after its day was finalized.
              </p>
            )}
            {check && check.missing_reports > 0 && (
              <p className="muted small">{check.missing_reports} daily report(s) this week (TEMU + Base) are not finalized yet.</p>
            )}
            {f.delivered.not_recorded > 0 && (
              <p className="warning">
                {f.delivered.not_recorded} delivered shipment(s) have no Rider, Captain or 3PL recorded.{' '}
                <Link to="/shipments?filter=delivered_none">Show them</Link>, then click Update on each and choose who delivered it.
              </p>
            )}
            {stale?.count > 0 && (
              <p className="warning">
                {stale.count} shipment(s) have had no status update for {stale.days} days or more, so they may
                be making items 1, 2 and 4 too high.{' '}
                <Link to="/shipments?filter=stale">Show them</Link> and record what happened to them.
              </p>
            )}
            {changedSinceSave && (
              <p className="notice">
                Something changed after you saved (now: TEMU {live.temu_pending}, Base {live.base_pending},
                delivered {live.delivered.total}, not in hub {live.not_in_hub}). Save again to use the new figures.
              </p>
            )}
            <p className="muted small">
              Pending = not delivered yet (Not Yet Checked, Pending/Unsuccessful and Returned).
              Not in hub = out with riders, no result yet; these are already included in pending.
            </p>
          </div>

          <div className="card">
            <h3>Fuel and incidents this week</h3>
            <div className="stats">
              <div className="stat"><span className="stat-value">{litres(f.fuel.riders)}</span><span className="stat-label">5. Fuel: riders</span></div>
              <div className="stat"><span className="stat-value">{litres(f.fuel.captains)}</span><span className="stat-label">Fuel: captains</span></div>
              <div className="stat"><span className="stat-value">{f.incidents.length}</span><span className="stat-label">6. Days with incidents</span></div>
            </div>
            {missingFuel.length > 0 && (
              <p className="warning">
                No fuel entered for {missingFuel.map(dayName).join(', ')}. Open that date on the Daily Report page
                and fill it in{data.saved && !viewingOld ? ', then save again' : ''}.
              </p>
            )}
            <p className="muted small">
              Typed in each day on the Daily Report page. Anything entered on a Sunday counts in the next week's report.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Riders (L)</th>
                    <th>Captains (L)</th>
                    <th>Incidents</th>
                  </tr>
                </thead>
                <tbody>
                  {data.days.map((d) => (
                    <tr key={d.date}>
                      <td>{d.weekday} {shortDate(d.date)}</td>
                      <td>{d.fuel_riders_litres ?? '—'}</td>
                      <td>{d.fuel_captains_litres ?? '—'}</td>
                      <td style={{ whiteSpace: 'pre-wrap' }}>{d.incidents || <span className="muted">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <form className="card" onSubmit={askToSave}>
            <h3>Anything else to add?</h3>
            <label>
              Extra notes for item 6 (optional)
              <textarea rows="3" value={extraNotes} onChange={(e) => setExtraNotes(e.target.value)}
                placeholder="e.g. We need one more rider for the Monday route" />
              {fieldError('extra_notes') && <span className="field-error">{fieldError('extra_notes')}</span>}
            </label>
            <div className="actions">
              {data.saved && <span className="muted small">Saving again adds version {data.versions + 1}; earlier versions are kept.</span>}
              <button type="submit" disabled={saving}>
                {saving ? 'Saving…' : data.saved ? 'Save again' : 'Save report'}
              </button>
            </div>
          </form>

          <div className="card">
            <h3>Report to send</h3>
            {dirty && <p className="warning">You have unsaved changes. Save first so the text below includes them.</p>}
            <pre style={{ whiteSpace: 'pre-wrap', background: 'var(--bg)', padding: 12, borderRadius: 6, fontFamily: 'inherit' }}>
              {data.text}
            </pre>
            <div className="actions">
              <button type="button" onClick={copy} disabled={dirty}>Copy report</button>
              <a className="button" href={reports.weeklyHubDownloadUrl(date, data.version ?? undefined)}>Download Excel</a>
            </div>
          </div>
        </>
      )}

      {confirming && (
        <ConfirmDialog
          title="Save with these warnings?"
          message="These are not fixed yet. The report will be saved (and frozen) as it is."
          items={problems().map((p, i) => ({ label: `${i + 1}`, value: p }))}
          note="You can fix them and save again later; every version is kept."
          confirmLabel="Save anyway"
          busy={saving}
          onConfirm={save}
          onCancel={() => setConfirming(false)}
        />
      )}

      <div className="card">
        <h3>Saved Saturday reports</h3>
        {history.length === 0 ? (
          <p className="muted">None saved yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Week</th>
                  <th>Version</th>
                  <th>TEMU pending</th>
                  <th>Base pending</th>
                  <th>Delivered</th>
                  <th>Saved</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {history.map((r) => (
                  <tr key={`${r.week_start}-${r.version}`}>
                    <td>{shortDate(r.week_start)} – {shortDate(r.week_end)}</td>
                    <td>{r.version}</td>
                    <td>{r.temu_pending}</td>
                    <td>{r.base_pending}</td>
                    <td>{r.delivered}</td>
                    <td>{savedTime(r.saved_at)}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button className="secondary small-button" onClick={() => openVersion(r.week_start, r.version)}>Open</button>{' '}
                      <a className="button small-button" href={reports.weeklyHubDownloadUrl(r.week_start, r.version)}>Excel</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}