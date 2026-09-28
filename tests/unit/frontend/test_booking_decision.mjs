import test from 'node:test'
import assert from 'node:assert/strict'
import { hasPermission, PERMISSIONS, ROLE_ACCESS } from '../../../frontend/src/lib/access.js'
import { validateBookingDecision, decideVenueBooking, bookingStatusMeta, bookingDecisionErrorMessage } from '../../../frontend/src/lib/venueBookings.js'

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
