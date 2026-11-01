import { useEffect, useRef, useState } from 'react'
import EventChangeComparison from './EventChangeComparison.jsx'
import {
  acceptEventChange, getEventChangeReview, rejectEventChange, resolveEventChangeImpact,
} from '../lib/eventChangeRequests.js'

export default function CoordinatorEventChangeReview({ eventId, requestId, onChange }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: '' })
  const [acknowledged, setAcknowledged] = useState(false)
  const [reason, setReason] = useState('')
  const [bookingChoices, setBookingChoices] = useState({})
  const [saving, setSaving] = useState(false)
  const busy = useRef(false)

  async function load() {
    setAcknowledged(false)
    setState({ status: 'loading', data: null, error: '' })
    try {
      setState({ status: 'ready', data: await getEventChangeReview(eventId, requestId), error: '' })
    } catch (error) {
      setState({ status: 'error', data: null, error: error.message || 'Could not load impact review.' })
    }
  }

  useEffect(() => {
    let active = true
    getEventChangeReview(eventId, requestId)
      .then((data) => { if (active) setState({ status: 'ready', data, error: '' }) })
      .catch((error) => { if (active) setState({ status: 'error', data: null, error: error.message || 'Could not load impact review.' }) })
    return () => { active = false }
  }, [eventId, requestId])

  async function perform(write) {
    if (busy.current) return
    busy.current = true
    setSaving(true)
    try {
      await write()
      await load()
      await onChange()
    } catch (error) {
      setState((current) => ({ ...current, error: error.message || 'Review could not be saved. Reload and retry.' }))
    } finally {
      busy.current = false
      setSaving(false)
    }
  }

  if (state.status === 'loading') return <p>Loading impact review…</p>
  if (state.status === 'error') return <section aria-label="Change impact review"><p role="alert">{state.error}</p><button type="button" onClick={load}>Try again</button></section>

  const { event, request, impacts, equipment, bookings } = state.data
  const unresolved = impacts.filter((item) => item.status === 'outstanding')
  return <section aria-label="Change impact review" className="my-6 space-y-4">
    <EventChangeComparison event={event} request={request} equipment={equipment} />
    {state.error && <p role="alert">{state.error}</p>}
    {request.status === 'applying' && <p role="status">Acceptance is incomplete. Reload and retry the operation.</p>}
    {request.status === 'accepted' && <p role="status">Change accepted. A fresh Operational Safety Check is required after affected arrangements are re-reviewed.</p>}
    {request.status === 'rejected' && <p role="status">Request rejected: {request.decision_reason}</p>}
    <div aria-label="Arrangement impact assessment" className="border rounded p-4">
      <h3>Arrangement impact review</h3>
      {impacts.length === 0 && <p>No existing arrangements require re-review.</p>}
      <ul>{impacts.map((item) => <li key={item.id} className="border-b py-3">
        <strong>{item.kind.replaceAll('_', ' ')} {item.arrangement_id}</strong>
        <p>{item.reason}</p><p>Next action: {item.required_action}</p><p>Status: {item.status}</p>
        {item.status === 'resolved' && <p>Reviewed by {item.resolved_by} on {new Date(item.resolved_at).toLocaleString()}: {item.resolution_action}</p>}
        {request.status === 'accepted' && item.status === 'outstanding' && <div>
          {item.kind === 'venue_booking' && <label>Confirmed booking reviewed
            <select value={bookingChoices[item.id] || ''} onChange={(e) => setBookingChoices((prior) => ({ ...prior, [item.id]: e.target.value }))}>
              <option value="">Choose booking</option>
              {bookings.filter((row) => row.status === 'confirmed').map((row) => <option key={row.id} value={row.id}>{row.venue_name || row.id}</option>)}
            </select>
          </label>}
          <button type="button" disabled={saving || (item.kind === 'venue_booking' && !bookingChoices[item.id])}
            onClick={() => perform(() => resolveEventChangeImpact(eventId, requestId, item.id, {
              expected_impact_version: request.impact_version,
              action: item.kind === 'venue_booking' ? 'Confirmed suitable booking reviewed' : 'Fresh Technical Support sign-off reviewed',
              evidence: item.kind === 'venue_booking' ? { booking_id: bookingChoices[item.id] } : { signoff_at: event.technical_signoff_at },
            }))}>Record re-review and resolve</button>
        </div>}
      </li>)}</ul>
    </div>
    {['pending', 'applying'].includes(request.status) && <div className="space-y-3">
      <label><input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />I reviewed every impact and proposed next action.</label>
      <button type="button" disabled={saving || !acknowledged} onClick={() => perform(() => acceptEventChange(eventId, requestId, {
        expected_event_updated_at: event.updated_at, impact_ids: impacts.map((item) => item.id),
        operation_id: request.operation_id || undefined,
      }))}>{request.status === 'applying' ? 'Retry acceptance' : 'Accept significant changes'}</button>
      {request.status === 'pending' && <div><label>Reason for rejection <input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <button type="button" disabled={saving || !reason.trim()} onClick={() => perform(() => rejectEventChange(eventId, requestId, reason.trim()))}>Reject request</button></div>}
    </div>}
    {request.status === 'accepted' && unresolved.length > 0 && <p role="status">{unresolved.length} arrangement impacts remain outstanding. Safety submission is blocked until resolution.</p>}
  </section>
}
