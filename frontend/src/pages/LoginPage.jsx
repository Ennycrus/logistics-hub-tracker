import { useState } from 'react'
import { auth } from '../api/client'

/*
 * The login screen. Uses your Django admin username and password.
 * onLoggedIn(user) tells App that login worked, so it can show the app.
 */
export default function LoginPage({ onLoggedIn }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault() // stop the browser reloading the page
    if (loading) return    // ignore double clicks

    setError('')
    setLoading(true)
    try {
      const user = await auth.login(username.trim(), password)
      onLoggedIn(user)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={handleSubmit}>
        <h1>Hub Tracker</h1>
        <p className="muted">Log in with your admin account.</p>

        <label>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={loading}>
          {loading ? 'Logging in…' : 'Log in'}
        </button>
      </form>
    </div>
  )
}