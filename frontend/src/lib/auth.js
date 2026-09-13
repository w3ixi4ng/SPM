const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

// Talks to the real users service via Kong (see backend/services/atomic/users).
// The session comes back as httpOnly cookies, not a token, so every call needs
// credentials: 'include' and the response body is never read for a session id.
async function postJSON(path, body) {
  let res
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error("We couldn't reach the server. Check your connection and try again.")
  }

  let data = null
  try {
    data = await res.json()
  } catch {
    data = null
  }

  if (!res.ok) {
    const error = new Error(data?.detail || 'Something went wrong. Please try again.')
    error.status = res.status
    error.fieldErrors = data?.errors ?? null
    throw error
  }

  return data
}

export function login({ email, password }) {
  return postJSON('/users/login', { email, password })
}

export function signUp({ name, email, password }) {
  return postJSON('/users/signup', { name, email, password })
}
