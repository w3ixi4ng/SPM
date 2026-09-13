import { useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001'

const DASHBOARD_LABELS = {
  event_organiser: 'Event Organiser Dashboard',
  event_coordinator: 'Event Coordinator Dashboard',
  venue_staff: 'Venue Staff Dashboard',
  technical_support: 'Technical Support Dashboard',
  attendee: 'Attendee Dashboard',
}

function validateForm(values) {
  const errors = {}
  const identifier = values.identifier.trim()

  if (!identifier) {
    errors.identifier = 'Email is required.'
  } else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(identifier)) {
    errors.identifier = 'Use your account email. Username login is not available yet.'
  }

  if (!values.password) {
    errors.password = 'Password is required.'
  }

  return errors
}

async function login(values) {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      identifier: values.identifier.trim(),
      password: values.password,
    }),
  })

  if (!response.ok) {
    throw new Error('Invalid credentials')
  }

  return response.json()
}

function App() {
  const [values, setValues] = useState({ identifier: '', password: '' })
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [session, setSession] = useState(null)

  function updateField(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    setFieldErrors((current) => ({ ...current, [name]: '' }))
    setFormError('')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const errors = validateForm(values)
    setFieldErrors(errors)
    setFormError('')

    if (Object.keys(errors).length > 0) {
      return
    }

    setIsSubmitting(true)
    try {
      const nextSession = await login(values)
      sessionStorage.setItem('connectsphere_access_token', nextSession.access_token)
      sessionStorage.setItem(
        'connectsphere_refresh_token',
        nextSession.refresh_token,
      )
      window.history.pushState({}, '', nextSession.redirect_path)
      setSession(nextSession)
    } catch {
      setFormError('Invalid email or password.')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (session) {
    const dashboardTitle = DASHBOARD_LABELS[session.user.role] || 'Dashboard'

    return (
      <main className="app-shell">
        <section className="dashboard-view" aria-labelledby="dashboard-title">
          <p className="eyebrow">ConnectSphere</p>
          <h1 id="dashboard-title">{dashboardTitle}</h1>
          <p className="dashboard-email">{session.user.email}</p>
        </section>
      </main>
    )
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="brand-block">
          <p className="eyebrow">ConnectSphere</p>
          <h1 id="login-title">Log in</h1>
        </div>

        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <div className="field-group">
            <label htmlFor="identifier">Email or username</label>
            <input
              id="identifier"
              name="identifier"
              type="text"
              autoComplete="username"
              value={values.identifier}
              onChange={updateField}
              aria-invalid={Boolean(fieldErrors.identifier)}
              aria-describedby={
                fieldErrors.identifier ? 'identifier-error' : undefined
              }
            />
            {fieldErrors.identifier ? (
              <p className="field-error" id="identifier-error">
                {fieldErrors.identifier}
              </p>
            ) : null}
          </div>

          <div className="field-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={values.password}
              onChange={updateField}
              aria-invalid={Boolean(fieldErrors.password)}
              aria-describedby={fieldErrors.password ? 'password-error' : undefined}
            />
            {fieldErrors.password ? (
              <p className="field-error" id="password-error">
                {fieldErrors.password}
              </p>
            ) : null}
          </div>

          {formError ? (
            <p className="form-error" role="alert">
              {formError}
            </p>
          ) : null}

          <button className="submit-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Logging in...' : 'Log in'}
          </button>
        </form>
      </section>
    </main>
  )
}

export default App
