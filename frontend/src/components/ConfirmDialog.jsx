import { useEffect, useRef } from 'react'

/*
 * A styled "Are you sure?" box, used instead of the browser's plain popup.
 *
 *   <ConfirmDialog
 *     title="Import mixed.xlsx?"
 *     message="For 30 Oct 2026."
 *     items={[{ label: 'New TEMU', value: 2 }, { label: 'Skipped', value: 1, muted: true }]}
 *     confirmLabel="Import"
 *     onConfirm={...}
 *     onCancel={...}
 *   />
 *
 * Esc or clicking outside the box cancels. Enter confirms.
 */
export default function ConfirmDialog({
  title, message, items = [], note, confirmLabel = 'Confirm', busy = false, onConfirm, onCancel,
}) {
  const confirmButton = useRef(null)

  useEffect(() => {
    confirmButton.current?.focus()
    const onKey = (e) => e.key === 'Escape' && !busy && onCancel()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onCancel])

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && !busy && onCancel()}>
      <div className="card dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <h2 id="confirm-title">{title}</h2>
        {message && <p className="muted">{message}</p>}

        {items.length > 0 && (
          <table style={{ margin: '12px 0' }}>
            <tbody>
              {items.map((item) => (
                <tr key={item.label}>
                  <td className={item.muted ? 'muted' : ''}>{item.label}</td>
                  <td style={{ textAlign: 'right', fontWeight: 700 }} className={item.muted ? 'muted' : ''}>
                    {item.value}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {note && <p className="notice">{note}</p>}

        <div className="dialog-actions">
          <button type="button" className="secondary" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="button" ref={confirmButton} onClick={onConfirm} disabled={busy}>
            {busy ? 'Please wait…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}