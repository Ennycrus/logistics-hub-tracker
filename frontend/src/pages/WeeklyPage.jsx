import { useEffect, useState } from 'react'
import { reports } from '../api/client'
import TypeSwitch, { typeLabel, useShipmentType } from '../components/TypeSwitch'

function today() {
  return new Date().toLocaleDateString('en-CA')
}

function shortDate(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

function percent(value) {
  return value === null ? '—' : `${value}%`
}

/*
 * Weekly delivery for one type (TEMU or Base): the Monday-Saturday week
 * containing the chosen date. Figures come only from FINALIZED daily reports,
 * so they always match what was sent to the company. All maths is in Django.
 */
export default function WeeklyPage() {
  const [date, setDate] = useState(today())
  const [type, setType] = useShipmentType()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let ignore = false
    setLoading(true)
    setError('')
    reports
      .weekly(date, type)
      .then((result) => !ignore && setData(result))
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
  }, [date, type])

  // Move a whole week back or forward.
  function shiftWeek(days) {
    const d = new Date(`${date}T00:00:00`)
    d.setDate(d.getDate() + days)
    const next = d.toLocaleDateString('en-CA')
    setDate(next > today() ? today() : next)
  }

  const t = data?.totals

  return (
    <>
      <div className="card">
        <div className="title-row">
          <h2>Weekly delivery · {typeLabel(type)}</h2>
          <TypeSwitch value={type} onChange={setType} />
        </div>
        <div className="title-row">
          <p className="muted">
            {data ? `Week ${shortDate(data.week_start)} – ${shortDate(data.week_end)} (Monday to Saturday)` : ' '}
          </p>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <button className="secondary small-button" onClick={() => shiftWeek(-7)}>← Previous week</button>
            <label className="inline-date">
              Any day in the week
              <input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} />
            </label>
            <button className="secondary small-button" onClick={() => shiftWeek(7)} disabled={data?.week_end >= today()}>
              Next week →
            </button>
          </div>
        </div>
        {loading && <p className="muted">Loading…</p>}
        {error && <p className="error">{error}</p>}
      </div>

      {data && !loading && (
        <>
          <div className="card">
            <div className="stats">
              <div className="stat"><span className="stat-value">{t.delivered}</span><span className="stat-label">Delivered this week</span></div>
              <div className="stat"><span className="stat-value">{t.available ?? '—'}</span><span className="stat-label">Available this week</span></div>
              <div className="stat"><span className="stat-value">{percent(t.rate)}</span><span className="stat-label">Weekly delivery rate</span></div>
            </div>
            <p className="muted small">
              Available = waiting on Monday ({t.opening_pending ?? '—'}) + new inbound Monday to Saturday ({t.new_inbound}).
              Each shipment is counted once, however many days it waited.
            </p>
            {!data.complete && (
              <p className="warning">
                Incomplete week: {data.missing.length} day(s) not finalized
                ({data.missing.map(shortDate).join(', ')}).
                {t.rate === null && ' Monday is not finalized, so there is no weekly rate yet.'}
              </p>
            )}
          </div>

          <div className="card">
            <h3>Day by day</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Date</th>
                    <th>Total Available</th>
                    <th>Delivered</th>
                    <th>Delivery rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.days.map((d) => (
                    <tr key={d.date} className={d.finalized ? '' : 'replaced'}>
                      <td>{d.weekday}</td>
                      <td>{shortDate(d.date)}</td>
                      {d.finalized ? (
                        <>
                          <td>{d.total_available}</td>
                          <td>{d.delivered}</td>
                          <td>{percent(d.rate)}</td>
                        </>
                      ) : (
                        <td colSpan="3" className="muted">Not finalized</td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="actions">
              <a className="button" href={reports.weeklyDownloadUrl(date, type)}>Download {typeLabel(type)} weekly Excel</a>
            </div>
          </div>
        </>
      )}
    </>
  )
}