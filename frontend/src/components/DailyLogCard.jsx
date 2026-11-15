import { useEffect, useState } from 'react'
import { reports } from '../api/client'

// Number from the server -> text for an input ('' when not entered).
function asInput(value) {
  return value === null || value === undefined ? '' : String(value)
}

function savedTime(value) {
  return new Date(value).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function shown(value) {
  return value === null || value === undefined ? '—' : `${value} L`
}

/*
 * Today's fuel and incidents, for the Saturday report.
 * One log per day for the whole hub (TEMU and Base together), so it shows
 * the same on both report types. The Saturday report adds the week up.
 * Every save that changes something is kept, so "Show changes" lists them.
 */
export default function DailyLogCard({ date }) {
  const [saved, setSaved] = useState(null) // what the server has
  const [riders, setRiders] = useState('')
  const [captains, setCaptains] = useState('')
  const [incidents, setIncidents] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [message, setMessage] = useState('')
  const [showChanges, setShowChanges] = useState(false)

  function show(log) {
    setSaved(log)
    setRiders(asInput(log.fuel_riders_litres))
    setCaptains(asInput(log.fuel_captains_litres))
    setIncidents(log.incidents)
  }

  useEffect(() => {
    let ignore = false
    reports
      .dailyLog(date)
      .then((log) => !ignore && show(log))
      .catch((err) => !ignore && setError(err.message))
    return () => {
      ignore = true
    }
  }, [date])

  const dirty =
    saved !== null &&
    (riders !== asInput(saved.fuel_riders_litres) ||
      captains !== asInput(saved.fuel_captains_litres) ||
      incidents !== saved.incidents)

  async function save(event) {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setError('')
    setFieldErrors({})
    setMessage('')
    try {
      const log = await reports.saveDailyLog(date, {
        fuel_riders_litres: riders === '' ? null : riders,
        fuel_captains_litres: captains === '' ? null : captains,
        incidents,
      })
      show(log)
      setMessage('Saved. It will be added to this week’s Saturday report.')
    } catch (err) {
      setError(err.message)
      setFieldErrors(err.details || {})
    } finally {
      setSaving(false)
    }
  }

  const fieldError = (name) => fieldErrors[name]?.[0]

  if (saved === null) return error ? <div className="card"><p className="error">{error}</p></div> : null

  return (
    <form className="card" onSubmit={save}>
      <h3>Today’s fuel and incidents (for the Saturday report)</h3>
      <p className="muted small">One entry per day for the whole hub, TEMU and Base together.</p>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <label style={{ flex: 1, minWidth: 180 }}>
          Fuel used by riders (litres)
          <input type="number" min="0" step="0.01" value={riders}
            onChange={(e) => { setRiders(e.target.value); setMessage('') }} />
          {fieldError('fuel_riders_litres') && <span className="field-error">{fieldError('fuel_riders_litres')}</span>}
        </label>
        <label style={{ flex: 1, minWidth: 180 }}>
          Fuel used by captains (litres)
          <input type="number" min="0" step="0.01" value={captains}
            onChange={(e) => { setCaptains(e.target.value); setMessage('') }} />
          {fieldError('fuel_captains_litres') && <span className="field-error">{fieldError('fuel_captains_litres')}</span>}
        </label>
      </div>
      <label>
        Incidents / escalations / challenges / difficulties
        <textarea rows="3" value={incidents} placeholder="Leave empty if nothing happened"
          onChange={(e) => { setIncidents(e.target.value); setMessage('') }} />
        {fieldError('incidents') && <span className="field-error">{fieldError('incidents')}</span>}
      </label>
      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}
      {saved.changes.length > 0 && (
        <p className="muted small">
          Last saved {savedTime(saved.changes[0].saved_at)}
          {saved.changes.length > 1 && (
            <>
              {` · changed ${saved.changes.length - 1} time(s) after the first save `}
              <button type="button" className="link-button" onClick={() => setShowChanges(!showChanges)}>
                {showChanges ? 'Hide changes' : 'Show changes'}
              </button>
            </>
          )}
        </p>
      )}
      {showChanges && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Saved</th>
                <th>Riders</th>
                <th>Captains</th>
                <th>Incidents</th>
              </tr>
            </thead>
            <tbody>
              {saved.changes.map((c) => (
                <tr key={c.saved_at}>
                  <td className="small">{savedTime(c.saved_at)}</td>
                  <td>{shown(c.fuel_riders_litres)}</td>
                  <td>{shown(c.fuel_captains_litres)}</td>
                  <td style={{ whiteSpace: 'pre-wrap' }}>{c.incidents || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="actions">
        <button type="submit" disabled={saving || !dirty}>{saving ? 'Saving…' : 'Save fuel and incidents'}</button>
      </div>
    </form>
  )
}