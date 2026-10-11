import assert from 'node:assert/strict'
import test from 'node:test'

import { hasPermission, PERMISSIONS, ROLE_ACCESS } from '../../../frontend/src/lib/access.js'
import { ApiError } from '../../../frontend/src/lib/api.js'
import {
  cancellationErrorMessage,
  cancellationRequestedLabel,
  cancellationSentMessage,
  canRequestCancellation,
  organiserStatusMeta,
  requestEventCancellation,
  validateCancellationReason,
} from '../../../frontend/src/lib/eventRequests.js'

const ELIGIBLE = ['submitted', 'under_review', 'planning', 'confirmed', 'preparation', 'safety_changes_requested']
const INELIGIBLE = ['draft', 'returned', 'rejected', 'cancelled', 'safety_rejected']

// --- TC-FRONTEND-104 -------------------------------------------------------
test('cancellation is offered only for an eligible event without a request', () => {
  for (const status of ELIGIBLE) {
    assert.equal(canRequestCancellation({ status, cancellation_requested_at: null }), true, status)
  }
  for (const status of INELIGIBLE) {
    assert.equal(canRequestCancellation({ status, cancellation_requested_at: null }), false, status)
  }

  const requested = { status: 'planning', cancellation_requested_at: '2026-10-11T09:00:00Z' }
  assert.equal(canRequestCancellation(requested), false)
  // Never shown as cancelled: the status label is the event's own.
  assert.equal(organiserStatusMeta(requested.status).label, 'Planning')
  assert.equal(cancellationRequestedLabel(requested), 'Cancellation requested on 11 Oct 2026')
  assert.equal(cancellationRequestedLabel({ status: 'planning', cancellation_requested_at: null }), null)
  assert.equal(
    cancellationSentMessage('planning'),
    'Cancellation request sent. Your event stays in planning until it has been reviewed.',
  )
})

test('only event organisers may request cancellation, as in authorization.py', () => {
  assert.equal(PERMISSIONS.REQUEST_EVENT_CANCELLATION, 'events:request_cancellation')
  for (const role of Object.keys(ROLE_ACCESS)) {
    assert.equal(
      hasPermission(role, PERMISSIONS.REQUEST_EVENT_CANCELLATION),
      role === 'event_organiser',
      role,
    )
  }
})

// --- TC-FRONTEND-105 -------------------------------------------------------
test('the request posts the trimmed reason through Kong', async () => {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ id: 'e1', status: 'planning' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  try {
    await requestEventCancellation('e 1/2', '  Keynote speaker withdrew  ')
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(calls.length, 1)
  const [{ url, options }] = calls
  assert.equal(url, '/api/events/e%201%2F2/cancellation-request')
  assert.equal(options.method, 'POST')
  assert.equal(options.credentials, 'include')
  assert.deepEqual(JSON.parse(options.body), { reason: 'Keynote speaker withdrew' })
})

test('the reason is required and at most 1000 characters', () => {
  assert.equal(validateCancellationReason(''), 'Enter a reason for cancelling.')
  assert.equal(validateCancellationReason('   '), 'Enter a reason for cancelling.')
  assert.equal(validateCancellationReason('x'.repeat(1001)), 'Keep the reason to 1000 characters.')
  assert.equal(validateCancellationReason('ok'), null)
})

test('every failure says the event has not changed', () => {
  const conflict = cancellationErrorMessage(
    new ApiError('A cancellation request has already been sent for this event.', 409),
  )
  assert.match(conflict, /^A cancellation request has already been sent for this event\./)

  const messages = [
    conflict,
    cancellationErrorMessage(new ApiError('invalid', 422)),
    cancellationErrorMessage(new ApiError('Event not found', 404)),
    cancellationErrorMessage(new ApiError('Event storage unavailable', 500)),
    cancellationErrorMessage(new ApiError("We couldn't reach the server.", 0)),
  ]
  for (const message of messages) {
    assert.match(message, /Your event has not changed\.$/, message)
  }
  assert.match(messages[3], /Try again/)
  assert.match(messages[4], /try again/)
})
