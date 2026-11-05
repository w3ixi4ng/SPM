import test from 'node:test'
import assert from 'node:assert/strict'
import { hasPermission, PERMISSIONS, ROLE_ACCESS } from '../../../frontend/src/lib/access.js'
import { validateBookingDecision, decideVenueBooking, bookingStatusMeta, bookingDecisionErrorMessage, confirmHoldErrorMessage, confirmVenueHold, coordinatorHoldState, staffHoldApproval } from '../../../frontend/src/lib/venueBookings.js'
import { ApiError } from '../../../frontend/src/lib/api.js'

test('only venue staff have booking decision permission', () => {
  for (const role of [...Object.keys(ROLE_ACCESS), 'unknown', undefined]) {
    assert.equal(hasPermission(role, PERMISSIONS.DECIDE_VENUE_BOOKING), role === 'venue_staff')
  }
})

test('approval needs no reason and rejection needs reason or alternative', () => {
  assert.equal(validateBookingDecision({ decision: 'approved' }), null)
  for (const fields of [{ reason: 'Repairs' }, { alternative: 'Try Friday' }, { reason: 'Repairs', alternative: 'Try Friday' }]) {
    assert.equal(validateBookingDecision({ decision: 'rejected', ...fields }), null)
  }
  assert.ok(validateBookingDecision({ decision: 'rejected', reason: ' ', alternative: '\t' }))
  assert.ok(validateBookingDecision({ decision: 'pending' }))
})

test('decision call uses credentialled gateway route and only permitted fields', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/api/venue-bookings/b%201/decision')
      assert.equal(options.method, 'POST')
      assert.equal(options.credentials, 'include')
      assert.deepEqual(JSON.parse(options.body), { decision: 'rejected', reason: null, alternative: 'Try Friday' })
      return new Response(JSON.stringify({ status: 'rejected' }), { status: 200 })
    }
    assert.deepEqual(await decideVenueBooking('b 1', { decision: 'rejected', alternative: ' Try Friday ', decided_by: 'forged' }), { status: 'rejected' })
  } finally { globalThis.fetch = original }
})

test('saved booking statuses have distinct labels and safe failure messages', () => {
  assert.deepEqual(['pending', 'confirmed', 'rejected'].map(s => bookingStatusMeta(s).label), ['Pending', 'Confirmed', 'Rejected'])
  for (const status of [401, 403, 404, 409, 422, 500, 0]) {
    const message = bookingDecisionErrorMessage({ status, message: 'private diagnostic' })
    assert.ok(message && !message.includes('private'))
  }
  assert.match(bookingDecisionErrorMessage({ status: 409 }), /already been decided/)
  assert.match(bookingDecisionErrorMessage({ status: 0 }), /could not confirm/)
})

test('overlap conflict identifies the unavailable venue slot', () => {
  // S-76 replaced S-38's wording; it still identifies the venue, date and time.
  const detail = "Can't confirm this booking: it overlaps Alumni talk (confirmed), which occupies Studio B on 12 Nov 2026 from 10:00 to 12:00."
  assert.equal(bookingDecisionErrorMessage({ status: 409, message: detail }), detail)
  assert.doesNotMatch(bookingDecisionErrorMessage({ status: 409, message: detail }), /decision saved/i)
})

// --- S-81 reopened: the Coordinator confirms a hold ---------------------------

const HOLD = { id: 'H', status: 'held', hold_confirmed_at: null }
const CONFIRMED_HOLD = { ...HOLD, hold_confirmed_at: '2026-11-05T02:00:00Z' }
const PENDING_REQUEST = { id: 'P', status: 'pending' }
const CONFIRMED_BOOKING = { id: 'C', status: 'confirmed' }

// --- TC-FRONTEND-420 -------------------------------------------------------
test('confirming a hold goes to venue_bookings', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options })
    return { ok: true, status: 200, json: async () => CONFIRMED_HOLD }
  })
  assert.deepEqual(await confirmVenueHold('H'), CONFIRMED_HOLD)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/venue-bookings/H/hold-confirmation')
  assert.equal(calls[0].options.method, 'POST')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[0].options.body, undefined)
})

// --- TC-FRONTEND-421 -------------------------------------------------------
test('the Coordinator sees what a hold needs from them', () => {
  assert.deepEqual(coordinatorHoldState(HOLD),
    { canConfirm: true, text: 'Venue Staff are holding this venue for you. Confirm the hold so they can approve it.' })
  assert.deepEqual(coordinatorHoldState(CONFIRMED_HOLD),
    { canConfirm: false, text: 'Hold confirmed. Waiting for Venue Staff to approve it.' })
  assert.equal(coordinatorHoldState(PENDING_REQUEST), null)
  assert.equal(coordinatorHoldState(CONFIRMED_BOOKING), null)
})

// --- TC-FRONTEND-422 -------------------------------------------------------
test('Venue Staff see whether a hold can be approved yet', () => {
  assert.deepEqual(staffHoldApproval(HOLD), {
    canApprove: false,
    text: 'Waiting for the Event Coordinator to confirm this hold. You can reject it or release the hold, but not approve it yet.',
  })
  assert.deepEqual(staffHoldApproval(CONFIRMED_HOLD), { canApprove: true, text: 'The Event Coordinator confirmed this hold.' })
  assert.deepEqual(staffHoldApproval(PENDING_REQUEST), { canApprove: true, text: null })
  assert.deepEqual(staffHoldApproval(CONFIRMED_BOOKING), { canApprove: false, text: null })
})

// --- TC-FRONTEND-423 -------------------------------------------------------
test('a failed confirmation says what happened', () => {
  assert.equal(confirmHoldErrorMessage(new ApiError('Only a tentative hold can be confirmed', 409)),
    'Only a tentative hold can be confirmed. Reload the event to see its current state.')
  const notTheirs = "Only the event's assigned Coordinator can confirm this hold."
  assert.equal(confirmHoldErrorMessage(new ApiError('Permission denied', 403)), notTheirs)
  assert.equal(confirmHoldErrorMessage(new ApiError('Event not found', 404)), notTheirs)
  assert.equal(confirmHoldErrorMessage(new ApiError('Bookings service unavailable', 502)), "We couldn't confirm the hold. Try again.")
  assert.equal(confirmHoldErrorMessage(new ApiError("We couldn't reach the server.", 0)), "We couldn't confirm the hold. Try again.")
})
