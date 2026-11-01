import { useEffect, useState } from 'react'
import { listVenueBookingsForEvent } from '../lib/venueBookings.js'
import { resolveAssignedEditImpact } from '../lib/eventRequests.js'

export default function CoordinatorEditImpacts({ event, onSaved }) {
  const [bookings, setBookings] = useState([])
  const [choices, setChoices] = useState({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const outstanding = (event.s60_edit_impacts || []).filter((item) => item.status === 'outstanding')
  const hasVenueImpact = outstanding.some((item) => item.kind === 'venue_booking')

  useEffect(() => {
    let active = true
    if (hasVenueImpact) {
      listVenueBookingsForEvent(event.id).then((rows) => { if (active) setBookings(rows) })
        .catch((failure) => { if (active) setError(failure.message || 'Bookings could not be loaded.') })
    }
    return () => { active = false }
  }, [event.id, event.s60_edit_impact_version, hasVenueImpact])

  if (!outstanding.length) return null
  async function resolve(item) {
    if (saving) return
    setSaving(true)
    setError('')
    try {
      const updated = await resolveAssignedEditImpact(event.id, item.id, {
        expected_impact_version: event.s60_edit_impact_version,
        action: item.kind === 'venue_booking' ? 'Confirmed suitable booking reviewed' : 'Fresh Technical Support sign-off reviewed',
        evidence: item.kind === 'venue_booking' ? { booking_id: choices[item.id] } : { signoff_at: event.technical_signoff_at },
      })
      onSaved(updated)
    } catch (failure) {
      setError(failure.message || 'Impact could not be resolved.')
    } finally {
      setSaving(false)
    }
  }

  return <section aria-label="Outstanding event edit impacts" className="my-6 border rounded p-4">
    <h3>Arrangements needing re-review</h3>
    {error && <p role="alert">{error}</p>}
    <ul>{outstanding.map((item) => <li key={item.id} className="border-b py-3">
      <strong>{item.kind.replaceAll('_', ' ')} {item.arrangement_id}</strong>
      <p>{item.reason}</p><p>Next action: {item.required_action}</p>
      {item.kind === 'venue_booking' && <label>Confirmed booking reviewed
        <select value={choices[item.id] || ''} onChange={(e) => setChoices((old) => ({ ...old, [item.id]: e.target.value }))}>
          <option value="">Choose booking</option>
          {bookings.filter((row) => row.status === 'confirmed').map((row) => <option key={row.id} value={row.id}>{row.venue_name || row.id}</option>)}
        </select>
      </label>}
      <button type="button" disabled={saving || (item.kind === 'venue_booking' && !choices[item.id])} onClick={() => resolve(item)}>Record re-review and resolve</button>
    </li>)}</ul>
    <p role="status">Safety submission remains blocked until these arrangements are resolved.</p>
  </section>
}
