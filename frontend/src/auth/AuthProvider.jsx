import { useCallback, useEffect, useMemo, useState } from 'react'
import { getCurrentUser, logout } from '../lib/auth.js'
import AuthContext from './AuthContext.js'

export default function AuthProvider({ children }) {
  const [state, setState] = useState({
    status: 'loading',
    user: null,
    error: null,
  })

  const refresh = useCallback(async () => {
    setState((current) => ({ ...current, status: 'loading', error: null }))
    try {
      const user = await getCurrentUser()
      setState({ status: 'authenticated', user, error: null })
      return user
    } catch (error) {
      if (error.status === 401) {
        setState({ status: 'unauthenticated', user: null, error: null })
        return null
      }
      setState({ status: 'error', user: null, error })
      throw error
    }
  }, [])

  useEffect(() => {
    let active = true
    getCurrentUser()
      .then((user) => {
        if (active) setState({ status: 'authenticated', user, error: null })
      })
      .catch((error) => {
        if (!active) return
        if (error.status === 401) {
          setState({ status: 'unauthenticated', user: null, error: null })
        } else {
          setState({ status: 'error', user: null, error })
        }
      })
    return () => {
      active = false
    }
  }, [])

  const signOut = useCallback(async () => {
    try {
      await logout()
    } finally {
      setState({ status: 'unauthenticated', user: null, error: null })
    }
  }, [])

  const value = useMemo(
    () => ({ ...state, refresh, signOut }),
    [refresh, signOut, state],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
