import assert from 'node:assert/strict'
import test from 'node:test'

import { ApiError } from '../../../frontend/src/lib/api.js'
import {
  canRequestVenue,
  holdActionErrorMessage,
  listPendingVenueBookings,
  listVenueBookingsForEvent,
  placeVenueHold,
  releaseVenueHold,
  submitVenueBooking,
  venueBookingErrorMessages,
  venueFit,
  venueRequestLinkLabel,
  venueWarning,
} from '../../../frontend/src/lib/venueBookings.js'

test('hold actions use authenticated gateway routes and safe errors', async () => {
  const calls = await recordingFetch(async () => {
    await placeVenueHold('b 1/2')
    await releaseVenueHold('b 1/2')
  })
  assert.deepEqual(calls.map(({ url, options }) => [url, options.method]), [
    ['/api/venue-bookings/b%201%2F2/hold', 'POST'],
    ['/api/venue-bookings/b%201%2F2/release', 'POST'],
  ])
  assert.equal(holdActionErrorMessage(new ApiError('conflict', 409)), 'conflict')
  assert.match(holdActionErrorMessage(new ApiError('down', 500)), /Reload the list/)
})

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

// --- S-35: warn when the chosen venue doesn't suit the event --------------

// --- TC-FRONTEND-039 -------------------------------------------------------
test("a venue that doesn't suit the event produces a warning listing why", () => {
  const event = {
    expected_attendance: 100,
    room_layout: 'banquet',
    required_facilities: ['stage'],
    required_accessibility: ['lift'],
  }
  const venue = (overrides) => ({
    name: 'Studio B',
    capacity: 100,
    room_layouts: ['banquet'],
    facilities: ['stage'],
    accessibility: ['lift'],
    ...overrides,
  })

  assert.equal(
    venueWarning(event, venue({ capacity: 80 })),
    "Studio B doesn't suit this event: Too small: holds 80, event expects 100. Choose a venue that fits.",
  )
  assert.equal(
    venueWarning(event, venue({ capacity: 150, room_layouts: ['theatre'], facilities: [], accessibility: [] })),
    "Studio B doesn't suit this event: No Banquet layout; Missing: Stage; Missing: Lift. Choose a venue that fits.",
  )
  assert.equal(venueWarning(event, venue({})), null)
  assert.equal(venueWarning(event, null), null)
})

// --- S-34: opening hours on the request screen -----------------------------

const THURSDAY_ONLY = {
  name: 'Studio B',
  capacity: 100,
  room_layouts: ['theatre'],
  facilities: [],
  accessibility: [],
  operating_hours: [{ day: 'thu', open: '08:00:00', close: '20:00:00' }],
}
const NO_NEEDS = { expected_attendance: 10 }

// --- TC-FRONTEND-065 -------------------------------------------------------
test("a venue closed at the booking's date and time is marked", () => {
  const at = (date, startTime, endTime) => ({ date, startTime, endTime })
  assert.deepEqual(venueFit(NO_NEEDS, THURSDAY_ONLY, at('2026-11-12', '09:00', '12:00')), [])
  assert.deepEqual(
    venueFit(NO_NEEDS, THURSDAY_ONLY, at('2026-11-12', '07:00', '10:00')),
    ['Open 08:00–20:00 on Thursdays'],
  )
  assert.deepEqual(venueFit(NO_NEEDS, THURSDAY_ONLY, at('2026-11-14', '10:00', '12:00')), ['Closed on Saturdays'])
  assert.deepEqual(venueFit(NO_NEEDS, THURSDAY_ONLY), [])
})

// --- TC-FRONTEND-066 -------------------------------------------------------
test('a closed venue produces the S-35 warning', () => {
  assert.equal(
    venueWarning(NO_NEEDS, THURSDAY_ONLY, { date: '2026-11-14', startTime: '10:00', endTime: '12:00' }),
    "Studio B doesn't suit this event: Closed on Saturdays. Choose a venue that fits.",
  )
})

// --- TC-FRONTEND-103 -------------------------------------------------------
test('the event page offers Add another venue once a venue is requested', () => {
  assert.equal(venueRequestLinkLabel([]), 'Request venue')
  for (const bookings of [
    [{ status: 'held' }],
    [{ status: 'rejected' }],
    [{ status: 'pending' }, { status: 'confirmed' }],
  ]) {
    assert.equal(venueRequestLinkLabel(bookings), 'Add another venue', JSON.stringify(bookings))
  }
})
