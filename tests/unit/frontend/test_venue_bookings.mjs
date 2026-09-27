import assert from 'node:assert/strict'
import test from 'node:test'

import { ApiError } from '../../../frontend/src/lib/api.js'
import {
  canRequestVenue,
  capacityWarning,
  listPendingVenueBookings,
  listVenueBookingsForEvent,
  submitVenueBooking,
  venueBookingErrorMessages,
  venueFit,
} from '../../../frontend/src/lib/venueBookings.js'

const FULL_FORM = {
  eventId: 'e1',
  venueId: 'v1',
  bookingDate: '2026-11-12',
  startTime: '09:00',
  endTime: '12:00',
  notes: '  Setup from 08:30 ',
}

const REQUIRED_ONLY_FORM = {
  ...FULL_FORM,
  notes: '',
}

async function recordingFetch(run) {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ id: 'b1', status: 'pending' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  try {
    await run()
  } finally {
    globalThis.fetch = originalFetch
  }
  return calls
}

// --- TC-FRONTEND-029 -------------------------------------------------------
test('Request venue is offered only for an event in planning', () => {
  for (const status of ['draft', 'submitted', 'returned', 'rejected', undefined]) {
    assert.equal(canRequestVenue(status), false, String(status))
  }
  assert.equal(canRequestVenue('planning'), true)
})

// --- TC-FRONTEND-030 -------------------------------------------------------
test('venue booking calls use the authenticated Kong contract', async () => {
  const calls = await recordingFetch(async () => {
    await submitVenueBooking(FULL_FORM)
    await submitVenueBooking(REQUIRED_ONLY_FORM)
    await listPendingVenueBookings()
  })

  assert.deepEqual(
    calls.map(({ url, options }) => [url, options.method ?? 'GET']),
    [
      ['/api/venue-bookings', 'POST'],
      ['/api/venue-bookings', 'POST'],
      ['/api/venue-bookings/pending', 'GET'],
    ],
  )
  for (const { options } of calls) assert.equal(options.credentials, 'include')

  assert.deepEqual(JSON.parse(calls[0].options.body), {
    event_id: 'e1',
    venue_id: 'v1',
    booking_date: '2026-11-12',
    start_time: '09:00',
    end_time: '12:00',
    notes: 'Setup from 08:30',
  })
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    event_id: 'e1',
    venue_id: 'v1',
    booking_date: '2026-11-12',
    start_time: '09:00',
    end_time: '12:00',
  })
})

// --- TC-FRONTEND-031 -------------------------------------------------------
test('venue booking errors say what happened and what to do', () => {
  const refused = new ApiError("This venue can't take this booking", 422, {
    expected_attendance: 'Studio B holds 150 people; this event expects 200',
    operating_hours: 'Studio B is open 08:00–20:00 on Thursdays',
  })
  assert.deepEqual(venueBookingErrorMessages(refused), [
    'Studio B holds 150 people; this event expects 200',
    'Studio B is open 08:00–20:00 on Thursdays',
  ])

  for (const [status, detail] of [
    [404, 'Event not found'],
    [404, 'Venue not found'],
    [409, 'A venue can only be requested for an event in planning'],
  ]) {
    assert.deepEqual(venueBookingErrorMessages(new ApiError(detail, status)), [detail])
  }

  assert.deepEqual(venueBookingErrorMessages(new ApiError('Not authenticated', 401)), [
    'Your session has expired. Please sign in again.',
  ])

  const unreachable = [
    "We couldn't send the venue request. Nothing was submitted — try again in a moment.",
  ]
  assert.deepEqual(venueBookingErrorMessages(new ApiError('Bookings service unavailable', 502)), unreachable)
  assert.deepEqual(
    venueBookingErrorMessages(new ApiError("We couldn't reach the server.", 0)),
    unreachable,
  )
})

// --- TC-FRONTEND-032 -------------------------------------------------------
test("an event's venue requests load through Kong", async () => {
  const calls = await recordingFetch(async () => {
    await listVenueBookingsForEvent('e 1/2')
  })

  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/venue-bookings?event_id=e%201%2F2')
  assert.equal(calls[0].options.method ?? 'GET', 'GET')
  assert.equal(calls[0].options.credentials, 'include')
})

// --- TC-FRONTEND-035 -------------------------------------------------------
test('each venue is marked against the event requirements', () => {
  const event = {
    expected_attendance: 100,
    room_layout: 'banquet',
    required_facilities: ['projector', 'stage'],
    required_accessibility: ['hearing_loop'],
  }
  const fitting = {
    capacity: 100,
    room_layouts: ['banquet'],
    facilities: ['projector', 'stage'],
    accessibility: ['hearing_loop'],
  }
  const failing = {
    capacity: 80,
    room_layouts: ['theatre'],
    facilities: ['projector'],
    accessibility: [],
  }

  assert.deepEqual(venueFit(event, fitting), [])
  assert.deepEqual(venueFit(event, failing), [
    'Too small: holds 80, event expects 100',
    'No Banquet layout',
    'Missing: Stage',
    'Missing: Hearing loop',
  ])
})

// --- S-35: warn on attendance exceeding venue capacity ---------------------

// --- TC-FRONTEND-036 -------------------------------------------------------
test('a venue too small for the event produces the capacity warning', () => {
  const event = { expected_attendance: 100 }
  const venue = (capacity) => ({ name: 'Studio B', capacity })

  assert.equal(
    capacityWarning(event, venue(80)),
    'Studio B holds 80 people; this event expects 100. Choose a larger venue.',
  )
  assert.equal(capacityWarning(event, venue(100)), null)
  assert.equal(capacityWarning(event, venue(150)), null)
  assert.equal(capacityWarning(event, null), null)
})
