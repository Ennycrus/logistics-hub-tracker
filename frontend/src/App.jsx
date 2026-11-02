import { useEffect, useRef, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { auth } from './api/client'
import Layout from './components/Layout'
import DashboardPage from './pages/DashboardPage'
import HistoryPage from './pages/HistoryPage'
import ImportPage from './pages/ImportPage'
import LoginPage from './pages/LoginPage'
import PendingPage from './pages/PendingPage'
import ReportPage from './pages/ReportPage'
import SettingsPage from './pages/SettingsPage'
import ShipmentsPage from './pages/ShipmentsPage'
import WeeklyPage from './pages/WeeklyPage'

// Anything you do on the page counts as activity and restarts the idle clock.
const ACTIVITY_EVENTS = ['mousedown', 'keydown', 'scroll', 'touchstart']

/*
 * The top of the app. It decides what to show:
 *   - "Loading…" while it asks Django who is logged in
 *   - the login page if nobody is
 *   - the admin layout with the page for the current address if you are
 *
 * Idle log-out: after the number of minutes Django sets (IDLE_TIMEOUT_MINUTES,
 * 15 by default) with no clicks, typing or scrolling, you are logged out and
 * must enter your password again. Django also ends the session on its side,
 * so the data stays protected even if this page is left open.
 */
export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('') // shown on the login page, e.g. "logged out after 15 minutes"
  const lastActivity = useRef(Date.now())

  // Runs once when the page first opens.
  useEffect(() => {
    async function start() {
      try {
        await auth.csrf()              // get the CSRF cookie
        setUser(await auth.me())       // who is logged in?
      } catch (err) {
        setError(err.message)
      } finally {
        setChecking(false)
      }
    }
    start()
  }, [])

  const loggedIn = Boolean(user?.authenticated)
  const timeoutMinutes = user?.idle_timeout_minutes ?? 15

  // While logged in: watch for activity, and log out after the idle time.
  useEffect(() => {
    if (!loggedIn) return

    async function endSession(message) {
      try {
        await auth.logout()
        await auth.csrf() // Django gives a fresh token after logout
      } catch {
        // already logged out on the server: nothing to do
      }
      setUser({ authenticated: false, username: null, idle_timeout_minutes: timeoutMinutes })
      setNotice(message)
    }

    const idleMessage = `You were logged out after ${timeoutMinutes} minutes without activity. Please log in again.`

    function markActive() {
      lastActivity.current = Date.now()
    }
    function checkIdle() {
      if (Date.now() - lastActivity.current >= timeoutMinutes * 60 * 1000) endSession(idleMessage)
    }
    // Django already ended the session (e.g. the laptop was asleep): just show the login page.
    function onExpired() {
      endSession(idleMessage)
    }

    markActive()
    ACTIVITY_EVENTS.forEach((name) => window.addEventListener(name, markActive, { passive: true }))
    window.addEventListener('auth:expired', onExpired)
    document.addEventListener('visibilitychange', checkIdle) // check as soon as you come back to the tab
    const timer = setInterval(checkIdle, 30 * 1000)

    return () => {
      ACTIVITY_EVENTS.forEach((name) => window.removeEventListener(name, markActive))
      window.removeEventListener('auth:expired', onExpired)
      document.removeEventListener('visibilitychange', checkIdle)
      clearInterval(timer)
    }
  }, [loggedIn, timeoutMinutes])

  async function handleLogout() {
    await auth.logout()
    await auth.csrf() // Django gives a fresh token after logout
    setNotice('')
    setUser({ authenticated: false, username: null, idle_timeout_minutes: timeoutMinutes })
  }

  function handleLoggedIn(newUser) {
    setNotice('')
    setUser(newUser)
  }

  if (checking) return <p className="center muted">Loading…</p>
  if (error) return <p className="center error">{error}</p>
  if (!loggedIn) return <LoginPage onLoggedIn={handleLoggedIn} notice={notice} />

  return (
    <BrowserRouter>
      <Layout username={user.username} onLogout={handleLogout}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/shipments" element={<ShipmentsPage />} />
          <Route path="/pending" element={<PendingPage />} />
          <Route path="/report" element={<ReportPage />} />
          <Route path="/weekly" element={<WeeklyPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          {/* Any other address (including the home page) goes to the Dashboard. */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}