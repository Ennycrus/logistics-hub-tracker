import { useEffect, useState } from 'react'
import { reports } from '../api/client'
import TypeSwitch, { typeLabel, useShipmentType } from '../components/TypeSwitch'

function weekLabel(iso) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

/*
 * Trends for one type (TEMU or Base): delivered vs failed-attempt counts per
 * week over the last couple of months, and the most common failure reasons.
 * All counts come from Django (status history), so nothing is calculated here.
 */
export default function TrendsPage() {
  const [type, setType] = useShipmentType()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    reports.trends(type, 8, 30)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [type])

  const header = (
    <div className="card">
      <div className="title-row">
        <h2>Trends · {typeLabel(type)}</h2>
        <TypeSwitch value={type} onChange={setType} />
      </div>
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}
    </div>
  )
  if (loading || error || !data) return header

  const maxWeek = Math.max(1, ...data.weeks.map((w) => w.delivered + w.unsuccessful))
  const reasons = data.top_reasons
  const maxReason = Math.max(1, ...reasons.reasons.map((r) => r.count))

  return (
    <>
      <div className="card">
        <div className="title-row">
          <h2>Trends · {typeLabel(type)}</h2>
          <TypeSwitch value={type} onChange={setType} />
        </div>
        <p className="muted">
          Delivered and failed-attempt counts per week (Monday to Sunday), last {data.weeks.length} weeks.
          Counted from status history, so they don't depend on finalizing reports.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
          {data.weeks.map((w) => (
            <div key={w.week_start} style={{ display: 'grid', gridTemplateColumns: '70px 1fr 120px', alignItems: 'center', gap: 10 }}>
              <span className="muted small">{weekLabel(w.week_start)}</span>
              <div style={{ display: 'flex', height: 18, background: 'var(--surface-2, #eceff1)', borderRadius: 4, overflow: 'hidden' }}>
                <div title={`Delivered ${w.delivered}`} style={{ width: `${(w.delivered / maxWeek) * 100}%`, background: 'var(--ok, #2e7d32)' }} />
                <div title={`Failed attempts ${w.unsuccessful}`} style={{ width: `${(w.unsuccessful / maxWeek) * 100}%`, background: 'var(--warn, #c62828)' }} />
              </div>
              <span className="small mono">{w.delivered} ✓ / {w.unsuccessful} ✗</span>
            </div>
          ))}
        </div>
        <p className="muted small" style={{ marginTop: 10 }}>
          <span style={{ color: 'var(--ok, #2e7d32)' }}>■</span> Delivered &nbsp;&nbsp;
          <span style={{ color: 'var(--warn, #c62828)' }}>■</span> Failed attempts
        </p>
      </div>

      <div className="card">
        <h3>Top failure reasons · last {reasons.days} days</h3>
        {reasons.total === 0 ? (
          <p className="muted">No failed deliveries recorded in this period.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
            {reasons.reasons.map((r) => (
              <div key={r.name} style={{ display: 'grid', gridTemplateColumns: '1fr 54px', alignItems: 'center', gap: 10 }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>{r.name}</span>
                    <span className="muted small">{Math.round((r.count / reasons.total) * 100)}%</span>
                  </div>
                  <div style={{ height: 8, background: 'var(--surface-2, #eceff1)', borderRadius: 4, marginTop: 3 }}>
                    <div style={{ width: `${(r.count / maxReason) * 100}%`, height: '100%', background: 'var(--accent, #1565c0)', borderRadius: 4 }} />
                  </div>
                </div>
                <span className="mono small" style={{ textAlign: 'right' }}>{r.count}</span>
              </div>
            ))}
          </div>
        )}
        <p className="muted small" style={{ marginTop: 10 }}>
          Counts each failed delivery attempt. A shipment that failed on several days counts once per day.
        </p>
      </div>
    </>
  )
}