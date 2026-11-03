import { useEffect, useState } from 'react'
import { auth, settings } from '../api/client'

// Matches the categories in Django (core/models.py).
const CATEGORIES = [
  { value: 'unchecked', label: 'Not yet checked' },
  { value: 'outstanding', label: 'Outstanding (still at hub)' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'returned', label: 'Returned to hub' },
  { value: 'left_hub', label: 'Left the hub (e.g. rerouted)' },
]

// Which columns each list shows and edits.
const STATUS_FIELDS = [
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'category', label: 'Category', type: 'select', options: CATEGORIES, lockedWhenInUse: true },
  { key: 'requires_reason', label: 'Needs a reason', type: 'checkbox', lockedWhenInUse: true },
  { key: 'sort_order', label: 'Order', type: 'number' },
]

const REASON_FIELDS = [
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'is_other', label: '"Other" (needs a written explanation)', type: 'checkbox' },
  { key: 'sort_order', label: 'Order', type: 'number' },
]

/*
 * Settings: hub name and report options, statuses, failure reasons, and your password.
 * Nothing is deleted: switch a status or reason off instead, so old records stay intact.
 */
export default function SettingsPage() {
  return (
    <>
      <HubSection />
      <OptionList
        title="Statuses"
        help="Used statuses keep their category and 'needs a reason' setting, because past figures depend on them. You can still rename, reorder or switch them off."
        fields={STATUS_FIELDS}
        empty={{ name: '', category: 'outstanding', requires_reason: false, sort_order: 0 }}
        load={settings.statuses}
        create={settings.createStatus}
        update={settings.updateStatus}
      />
      <OptionList
        title="Failure reasons"
        help="Shown when a delivery is unsuccessful."
        fields={REASON_FIELDS}
        empty={{ name: '', is_other: false, sort_order: 0 }}
        load={settings.reasons}
        create={settings.createReason}
        update={settings.updateReason}
      />
      <PasswordSection />
    </>
  )
}

/* Change your login password. Django checks the current one and the password rules. */
function PasswordSection() {
  const blank = { current: '', next: '', confirm: '' }
  const [form, setForm] = useState(blank)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [message, setMessage] = useState('')

  // Typing clears the old messages, so they never describe a password you already changed.
  const set = (field) => (e) => {
    setForm({ ...form, [field]: e.target.value })
    setFieldErrors({})
    setError('')
    setMessage('')
  }
  const mismatch = form.confirm !== '' && form.next !== form.confirm
  const fieldError = (name) => fieldErrors[name]?.join(' ')

  async function save(event) {
    event.preventDefault()
    if (busy || mismatch) return
    setBusy(true)
    setError('')
    setFieldErrors({})
    setMessage('')
    try {
      await auth.changePassword(form.current, form.next)
      setForm(blank)
      setMessage('Password changed. Use the new password next time you log in.')
    } catch (err) {
      setError(err.message)
      setFieldErrors(err.details || {})
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={save}>
      <h2>Change password</h2>
      <p className="muted small">
        At least 8 characters, not too common, not only numbers, and not like your username.
      </p>
      <div className="form-row">
        <label className="grow">
          Current password
          <input type="password" autoComplete="current-password" value={form.current} onChange={set('current')} required />
          {fieldError('current_password') && <span className="field-error">{fieldError('current_password')}</span>}
        </label>
        <label className="grow">
          New password
          <input type="password" autoComplete="new-password" value={form.next} onChange={set('next')} required />
          {fieldError('new_password') && <span className="field-error">{fieldError('new_password')}</span>}
        </label>
        <label className="grow">
          Repeat new password
          <input type="password" autoComplete="new-password" value={form.confirm} onChange={set('confirm')} required />
          {mismatch && <span className="field-error">The two new passwords don't match.</span>}
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}
      <div className="actions">
        <button type="submit" disabled={busy || mismatch || !form.current || !form.next || !form.confirm}>
          {busy ? 'Saving…' : 'Change password'}
        </button>
      </div>
    </form>
  )
}

function HubSection() {
  const [saved, setSaved] = useState(null)
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    settings.hub()
      .then((data) => {
        setSaved(data)
        setForm(data)
      })
      .catch((err) => setError(err.message))
  }, [])

  if (!form) return <div className="card">{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</div>

  const dirty = form.hub_name !== saved.hub_name
    || form.reasons_format !== saved.reasons_format
    || form.tracking_url !== saved.tracking_url

  async function save(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const data = await settings.updateHub({
        hub_name: form.hub_name,
        reasons_format: form.reasons_format,
        tracking_url: form.tracking_url,
      })
      setSaved(data)
      setForm(data)
      setMessage('Saved. New reports will use these settings.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={save}>
      <h2>Settings</h2>
      <h3>Hub</h3>
      <div className="form-row">
        <label className="grow">
          Hub name (the HUBS column)
          <input value={form.hub_name} onChange={(e) => setForm({ ...form, hub_name: e.target.value })} required />
        </label>
        <label className="grow">
          Reasons column
          <select value={form.reasons_format} onChange={(e) => setForm({ ...form, reasons_format: e.target.value })}>
            <option value="grouped">Automatic summary (e.g. Customer unavailable - 6)</option>
            <option value="text">I write it myself on each report</option>
          </select>
        </label>
      </div>
      <p className="muted small">Finalized reports keep the hub name they were finalized with.</p>
      <label>
        Tracking page address (for the Track buttons)
        <input
          value={form.tracking_url}
          onChange={(e) => setForm({ ...form, tracking_url: e.target.value })}
          placeholder="https://.../track?waybill={waybill}"
        />
      </label>
      <p className="muted small">
        Open one waybill's result on the company tracking page, copy the address, and replace the
        waybill number with <code>{'{waybill}'}</code>. Leave empty to hide the Track buttons.
      </p>
      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}
      <div className="actions">
        <button type="submit" disabled={!dirty || busy}>{busy ? 'Saving…' : 'Save'}</button>
      </div>
    </form>
  )
}

