import assert from 'node:assert/strict'
import test from 'node:test'

import { ApiError } from '../../../frontend/src/lib/api.js'
import {
  replacementErrorMessages,
  replacementOriginLabel,
  replacementPath,
  replacementSearchSummary,
  replacementState,
  requestReplacementVenue,
  resolutionPayload,
  resolveAlternativeArrangements,
  searchReplacementVenues,
  validateResolutionNote,
} from '../../../frontend/src/lib/venueBookings.js'

// S-78: replacing a booking an unavailable period affects, TC-FRONTEND-129, 130, 131, 115, and 116.

const A_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const R1_ID = '11111111-1111-4111-8111-111111111111'
const E1 = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
const HALL_C = 'cccccccc-0000-4000-8000-000000000000'

const A = {
  id: A_ID, venue_name: 'Studio B', status: 'confirmed', booking_date: '2026-11-13',
  start_time: '10:00:00', end_time: '12:00:00', replaces_booking_id: null,
  requires_alternative_arrangements: true, unavailable_periods: [],
}
const R1 = { ...A, id: R1_ID, venue_name: 'Hall C', status: 'pending', replaces_booking_id: A_ID, requires_alternative_arrangements: false }

async function recordingFetch(answers, run) {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    const [status, body] = answers.shift()
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await run()
  } finally {
    globalThis.fetch = originalFetch
  }
  return calls
}

// --- TC-FRONTEND-129 -------------------------------------------------------
test('a flagged booking offers a replacement and a resolution, and an unflagged one offers neither', () => {
  assert.deepEqual(replacementState(A, [A]), { actions: ['replace', 'resolve'], label: null })
  for (const status of ['pending', 'held']) {
    assert.deepEqual(replacementState(A, [A, { ...R1, status }]), {
      actions: ['resolve'], label: 'Replacement requested: Hall C, waiting for Venue Staff',
    })
  }
  assert.deepEqual(replacementState(A, [A, { ...R1, status: 'rejected' }]), {
    actions: ['replace', 'resolve'], label: 'Hall C declined the replacement request',
  })
  const replaced = { ...A, status: 'replaced', requires_alternative_arrangements: false, replaced_by_booking_id: R1_ID }
  assert.deepEqual(replacementState(replaced, [replaced, { ...R1, status: 'confirmed' }]), {
    actions: [], label: 'Replaced by Hall C',
  })
  const resolved = { ...A, requires_alternative_arrangements: false, alternative_resolution_note: 'Moved online' }
  assert.deepEqual(replacementState(resolved, [resolved]), { actions: [], label: 'Resolved: Moved online' })
  const plain = { ...A, requires_alternative_arrangements: false }
  assert.deepEqual(replacementState(plain, [plain]), { actions: [], label: null })
  const pending = { ...plain, status: 'pending' }
  assert.deepEqual(replacementState(pending, [pending]), { actions: [], label: null })
  assert.deepEqual(replacementState(R1, [A, R1]), { actions: [], label: 'Replacement for Studio B' })
})

test("Venue Staff's request page names the booking a replacement replaces", () => {
  assert.equal(replacementOriginLabel({ ...R1, replaces: { venue_name: 'Studio B' } }), 'Replacement for Studio B')
  assert.equal(replacementOriginLabel({ ...A, replaces: null }), null)
})

// --- TC-FRONTEND-130 -------------------------------------------------------
test('the resolution note must be written, and not too long', () => {
  assert.equal(validateResolutionNote(''), "Say what you've arranged instead.")
  assert.equal(validateResolutionNote('   '), "Say what you've arranged instead.")
  assert.equal(validateResolutionNote('x'.repeat(501)), 'Keep the note to 500 characters.')
  assert.equal(validateResolutionNote('x'.repeat(500)), null)
  assert.equal(validateResolutionNote('  Moved online  '), null)
  assert.deepEqual(resolutionPayload('  Moved online  '), { note: 'Moved online' })
})

// --- TC-FRONTEND-131 -------------------------------------------------------
test('the replacement request sends only the venue and notes', async () => {
  const calls = await recordingFetch([[201, R1], [200, A], [200, { booking: A, venues: [] }]], async () => {
    await requestReplacementVenue(A_ID, { venueId: HALL_C, notes: '  ' })
    await resolveAlternativeArrangements(A_ID, 'Moved online')
    await searchReplacementVenues(A_ID)
  })

  assert.equal(calls[0].url, `/api/venue-bookings/${A_ID}/replacement`)
  assert.equal(calls[0].options.method, 'POST')
  assert.deepEqual(JSON.parse(calls[0].options.body), { venue_id: HALL_C, notes: null })
  assert.equal(calls[1].url, `/api/venue-bookings/${A_ID}/resolution`)
  assert.equal(calls[1].options.method, 'POST')
  assert.deepEqual(JSON.parse(calls[1].options.body), { note: 'Moved online' })
  assert.equal(calls[2].url, `/api/venue-bookings/${A_ID}/replacement-venues`)
  assert.equal(calls[2].options.method, undefined)
})

// --- TC-FRONTEND-115 -------------------------------------------------------
test('every failure says what happened and what to do next', () => {
  assert.deepEqual(
    replacementErrorMessages(new ApiError("This booking doesn't need a replacement venue", 409)),
    ['This booking no longer needs a replacement. Go back to the event to see its current state.'],
  )
  assert.deepEqual(
    replacementErrorMessages(new ApiError('A replacement request for this booking is already with Venue Staff', 409)),
    ["You've already asked for a replacement for this booking. Wait for Venue Staff's decision."],
  )
  const taken = 'Hall F is already confirmed on 13 Nov 2026 from 11:00 to 13:00.'
  assert.deepEqual(replacementErrorMessages(new ApiError(taken, 409)), [taken, 'Choose another venue.'])
  assert.deepEqual(
    replacementErrorMessages(new ApiError("This venue can't take this booking", 422, {
      expected_attendance: 'Room D holds 100 people; this event expects 120',
      required_facilities: 'Room D does not have: microphones',
    })),
    ['Room D holds 100 people; this event expects 120', 'Room D does not have: microphones'],
  )
  assert.deepEqual(
    replacementErrorMessages(new ApiError('Booking not found', 404)),
    ["We couldn't find this booking. Go back to the event and try again."],
  )
  for (const error of [new ApiError('Bookings service unavailable', 502), new ApiError('offline', 0)]) {
    assert.deepEqual(replacementErrorMessages(error), ["We couldn't reach the booking service. Try again in a moment."])
  }
})

// --- TC-FRONTEND-116 -------------------------------------------------------
test("the replacement screen's path and its empty state", () => {
  assert.equal(replacementPath(E1, A_ID), `/coordinator/events/${E1}/bookings/${A_ID}/replacement`)
  assert.equal(
    replacementSearchSummary({ booking: A, venues: [] }),
    "No venue can take this event on 13 Nov 2026 from 10:00 to 12:00. Resolve the booking with a note if you've made other arrangements.",
  )
  assert.equal(
    replacementSearchSummary({ booking: A, venues: [{}, {}] }),
    '2 venues can take this event on 13 Nov 2026 from 10:00 to 12:00.',
  )
  assert.equal(
    replacementSearchSummary({ booking: A, venues: [{}] }),
    '1 venue can take this event on 13 Nov 2026 from 10:00 to 12:00.',
  )
})
