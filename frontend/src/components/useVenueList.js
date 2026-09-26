import { useCallback, useEffect, useState } from 'react'
import { listVenues, venueErrorMessage } from '../lib/venues.js'

function loadVenues() {
  return listVenues().then(
    (venues) => ({ venues, loading: false, error: null }),
    (error) => ({
      venues: [],
      loading: false,
      error: {
        401: venueErrorMessage(error),
        403: 'Your role is not permitted to view venues.',
      }[error.status] ?? "We couldn't load venues right now.",
    }),
  )
}

// Loads the venue list for a dashboard. `reload` is what the add-venue panel
// calls after a save, so the list shows what the service stored.
export default function useVenueList() {
  const [state, setState] = useState({ venues: [], loading: true, error: null })

  useEffect(() => {
    let active = true
    loadVenues().then((next) => { if (active) setState(next) })
    return () => { active = false }
  }, [])

  const reload = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: null }))
    loadVenues().then(setState)
  }, [])

  return { ...state, reload }
}
