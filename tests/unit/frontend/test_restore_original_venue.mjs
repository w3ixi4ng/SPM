import assert from 'node:assert/strict'
import test from 'node:test'

import { ApiError } from '../../../frontend/src/lib/api.js'
import {
  bookingStatusMeta,
  decideRestore,
  listRestoreRequests,
  replacementState,
  requestRestore,
  restoreErrorMessage,
  restoreNotice,
  restoreRequestSummary,
} from '../../../frontend/src/lib/venueBookings.js'

// S-90: restoring the original booking, TC-FRONTEND-286..288.

const O_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const R_ID = '11111111-1111-4111-8111-111111111111'

const O = {
  id: O_ID, venue_name: 'Studio B', status: 'confirmed', event_name: 'Alumni networking evening',
  booking_date: '2026-11-12', start_time: '10:00:00', end_time: '12:00:00',
  replaces_booking_id: null, requires_alternative_arrangements: false,
  restore_requested_at: null, alternative_resolution_note: null,
}
const R = { ...O, id: R_ID, venue_name: 'Hall C', status: 'pending', replaces_booking_id: O_ID }

async function recordingFetch(run) {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await run()
  } finally {
    globalThis.fetch = originalFetch
  }
  return calls
}

// --- TC-FRONTEND-286 ---------------------------------------------------------
test('the event page offers a restore once the original venue is free', () => {
  assert.deepEqual(replacementState(O, [O, R]), {
    actions: ['restore'],
    label: 'Replacement requested: Hall C, waiting for Venue Staff. Studio B is free again.',
  })
  // Still flagged: the venue isn't free, so S-78's options are unchanged.
  const flagged = { ...O, requires_alternative_arrangements: true }
  assert.deepEqual(replacementState(flagged, [flagged, R]), {
    actions: ['resolve'],
    label: 'Replacement requested: Hall C, waiting for Venue Staff',
  })
  const asked = { ...O, restore_requested_at: '2026-11-01T02:00:00Z' }
  assert.deepEqual(replacementState(asked, [asked, R]), {
    actions: [],
    label: 'Restore requested: waiting for Venue Staff to confirm Studio B',
  })
  const restored = { ...O, alternative_resolution_note: 'Restored to the original venue' }
  const withdrawn = { ...R, status: 'withdrawn' }
  assert.deepEqual(replacementState(restored, [restored, withdrawn]), {
    actions: [], label: 'Resolved: Restored to the original venue',
  })
  assert.deepEqual(replacementState(withdrawn, [restored, withdrawn]), {
    actions: [], label: 'Withdrawn: Studio B was restored',
  })
  const replaced = { ...O, status: 'replaced', replaced_by_booking_id: R_ID }
  assert.deepEqual(replacementState(replaced, [replaced, { ...R, status: 'confirmed' }]), {
    actions: [], label: 'Replaced by Hall C',
  })
  // A replacement that was rejected leaves nothing to restore from.
  assert.deepEqual(replacementState(O, [O, { ...R, status: 'rejected' }]).actions, [])
})

// --- TC-FRONTEND-287 ---------------------------------------------------------
test('restore requests and decisions go to the composite', async () => {
  const calls = await recordingFetch(async () => {
    await requestRestore(O_ID)
    await listRestoreRequests()
    await decideRestore(O_ID, 'approved')
    await decideRestore(O_ID, 'declined')
  })
  assert.deepEqual(calls.map(({ url, options }) => [options.method ?? 'GET', url, options.body ?? null]), [
    ['POST', `/api/venue-bookings/${O_ID}/restore`, null],
    ['GET', '/api/venue-bookings/restores', null],
    ['POST', `/api/venue-bookings/${O_ID}/restore-decision`, '{"decision":"approved"}'],
    ['POST', `/api/venue-bookings/${O_ID}/restore-decision`, '{"decision":"declined"}'],
  ])
  assert.deepEqual(bookingStatusMeta('withdrawn'), { label: 'Withdrawn', color: '#4C5A70' })
})

test('a refused restore says why in the service\'s words', () => {
  const busy = 'Studio B is unavailable from 12 Nov 2026 12:30 to 12 Nov 2026 14:00.'
  assert.equal(restoreErrorMessage(new ApiError(busy, 409)), busy)
  assert.equal(restoreErrorMessage(new ApiError('Nope', 403)), 'You do not have permission to do this.')
  assert.equal(
    restoreErrorMessage(new ApiError('Bookings service unavailable', 502)),
    'We could not reach the booking service. Try again in a moment.',
  )
})

// --- TC-FRONTEND-288 ---------------------------------------------------------
test('venue staff see what confirming a restore will do', () => {
  const row = { ...O, replacement: { venue_name: 'Hall C', status: 'pending' } }
  assert.deepEqual(restoreRequestSummary(row), {
    title: 'Alumni networking evening',
    when: '12 Nov 2026, 10:00 am to 12:00 pm',
    keeps: 'Keep Studio B',
    withdraws: 'Withdraw the request for Hall C',
  })
  assert.equal(restoreNotice('approved', row), 'Studio B restored for Alumni networking evening.')
  assert.equal(restoreNotice('declined', row), 'Restore of Studio B for Alumni networking evening declined.')
})
