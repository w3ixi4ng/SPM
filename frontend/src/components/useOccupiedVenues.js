import { useEffect, useState } from 'react'
import { getOccupiedVenues } from '../lib/venueAvailability.js'

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

// S-34: what occupies each venue on `date`, for filterVenues. Nothing is
// asked for until a whole date is chosen. A failed check is reported rather
// than treated as "nothing is occupied", which would read as every venue free.
export default function useOccupiedVenues(date) {
  const [state, setState] = useState({ date: '', entries: [], failed: false })

  useEffect(() => {
    if (!ISO_DATE.test(date ?? '')) return undefined
    let active = true
    getOccupiedVenues(date).then(
      (body) => { if (active) setState({ date, entries: body.entries, failed: false }) },
      () => { if (active) setState({ date, entries: [], failed: true }) },
    )
    return () => { active = false }
  }, [date])

  // Entries for another date never apply to this one.
  const current = state.date === date
  return { entries: current ? state.entries : [], failed: current && state.failed }
}
