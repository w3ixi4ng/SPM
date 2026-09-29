import { useState } from 'react'
import { bookingDecisionErrorMessage, decideVenueBooking, validateBookingDecision } from '../lib/venueBookings.js'

export default function BookingDecisionForm({ booking, onDecided }) {
  const [decision, setDecision] = useState('')
  const [reason, setReason] = useState('')
  const [alternative, setAlternative] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function save(event) {
    event.preventDefault()
    const payload = { decision, reason, alternative }
    const invalid = validateBookingDecision(payload)
    if (invalid) { setError(invalid); return }
    setSaving(true)
    setError(null)
    try {
      const updated = await decideVenueBooking(booking.id, payload)
      onDecided(updated)
    } catch (failure) {
      setError(bookingDecisionErrorMessage(failure))
      setSaving(false)
    }
  }

  return (
    <form onSubmit={save} aria-label={`Decide booking for ${booking.event_name}`} className="font-ui text-sm mt-4 space-y-3">
      <fieldset disabled={saving} className="space-y-3">
        <legend className="font-medium">Record booking decision</legend>
        <div className="flex gap-4">
          {['approved', 'rejected'].map((value) => (
            <label key={value} className="flex gap-2 items-center">
              <input type="radio" name={`decision-${booking.id}`} value={value}
                checked={decision === value} onChange={() => { setDecision(value); setError(null) }} />
              {value === 'approved' ? 'Approve' : 'Reject'}
            </label>
          ))}
        </div>
        <label className="block">Reason (optional for approval)
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={2}
            className="block w-full border rounded-sm p-2 mt-1" />
        </label>
        <label className="block">Alternative venue or time (optional)
          <textarea value={alternative} onChange={(event) => setAlternative(event.target.value)} rows={2}
            className="block w-full border rounded-sm p-2 mt-1" />
        </label>
        <p>Rejection needs a reason or alternative. Suggestions do not reserve another venue or time. Decisions are final.</p>
        <button type="submit" className="px-4 py-2 rounded-sm bg-teal-700 text-white disabled:opacity-60">
          {saving ? 'Saving…' : 'Save decision'}
        </button>
      </fieldset>
      {error && <p role="alert" className="text-red-700">{error}</p>}
    </form>
  )
}
