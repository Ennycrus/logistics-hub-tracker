import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'

// The menu: address, label and icon for each page.
const PAGES = [
  { to: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
  { to: '/import', label: 'Import', icon: 'upload' },
  { to: '/shipments', label: 'Shipments', icon: 'box' },
  { to: '/pending', label: 'Pending', icon: 'clock' },
  { to: '/report', label: 'Daily Report', icon: 'report' },
  { to: '/weekly', label: 'Weekly', icon: 'week' },
  { to: '/history', label: 'History', icon: 'history' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
]

// Small line icons drawn with SVG (no extra package needed).
const ICON_PATHS = {
  dashboard: 'M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z',
  upload: 'M12 16V4M7 9l5-5 5 5M4 20h16',
  box: 'M21 8l-9-5-9 5 9 5 9-5zM3 8v8l9 5 9-5V8M12 13v8',
  report: 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6',
  history: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 3',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  week: 'M4 5h16v16H4zM4 10h16M9 3v4M15 3v4M8 14h2M14 14h2M8 18h2',
  menu: 'M3 6h18M3 12h18M3 18h18',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
}

export function Icon({ name }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICON_PATHS[name]} />
    </svg>
  )
}

/*
 * The admin layout: a dark menu on the left, a header with the page title,
 * and the current page underneath. On a phone the menu slides in from the left.
 */
export default function Layout({ username, onLogout, children }) {
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  // Close the phone menu whenever you go to another page.
  useEffect(() => setMenuOpen(false), [location.pathname])

  const current = PAGES.find((p) => location.pathname.startsWith(p.to))

  return (
    <div className="layout">
      <aside className={`sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="brand">
          <span className="brand-mark">HT</span>
          <span>Hub Tracker</span>
        </div>
        <nav className="side-nav">
          {PAGES.map((p) => (
            <NavLink key={p.to} to={p.to}>
              <Icon name={p.icon} />
              {p.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="avatar">{username.slice(0, 1).toUpperCase()}</span>
          <span className="sidebar-user">{username}</span>
          <button className="icon-button" onClick={onLogout} title="Log out" aria-label="Log out">
            <Icon name="logout" />
          </button>
        </div>
      </aside>

      {menuOpen && <div className="sidebar-backdrop" onClick={() => setMenuOpen(false)} />}

      <div className="main">
        <header className="page-header">
          <button className="icon-button menu-button" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Icon name="menu" />
          </button>
          <div>
            <div className="breadcrumb">Hub Tracker / {current?.label ?? ''}</div>
            <h1>{current?.label ?? 'Hub Tracker'}</h1>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  )
}