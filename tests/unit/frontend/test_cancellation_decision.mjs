import assert from 'node:assert/strict'
import test from 'node:test'

import { hasPermission, PERMISSIONS, ROLE_ACCESS } from '../../../frontend/src/lib/access.js'
import { ApiError } from '../../../frontend/src/lib/api.js'
import {
  cancellationApprovalSummary,
  cancellationDecisionErrorMessage,
  cancellationDeclinedLabel,
  canDecideCancellation,
  canRequestCancellation,
  coordinatorCancellationTag,
  decideCancellation,
  eventStatusMeta,
  organiserCancellationTag,
  validateDeclineReason,
} from '../../../frontend/src/lib/eventRequests.js'

const T = '2026-10-11T09:00:00Z'
const PENDING = { status: 'planning', cancellation_requested_at: T, cancellation_decision: null }
const DECLINED = {
  status: 'planning',
  cancellation_requested_at: T,
  cancellation_decision: 'declined',
  cancellation_decision_reason: 'Move the date instead',
  cancellation_decided_at: '2026-10-12T09:00:00Z',
}
const APPROVED = { status: 'cancelled', cancellation_requested_at: T, cancellation_decision: 'approved' }
const NONE = { status: 'planning', cancellation_requested_at: null }

// --- TC-FRONTEND-107 -------------------------------------------------------
test('who sees what about a cancellation request', () => {
  assert.deepEqual(
    [PENDING, DECLINED, APPROVED, NONE].map(canDecideCancellation),
    [true, false, false, false],
  )
  assert.deepEqual(
    [PENDING, DECLINED, APPROVED, NONE].map(coordinatorCancellationTag),
    ['Cancellation requested', null, null, null],
  )
  assert.equal(eventStatusMeta('cancelled').label, 'Cancelled')
  assert.deepEqual(
    [PENDING, DECLINED, APPROVED, NONE].map(organiserCancellationTag),
    ['Cancellation requested', 'Cancellation declined', null, null],
  )
  assert.equal(cancellationDeclinedLabel(DECLINED), 'Cancellation declined on 12 Oct 2026')
  assert.equal(cancellationDeclinedLabel(PENDING), null)
  assert.deepEqual(
    [PENDING, DECLINED, APPROVED, NONE].map(canRequestCancellation),
    [false, true, false, true],
  )
})

test('only event coordinators may decide cancellation requests, as in authorization.py', () => {
  assert.equal(PERMISSIONS.DECIDE_EVENT_CANCELLATION, 'events:decide_cancellation')
  for (const role of Object.keys(ROLE_ACCESS)) {
    assert.equal(
      hasPermission(role, PERMISSIONS.DECIDE_EVENT_CANCELLATION),
      role === 'event_coordinator',
      role,
    )
  }
})

// --- TC-FRONTEND-108 -------------------------------------------------------
test('the decision posts through Kong', async () => {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ id: 'e1' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  try {
    await decideCancellation('e 1/2', { decision: 'approved' })
    await decideCancellation('e 1/2', { decision: 'declined', reason: '  Move the date  ' })
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(({ url, options }) => [url, options.method, options.credentials]), [
    ['/api/event-requests/e%201%2F2/cancellation-decision', 'POST', 'include'],
    ['/api/event-requests/e%201%2F2/cancellation-decision', 'POST', 'include'],
  ])
  assert.deepEqual(JSON.parse(calls[0].options.body), { decision: 'approved' })
  assert.deepEqual(JSON.parse(calls[1].options.body), { decision: 'declined', reason: 'Move the date' })
})

test('a decline needs a reason of at most 1000 characters', () => {
  assert.equal(validateDeclineReason(''), 'Enter a reason for declining.')
  assert.equal(validateDeclineReason('   '), 'Enter a reason for declining.')
  assert.equal(validateDeclineReason('x'.repeat(1001)), 'Keep the reason to 1000 characters.')
  assert.equal(validateDeclineReason('ok'), null)
})

test('every failure says what changed', () => {
  const decided = 'This cancellation request has already been decided.'
  const partial = 'The event is cancelled, but its venue bookings were not released. Approve again to release them.'
  assert.equal(cancellationDecisionErrorMessage(new ApiError(decided, 409)), decided)
  assert.equal(cancellationDecisionErrorMessage(new ApiError(partial, 502)), partial)
  for (const status of [404, 500, 0]) {
    assert.match(cancellationDecisionErrorMessage(new ApiError('x', status)), /Nothing was changed\.$/, String(status))
  }
})

test('the approval summary names what is released', () => {
  const equipment = ' Equipment reserved for this event is freed.'
  assert.equal(cancellationApprovalSummary(0), `No venue bookings to release.${equipment}`)
  assert.equal(cancellationApprovalSummary(1), `1 venue booking will be removed and its time freed.${equipment}`)
  assert.equal(cancellationApprovalSummary(2), `2 venue bookings will be removed and their times freed.${equipment}`)
})
