import { useState } from 'react'

/*
 * Base / TEMU switch, shared by every page that shows one report type.
 *
 * useShipmentType() remembers your last choice in this browser, so if you
 * switch to Base on the Report page, Pending and the Dashboard open on Base too.
 */

export const TYPES = [
  { value: 'temu', label: 'TEMU' },
  { value: 'base', label: 'Base' },
]

const STORAGE_KEY = 'hub-tracker-type'

function readSaved() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return TYPES.some((t) => t.value === saved) ? saved : 'temu'
  } catch {
    return 'temu' // storage can be blocked (private window): just use TEMU
  }
}

export function useShipmentType() {
  const [type, setType] = useState(readSaved)

  function choose(value) {
    setType(value)
    try {
      localStorage.setItem(STORAGE_KEY, value)
    } catch {
      // not saved; the switch still works for this page
    }
  }

  return [type, choose]
}

export function typeLabel(value) {
  return TYPES.find((t) => t.value === value)?.label ?? value
}

export default function TypeSwitch({ value, onChange }) {
  return (
    <div className="tabs" role="group" aria-label="Report type">
      {TYPES.map((t) => (
        <button
          key={t.value}
          type="button"
          className={`tab ${value === t.value ? 'active' : ''}`}
          aria-pressed={value === t.value}
          onClick={() => onChange(t.value)}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}