import { requestJSON } from './api.js'

// Talks to the real users service via Kong (see backend/services/atomic/users).
// The session comes back as httpOnly cookies, not a token, so every call needs
// credentials: 'include' and the response body is never read for a session id.
export function login({ email, password }) {
  return requestJSON('/users/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
}

export function signUp({ name, email, password }) {
  return requestJSON('/users/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })
}

export function getCurrentUser() {
  return requestJSON('/users/me')
}

export function logout() {
  return requestJSON('/users/logout', { method: 'POST' })
}
