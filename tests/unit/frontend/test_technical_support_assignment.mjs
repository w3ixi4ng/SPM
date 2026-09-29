import assert from 'node:assert/strict'
import test from 'node:test'

import {
  canRequestTechnicalSupport,
  getTechnicalSupportAssignment,
  requestTechnicalSupportAssignment,
  technicalSupportAssignmentErrorMessage,
} from '../../../frontend/src/lib/technicalSupportAssignments.js'

// --- TC-FRONTEND-051 -----------------------------------------------------
test('support assignment uses the explicit authenticated action', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ assignment_state: 'assigned' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    await getTechnicalSupportAssignment('event/1')
    await requestTechnicalSupportAssignment('event/1', '  Sound check  ')
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(({ url, options }) => [options.method ?? 'GET', url]), [
    ['GET', '/api/event-requests/event%2F1/technical-support-assignment'],
    ['POST', '/api/event-requests/event%2F1/technical-support-assignment'],
  ])
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
  assert.deepEqual(JSON.parse(calls[1].options.body), { support_details: 'Sound check' })
})

// --- TC-FRONTEND-052 -----------------------------------------------------
test('support assignment controls and states follow the event', () => {
  assert.equal(canRequestTechnicalSupport('planning'), true)
  for (const status of ['draft', 'submitted', 'returned', 'rejected', 'confirmed', 'completed', 'cancelled']) {
    assert.equal(canRequestTechnicalSupport(status), false, status)
  }
})

// --- TC-FRONTEND-053 -----------------------------------------------------
test('support assignment failures are safe and actionable', () => {
  assert.match(technicalSupportAssignmentErrorMessage({ status: 401 }), /sign in again/i)
  assert.match(technicalSupportAssignmentErrorMessage({ status: 403 }), /not permitted/i)
  assert.match(technicalSupportAssignmentErrorMessage({ status: 404 }), /not found/i)
  assert.match(technicalSupportAssignmentErrorMessage({ status: 409, message: 'Event is no longer planning' }), /no longer planning/i)
  assert.match(technicalSupportAssignmentErrorMessage({ status: 500 }), /not been saved/i)
})
