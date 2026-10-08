import assert from 'node:assert/strict'
import test from 'node:test'

import {
  assignedEventWork,
  canRequestTechnicalSupport,
  getTechnicalSupportAssignment,
  getTechnicalSupportEvent,
  listTechnicalSupportEvents,
  requestTechnicalSupportAssignment,
  technicalSupportAssignmentErrorMessage,
  technicalSupportWorkErrorMessage,
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

// --- TC-FRONTEND-081 -----------------------------------------------------
test('assigned support event reads use authenticated gateway routes without a staff id', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify([]), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    await listTechnicalSupportEvents()
    await getTechnicalSupportEvent('event/support 1')
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(({ url }) => url), [
    '/api/events/support-assigned',
    '/api/events/support-assigned/event%2Fsupport%201',
  ])
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
  assert.equal(calls.every(({ url }) => !url.includes('staff_id')), true)
})

// --- TC-FRONTEND-082 -----------------------------------------------------
test('assigned event work groups only matching equipment under active events', () => {
  const events = [
    { id: 'event-a', name: 'Sound check', status: 'planning' },
    { id: 'event-b', name: 'Awards night', status: 'confirmed' },
    { id: 'event-c', name: 'Old event', status: 'cancelled' },
  ]
  const requirements = [
    { id: 'req-a', event_id: 'event-a', equipment: { type: 'Microphone' }, required_quantity: 2 },
    { id: 'req-b', event_id: 'event-b', equipment: { type: 'Projector' }, required_quantity: 1 },
    { id: 'req-c', event_id: 'event-c', equipment: { type: 'Old speaker' }, required_quantity: 3 },
    { id: 'req-other', event_id: 'event-other', equipment: { type: 'Leaked item' }, required_quantity: 9 },
  ]

  const work = assignedEventWork(events, requirements)

  assert.deepEqual(work.map(({ id }) => id), ['event-a', 'event-b'])
  assert.deepEqual(work[0].equipment_requirements, [requirements[0]])
  assert.deepEqual(work[1].equipment_requirements, [requirements[1]])
})

// --- TC-FRONTEND-083 -----------------------------------------------------
test('assigned event failures stay distinct from an empty workload', () => {
  assert.match(technicalSupportWorkErrorMessage({ status: 401 }), /sign in again/i)
  assert.match(technicalSupportWorkErrorMessage({ status: 403 }), /not permitted/i)
  assert.match(technicalSupportWorkErrorMessage({ status: 404 }), /no longer assigned/i)
  assert.match(technicalSupportWorkErrorMessage({ status: 502 }), /temporarily unavailable/i)
  assert.deepEqual(assignedEventWork([], []), [])
})
