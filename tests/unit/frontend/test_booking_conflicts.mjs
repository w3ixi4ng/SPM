// S-76: TC-FRONTEND-096 and 097, booking conflicts for Venue Staff.
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  bookingDecisionErrorMessage,
  clashPairLabel,
  clashReviewHeading,
  getClashesToReview,
  holdActionErrorMessage,
} from '../../../frontend/src/lib/venueBookings.js'

const REFUSED = "Can't confirm this booking: it overlaps Alumni talk (confirmed), which occupies Studio B "
  + 'on 12 Nov 2026 from 09:30 to 12:45 (event 10:00–12:00, 30 min setup, 45 min turnaround).'

// --- TC-FRONTEND-096 -------------------------------------------------------
test('a refused approval or hold shows which booking is in the way', () => {
  assert.equal(bookingDecisionErrorMessage({ status: 409, message: REFUSED }), REFUSED)
  const held = REFUSED.replace("Can't confirm", "Can't hold")
  assert.equal(holdActionErrorMessage({ status: 409, message: held }), held)
  assert.equal(
    bookingDecisionErrorMessage({ status: 409, message: 'This booking request has already been decided' }),
    'This request has already been decided. Reload the list to see the latest requests.',
  )
})

// --- TC-FRONTEND-097 -------------------------------------------------------
test("Venue Staff's clashes to review are fetched and labelled", async () => {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ venues: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    assert.deepEqual(await getClashesToReview(), { venues: [] })
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.equal(calls[0].url, '/api/venue-bookings/clashes')
  assert.equal(calls[0].options.credentials, 'include')

  const side = (name, start, end) => ({ event_name: name, status: 'confirmed', booking_date: '2026-11-12', start_time: start, end_time: end })
  const pair = { first: side('Morning yoga', '09:00:00', '10:00:00'), second: side('Book club', '10:15:00', '11:00:00') }
  assert.equal(
    clashReviewHeading({ venue_name: 'Studio B', setup_minutes: 30, turnaround_minutes: 45, pairs: [pair] }),
    'Studio B · 1 pair · setup 30 min, turnaround 45 min',
  )
  assert.equal(
    clashReviewHeading({ venue_name: 'Hall C', setup_minutes: 15, turnaround_minutes: 15, pairs: [pair, pair] }),
    'Hall C · 2 pairs · setup 15 min, turnaround 15 min',
  )
  assert.equal(clashPairLabel(pair), 'Morning yoga (Confirmed, 09:00–10:00) and Book club (Confirmed, 10:15–11:00) on 12 Nov 2026')
})
