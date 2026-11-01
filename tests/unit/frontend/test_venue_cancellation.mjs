import assert from 'node:assert/strict'
import test from 'node:test'

import { ApiError } from '../../../frontend/src/lib/api.js'
import { describeEntry } from '../../../frontend/src/lib/eventHistory.js'
import { bookingStatusMeta } from '../../../frontend/src/lib/venueBookings.js'
import {
  canCancelForUnavailableVenue,
  venueCancellationBody,
  venueCancellationErrorMessage,
  venueCancellationErrors,
  venueCancellationIncomplete,
} from '../../../frontend/src/lib/venueCancellation.js'

const FLAGGED = [
  { id: 'b1', status: 'confirmed', requires_alternative_arrangements: true },
  { id: 'b2', status: 'confirmed', requires_alternative_arrangements: false },
]
const CLEAR = [{ id: 'b2', status: 'confirmed', requires_alternative_arrangements: false }]

// TC-FRONTEND-400
test('S-89 cancellation is offered only for an affected, cancellable event', () => {
  assert.equal(canCancelForUnavailableVenue({ status: 'confirmed' }, FLAGGED), true)
  assert.equal(canCancelForUnavailableVenue({ status: 'confirmed' }, CLEAR), false)
  assert.equal(canCancelForUnavailableVenue({ status: 'cancelled' }, FLAGGED), false)
  assert.equal(canCancelForUnavailableVenue(
    { status: 'confirmed', cancellation_requested_at: '2026-10-30T00:00:00Z', cancellation_decision: null },
    FLAGGED,
  ), false)
  assert.equal(canCancelForUnavailableVenue(
    { status: 'confirmed', cancellation_requested_at: '2026-10-30T00:00:00Z', cancellation_decision: 'declined' },
    FLAGGED,
  ), true)
  assert.equal(canCancelForUnavailableVenue({ status: 'submitted' }, FLAGGED), false)
  for (const status of ['planning', 'pending_safety_check', 'preparation', 'safety_changes_requested']) {
    assert.equal(canCancelForUnavailableVenue({ status }, FLAGGED), true, status)
  }
  assert.equal(canCancelForUnavailableVenue({ status: 'confirmed' }, undefined), false)
})

// TC-FRONTEND-401
test('S-89 request body is trimmed and carries the version shown', () => {
  const form = { reason: '  Hall A closed  ', alternativesConsidered: ' Hall B too small\n' }

  assert.deepEqual(venueCancellationBody(form, { edit_version: 7 }), {
    reason: 'Hall A closed',
    alternatives_considered: 'Hall B too small',
    expected_version: 7,
  })
  assert.deepEqual(venueCancellationErrors(form), {})
  assert.deepEqual(venueCancellationErrors({ reason: '  ', alternativesConsidered: 'x' }), {
    reason: 'Enter why the event is being cancelled.',
  })
  assert.deepEqual(venueCancellationErrors({ reason: 'x', alternativesConsidered: '' }), {
    alternatives_considered: 'Describe the alternatives you discussed with the Organiser.',
  })
  assert.deepEqual(venueCancellationErrors({ reason: 'r'.repeat(1000), alternativesConsidered: 'a'.repeat(1000) }), {})
  assert.deepEqual(Object.keys(venueCancellationErrors({ reason: 'r'.repeat(1001), alternativesConsidered: 'a'.repeat(1001) })),
    ['reason', 'alternatives_considered'])
})

// TC-FRONTEND-402
test('S-89 every server outcome has a message in the product voice', () => {
  const stale = 'This event changed since you opened it. Reload and try again.'
  assert.deepEqual(venueCancellationErrorMessage(new ApiError(stale, 409)), { message: stale, retry: false })

  const unfinished = 'The event is cancelled, but its venue bookings were not released. Cancel again to finish.'
  assert.deepEqual(venueCancellationErrorMessage(new ApiError(unfinished, 502)), { message: unfinished, retry: true })

  assert.equal(venueCancellationErrorMessage(new ApiError('x', 404)).message, 'This event is no longer assigned to you.')

  const invalid = venueCancellationErrorMessage(new ApiError('x', 422, { reason: 'required', alternatives_considered: 'required' }))
  assert.equal(invalid.retry, false)
  assert.deepEqual(Object.keys(invalid.fieldErrors), ['reason', 'alternatives_considered'])

  assert.deepEqual(venueCancellationErrorMessage(new ApiError('x', 0)), {
    message: "We couldn't reach the server. Reload the event to see whether it was cancelled.",
    retry: false,
  })
})

// TC-FRONTEND-403
test('S-89 an unfinished cancellation is recognised after a reload', () => {
  assert.equal(venueCancellationIncomplete({ venue_cancelled_at: '2026-11-01T03:00:00Z', venue_cancellation_completed_at: null }), true)
  assert.equal(venueCancellationIncomplete({
    venue_cancelled_at: '2026-11-01T03:00:00Z', venue_cancellation_completed_at: '2026-11-01T03:01:00Z',
  }), false)
  assert.equal(venueCancellationIncomplete({ status: 'cancelled', cancellation_decision: 'approved' }), false)
})

// TC-FRONTEND-404
test('S-89 released bookings and the cancellation history read clearly', () => {
  assert.deepEqual(bookingStatusMeta('released'), { label: 'Released', color: '#4C5A70' })
  assert.deepEqual(bookingStatusMeta('replaced'), { label: 'Replaced', color: '#4C5A70' })

  const entry = {
    action: 'cancelled_venue_unavailable',
    category: 'review',
    actor_id: 'c',
    actor_role: 'event_coordinator',
    details: { reason: 'Hall A closed', alternatives_considered: 'Hall B too small' },
    occurred_at: '2026-11-01T03:00:00Z',
  }
  assert.equal(
    describeEntry(entry),
    'Cancelled the event as no alternative venue could be found: Hall A closed. Alternatives considered: Hall B too small',
  )
})
