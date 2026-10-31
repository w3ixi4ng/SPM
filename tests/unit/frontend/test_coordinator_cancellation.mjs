import assert from 'node:assert/strict'
import test from 'node:test'

import { hasPermission, PERMISSIONS } from '../../../frontend/src/lib/access.js'
import { ApiError } from '../../../frontend/src/lib/api.js'
import {
  canCancelForUnavailableVenue,
  cancelForUnavailableVenue,
  coordinatorCancellationErrorMessage,
  coordinatorCancellationNotice,
  coordinatorCancelledLabel,
  validateCancellationReason,
} from '../../../frontend/src/lib/eventRequests.js'

const flagged = (...flags) => flags.map((flag, i) => ({ id: `b${i}`, requires_alternative_arrangements: flag }))

// TC-FRONTEND-284
test('the Cancel event action is offered only for a live event with a flagged booking', () => {
  const cases = [
    ['planning', flagged(true, false), true],
    ['confirmed', flagged(true), true],
    ['planning', flagged(false, false), false],
    ['planning', [], false],
    ['cancelled', flagged(true), false],
    ['draft', flagged(true), false],
  ]
  for (const [status, bookings, expected] of cases) {
    assert.equal(canCancelForUnavailableVenue({ status }, bookings), expected, `${status} ${JSON.stringify(bookings)}`)
  }
  assert.equal(canCancelForUnavailableVenue(null, null), false)
  assert.equal(PERMISSIONS.CANCEL_ASSIGNED_EVENT, 'events:cancel_assigned')
  assert.equal(hasPermission('event_coordinator', PERMISSIONS.CANCEL_ASSIGNED_EVENT), true)
  for (const role of ['event_organiser', 'venue_staff', 'attendee']) {
    assert.equal(hasPermission(role, PERMISSIONS.CANCEL_ASSIGNED_EVENT), false, role)
  }
})

// TC-FRONTEND-285
test('the reason is required and capped at 1000 characters', () => {
  assert.equal(validateCancellationReason(''), 'Enter a reason for cancelling.')
  assert.equal(validateCancellationReason('   '), 'Enter a reason for cancelling.')
  assert.equal(validateCancellationReason('x'.repeat(1001)), 'Keep the reason to 1000 characters.')
  assert.equal(validateCancellationReason('V1 is closed for repairs.'), null)
})

test('cancelling posts the trimmed reason to the composite', async () => {
  const originalFetch = globalThis.fetch
  let seen
  globalThis.fetch = async (url, options = {}) => {
    seen = { url, options }
    return new Response(JSON.stringify({ status: 'cancelled' }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }
  try {
    assert.deepEqual(await cancelForUnavailableVenue('E 1', '  V1 is closed.  '), { status: 'cancelled' })
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.match(seen.url, /\/event-requests\/E%201\/coordinator-cancellation$/)
  assert.equal(seen.options.method, 'POST')
  assert.deepEqual(JSON.parse(seen.options.body), { reason: 'V1 is closed.' })
})

// TC-FRONTEND-286
test('the success notice says what was released and who was told', () => {
  assert.equal(
    coordinatorCancellationNotice({ released_bookings: 2, notified_attendees: 3 }),
    'Event cancelled. 2 venue bookings released. The Organiser and 3 Attendees were notified.',
  )
  assert.equal(
    coordinatorCancellationNotice({ released_bookings: 1, notified_attendees: 1 }),
    'Event cancelled. 1 venue booking released. The Organiser and 1 Attendee were notified.',
  )
  assert.equal(
    coordinatorCancellationNotice({ released_bookings: 0, notified_attendees: 0 }),
    'Event cancelled. No venue bookings to release. The Organiser was notified.',
  )
})

// TC-FRONTEND-287
test('errors say what happened and what to do next', () => {
  const refused = 'Only an event with a venue booking affected by an unavailable venue can be cancelled here.'
  const partial = "The event is cancelled, but its venue bookings couldn't be released. Cancel again to retry."
  assert.equal(coordinatorCancellationErrorMessage(new ApiError(refused, 409)), refused)
  assert.equal(coordinatorCancellationErrorMessage(new ApiError(partial, 502)), partial)
  assert.equal(
    coordinatorCancellationErrorMessage(new ApiError('x', 422)),
    'Enter a reason of up to 1000 characters. Nothing was changed.',
  )
  assert.equal(
    coordinatorCancellationErrorMessage(new ApiError('x', 404)),
    'This event was not found or is not assigned to you. Nothing was changed.',
  )
  assert.equal(
    coordinatorCancellationErrorMessage(new ApiError('x', 401)),
    'Your session has expired. Sign in again and retry. Nothing was changed.',
  )
  assert.equal(
    coordinatorCancellationErrorMessage(new ApiError('x', 0)),
    "We couldn't reach the server. Check your connection and try again. Nothing was changed.",
  )
})

// TC-FRONTEND-288
test('the cancelled event shows who cancelled it, when, and why', () => {
  assert.equal(
    coordinatorCancelledLabel({
      status: 'cancelled',
      coordinator_cancelled_at: '2026-11-01T06:30:00Z',
      coordinator_cancellation_reason: 'V1 is closed for repairs.',
    }),
    'You cancelled this event on 1 Nov 2026: V1 is closed for repairs.',
  )
  assert.equal(coordinatorCancelledLabel({ status: 'cancelled', coordinator_cancelled_at: null }), null)
})
