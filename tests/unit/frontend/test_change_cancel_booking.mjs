import assert from 'node:assert/strict'
import test from 'node:test'

import { ApiError } from '../../../frontend/src/lib/api.js'
import {
  bookingToChangeForm,
  cancelVenueBooking,
  cancelVenueBookingPrompt,
  canChangeVenueBooking,
  changeVenueBooking,
  VENUE_BOOKING_CANCELLED,
  VENUE_BOOKING_CHANGED,
  venueBookingChangeErrorMessage,
} from '../../../frontend/src/lib/venueBookings.js'

const HALL = {
  id: 'b1',
  event_id: 'e1',
  venue_id: 'v1',
  venue_name: 'Main Hall',
  booking_date: '2026-11-12',
  start_time: '09:00:00',
  end_time: '12:00:00',
  notes: 'Side door',
  status: 'confirmed',
}

// --- TC-FRONTEND-127 -------------------------------------------------------
test('which bookings offer Change and Cancel, and what the screens say', () => {
  for (const status of ['pending', 'held', 'confirmed']) {
    assert.equal(canChangeVenueBooking({ status }, 'planning'), true, status)
    assert.equal(canChangeVenueBooking({ status }, 'confirmed'), false, `${status} after planning`)
  }
  assert.equal(canChangeVenueBooking({ status: 'rejected' }, 'planning'), false)

  assert.deepEqual(bookingToChangeForm(HALL), {
    eventId: 'e1',
    venueId: 'v1',
    bookingDate: '2026-11-12',
    startTime: '09:00',
    endTime: '12:00',
    notes: 'Side door',
  })
  assert.equal(bookingToChangeForm({ ...HALL, notes: null }).notes, '')

  assert.equal(
    cancelVenueBookingPrompt(HALL),
    'Cancel Main Hall on 12 Nov 2026, 09:00–12:00? Its time is freed for other events. '
      + 'Your other venue bookings stay as they are.',
  )
  assert.equal(VENUE_BOOKING_CHANGED, "Venue booking changed. It's pending until Venue Staff review it again.")
  assert.equal(VENUE_BOOKING_CANCELLED, 'Venue booking cancelled. Its time is free for other events.')
})

// --- TC-FRONTEND-128 -------------------------------------------------------
test('the change and cancel calls go through Kong', async () => {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return options.method === 'DELETE'
      ? new Response(null, { status: 204 })
      : new Response(JSON.stringify({ id: 'b1' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await changeVenueBooking('b 1/2', { ...bookingToChangeForm(HALL), startTime: '10:00', endTime: '13:00' })
    await changeVenueBooking('b 1/2', { ...bookingToChangeForm(HALL), notes: '  ' })
    await cancelVenueBooking('b 1/2')
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(({ url, options }) => [url, options.method, options.credentials]), [
    ['/api/venue-bookings/b%201%2F2', 'PATCH', 'include'],
    ['/api/venue-bookings/b%201%2F2', 'PATCH', 'include'],
    ['/api/venue-bookings/b%201%2F2', 'DELETE', 'include'],
  ])
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    venue_id: 'v1', booking_date: '2026-11-12', start_time: '10:00', end_time: '13:00', notes: 'Side door',
  })
  // Blank notes clear them; there is never an event_id.
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    venue_id: 'v1', booking_date: '2026-11-12', start_time: '09:00', end_time: '12:00', notes: null,
  })
})

test('a failed change or cancel says the booking has not changed', () => {
  const clash = 'Studio C is already confirmed on 12 Nov 2026 from 13:00 to 15:00.'
  assert.equal(venueBookingChangeErrorMessage(new ApiError(clash, 409)), clash)
  for (const status of [422, 404, 500, 0]) {
    assert.match(venueBookingChangeErrorMessage(new ApiError('x', status)), /The booking has not changed\.$/, String(status))
  }
})