/* A list of statuses or reasons: edit a row, switch it on/off, or add a new one. */
function OptionList({ title, help, fields, empty, load, create, update }) {
  const [items, setItems] = useState([])
  const [editingId, setEditingId] = useState(null)
  const [draft, setDraft] = useState(null)   // the row being edited, or the new row
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function reload() {
    return load().then(setItems).catch((err) => setError(err.message))
  }
  useEffect(() => {
    reload()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function run(action) {
    if (busy) return false
    setBusy(true)
    setError('')
    try {
      await action()
      await reload()
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setBusy(false)
    }
  }

  function startEdit(item) {
    setEditingId(item.id)
    setDraft({ ...item })
  }

  async function saveEdit() {
    const changes = {}
    for (const f of fields) {
      if (f.lockedWhenInUse && draft.in_use) continue // don't send what can't change
      changes[f.key] = f.type === 'number' ? Number(draft[f.key]) : draft[f.key]
    }
    if (await run(() => update(draft.id, changes))) cancel()
  }

  function cancel() {
    setEditingId(null)
    setDraft(null)
  }

  async function addNew(event) {
    event.preventDefault()
    const item = { ...draft }
    for (const f of fields) if (f.type === 'number') item[f.key] = Number(item[f.key])
    if (await run(() => create(item))) cancel()
  }

  function input(field, value, onChange, locked) {
    if (field.type === 'checkbox') {
      return <input type="checkbox" className="check" checked={value} disabled={locked} onChange={(e) => onChange(e.target.checked)} />
    }
    if (field.type === 'select') {
      return (
        <select value={value} disabled={locked} onChange={(e) => onChange(e.target.value)}>
          {field.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      )
    }
    return (
      <input
        type={field.type}
        min={field.type === 'number' ? 0 : undefined}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={field.key === 'name'}
      />
    )
  }

  function show(field, value) {
    if (field.type === 'checkbox') return value ? 'Yes' : '—'
    if (field.type === 'select') return field.options.find((o) => o.value === value)?.label ?? value
    return value
  }

  const adding = draft && editingId === null

  return (
    <div className="card">
      <h3>{title}</h3>
      <p className="muted small">{help}</p>
      {error && <p className="error">{error}</p>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {fields.map((f) => <th key={f.key}>{f.label}</th>)}
              <th>Active</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) =>
              editingId === item.id ? (
                <tr key={item.id} className="editing">
                  {fields.map((f) => (
                    <td key={f.key}>
                      {input(f, draft[f.key], (v) => setDraft({ ...draft, [f.key]: v }), f.lockedWhenInUse && item.in_use)}
                    </td>
                  ))}
                  <td>{item.is_active ? 'Yes' : 'No'}</td>
                  <td className="row-actions">
                    <button className="small-button" onClick={saveEdit} disabled={busy}>Save</button>
                    <button className="secondary small-button" onClick={cancel} disabled={busy}>Cancel</button>
                  </td>
                </tr>
              ) : (
                <tr key={item.id} className={item.is_active ? '' : 'replaced'}>
                  {fields.map((f) => <td key={f.key}>{show(f, item[f.key])}</td>)}
                  <td>
                    <span className={`badge ${item.is_active ? 'badge-delivered' : 'badge-unchecked'}`}>
                      {item.is_active ? 'On' : 'Off'}
                    </span>
                    {item.in_use && <div className="small muted">in use</div>}
                  </td>
                  <td className="row-actions">
                    <button className="secondary small-button" onClick={() => startEdit(item)} disabled={busy || draft !== null}>
                      Edit
                    </button>
                    <button
                      className="secondary small-button"
                      disabled={busy}
                      onClick={() => run(() => update(item.id, { is_active: !item.is_active }))}
                    >
                      {item.is_active ? 'Switch off' : 'Switch on'}
                    </button>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>

      {adding ? (
        <form className="add-form" onSubmit={addNew}>
          <div className="form-row">
            {fields.map((f) => (
              <label key={f.key} className={f.type === 'text' ? 'grow' : ''}>
                {f.label}
                {input(f, draft[f.key], (v) => setDraft({ ...draft, [f.key]: v }), false)}
              </label>
            ))}
          </div>
          <div className="actions">
            <button type="button" className="secondary" onClick={cancel} disabled={busy}>Cancel</button>
            <button type="submit" disabled={busy}>Add</button>
          </div>
        </form>
      ) : (
        <div className="actions">
          <button className="secondary" onClick={() => setDraft({ ...empty })} disabled={busy || draft !== null}>
            + Add
          </button>
        </div>
      )}
    </div>
  )
}
