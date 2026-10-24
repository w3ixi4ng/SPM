import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  assignEventRequest,
  assignmentErrorMessage,
  coordinatorOptionLabel,
  listAssignmentCoordinators,
  listUnassignedEventRequests,
} from '../../../frontend/src/lib/eventAssignments.js'

// --- TC-FRONTEND-093 -----------------------------------------------------
test('lead assignment helpers use the composite routes through Kong', async () => {
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
    await listUnassignedEventRequests()
    await listAssignmentCoordinators()
    await assignEventRequest('event/1', 'coordinator-1')
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(({ url, options }) => [options.method ?? 'GET', url]), [
    ['GET', '/api/event-requests/unassigned'],
    ['GET', '/api/event-requests/coordinators'],
    ['POST', '/api/event-requests/event%2F1/assignment'],
  ])
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
  assert.deepEqual(JSON.parse(calls[2].options.body), { coordinator_id: 'coordinator-1' })
})

test('coordinator choices use Auth email when profile names overlap', () => {
  assert.equal(
    coordinatorOptionLabel({ name: 'E2E Tester', email: 'spm-e2e-123@example.com' }),
    'spm-e2e-123@example.com',
  )
  assert.equal(coordinatorOptionLabel({ name: 'Coordinator', email: null }), 'Coordinator')
})

test('assignment failures give the lead actionable feedback', () => {
  assert.match(assignmentErrorMessage({ status: 401 }), /sign in again/i)
  assert.match(assignmentErrorMessage({ status: 403 }), /only an Event Coordinator Lead/i)
  assert.match(assignmentErrorMessage({ status: 404 }), /no longer exists/i)
  assert.equal(
    assignmentErrorMessage({ status: 409, message: 'Already assigned' }),
    'Already assigned',
  )
  assert.match(assignmentErrorMessage({ status: 422 }), /valid Event Coordinator/i)
  assert.match(assignmentErrorMessage({ status: 502 }), /retry/i)
})

// --- TC-FRONTEND-094 -----------------------------------------------------
test('lead queue presents the required details and removes an assigned card', () => {
  const source = readFileSync(
    new URL('../../../frontend/src/pages/EventCoordinatorLeadDashboard.jsx', import.meta.url),
    'utf8',
  )

  for (const contract of [
    'event.name',
    'event.start_date',
    'event.start_time',
    'event.end_date',
    'event.end_time',
    'event.expected_attendance',
    'event.organiser?.name',
    'state.coordinators.map',
    'assignEventRequest(event.id, coordinatorId)',
    'current.events.filter((item) => item.id !== event.id)',
    'No event requests are waiting for assignment.',
  ]) {
    assert.match(source, new RegExp(contract.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
})
