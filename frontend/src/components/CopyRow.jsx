import { useState } from 'react'

/*
 * Copies a finalized report row so it can be pasted straight into the
 * company's Google Sheet.
 *
 * The values are joined with TAB characters. When you paste tab-separated
 * text into Google Sheets (or Excel), each value lands in its own cell,
 * left to right.
 *
 * Two choices:
 *   - Figures only (Inbound -> Reasons): click the Inbound cell (column B)
 *     of your hub's row, then paste. Your hub name in column A stays as it is.
 *   - Whole row (HUBS -> Reasons): click column A, then paste.
 */

// Tabs or line breaks inside a value would push the rest into the wrong cells.
function clean(value) {
  if (value === null || value === undefined) return ''
  return String(value).replace(/[\t\r\n]+/g, ' ').trim()
}

// Clipboard helper with a fallback for browsers that block the modern API.
async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const area = document.createElement('textarea')
  area.value = text
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(area)
  if (!ok) throw new Error('copy failed')
}

export default function CopyRow({ values }) {
  const [copied, setCopied] = useState('')
  const [error, setError] = useState('')

  const figures = [
    values.inbound, values.old_pending, values.total_available, values.delivered,
    values.current_day, values.return, values.vans, values.bikes, values.third_party,
    values.reasons_text,
  ].map(clean)

  async function copy(which) {
    setError('')
    const cells = which === 'row' ? [clean(values.hub_name), ...figures] : figures
    try {
      await copyText(cells.join('\t'))
      setCopied(which)
      setTimeout(() => setCopied(''), 4000)
    } catch {
      setError('Your browser blocked copying. Select the row above and press Ctrl + C instead.')
    }
  }

  return (
    <div className="copy-row">
      <div className="copy-buttons">
        <button type="button" className="secondary" onClick={() => copy('figures')}>
          {copied === 'figures' ? 'Copied ✓' : 'Copy figures (Inbound → Reasons)'}
        </button>
        <button type="button" className="secondary" onClick={() => copy('row')}>
          {copied === 'row' ? 'Copied ✓' : 'Copy whole row'}
        </button>
      </div>
      <p className="muted small">
        {copied === 'row'
          ? 'Now click the HUBS cell (column A) of your row in the Google Sheet and press Ctrl + V.'
          : 'Then click the Inbound cell (column B) of your hub’s row in the Google Sheet and press Ctrl + V.'}
      </p>
      {error && <p className="error">{error}</p>}
    </div>
  )
}