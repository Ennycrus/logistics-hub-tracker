import { useEffect, useState } from 'react'
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

/*
 * The top of the app. It decides what to show:
 *   - "Loading…" while it asks Django who is logged in
 *   - the login page if nobody is
 *   - the admin layout with the page for the current address if you are
 */
export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')

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

  async function handleLogout() {
    await auth.logout()
    await auth.csrf() // Django gives a fresh token after logout
    setUser({ authenticated: false, username: null })
  }

  if (checking) return <p className="center muted">Loading…</p>
  if (error) return <p className="center error">{error}</p>
  if (!user?.authenticated) return <LoginPage onLoggedIn={setUser} />

  return (
    <BrowserRouter>
      <Layout username={user.username} onLogout={handleLogout}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/shipments" element={<ShipmentsPage />} />
          <Route path="/pending" element={<PendingPage />} />
          <Route path="/report" element={<ReportPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          {/* Any other address (including the home page) goes to the Dashboard. */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}