import { useEffect, useState } from 'react'
import EventChangeComparison from './EventChangeComparison.jsx'
import { getEventChangeRequests } from '../lib/eventChangeRequests.js'

export default function CoordinatorEventChangePanel({ eventId }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: '' })

  async function load() {
    setState({ status: 'loading', data: null, error: '' })
    try {
      const data = await getEventChangeRequests(eventId)
      setState({ status: 'ready', data, error: '' })
    } catch (failure) {
      setState({ status: 'error', data: null, error: failure.message || 'Could not load change requests.' })
    }
  }

  useEffect(() => {
    let active = true
    getEventChangeRequests(eventId)
      .then((data) => { if (active) setState({ status: 'ready', data, error: '' }) })
      .catch((failure) => { if (active) setState({ status: 'error', data: null, error: failure.message || 'Could not load change requests.' }) })
    return () => { active = false }
  }, [eventId])

  if (state.status === 'loading') return <p>Loading change requests…</p>
  if (state.status === 'error') return <section aria-label="Event change requests"><p role="alert">{state.error}</p><button type="button" onClick={load}>Try again</button></section>

  const pending = state.data.requests.find((request) => request.status === 'pending')
  if (!pending) return null
  return <EventChangeComparison event={state.data.event} request={pending} equipment={state.data.equipment} />
}
