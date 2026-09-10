const MOCK_DELAY_MS = 900
const MOCK_USERNAME = 'demo'
const MOCK_PASSWORD = 'password123'

// Placeholder for Supabase Auth (see VITE_SUPABASE_* in .env.example) — swap
// the body for supabase.auth.signInWithPassword and keep the same signature.
export function login({ username, password }) {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (username === MOCK_USERNAME && password === MOCK_PASSWORD) {
        resolve({ id: 'mock-user-1', username })
      } else {
        reject(new Error('invalid_credentials'))
      }
    }, MOCK_DELAY_MS)
  })
}
