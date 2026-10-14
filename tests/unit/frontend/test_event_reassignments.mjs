import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  listActiveAssignments,
  reassignEvent,
  reassignmentErrorMessage,
} from '../../../frontend/src/lib/eventAssignments.js'

// --- TC-FRONTEND-085 -----------------------------------------------------
test('reassignment helpers use versioned composite routes', async () => {
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
    await listActiveAssignments()
    await reassignEvent('event/1', 'coordinator-b', 'coordinator-a', 4)
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(({ url, options }) => [options.method ?? 'GET', url]), [
    ['GET', '/api/event-requests/assigned-active'],
    ['POST', '/api/event-requests/event%2F1/reassignment'],
  ])
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    coordinator_id: 'coordinator-b',
    expected_coordinator_id: 'coordinator-a',
    expected_assignment_version: 4,
  })
})

test('reassignment failures give the Lead actionable feedback', () => {
  assert.match(reassignmentErrorMessage({ status: 401 }), /sign in again/i)
  assert.match(reassignmentErrorMessage({ status: 403 }), /only an Event Coordinator Lead/i)
  assert.match(reassignmentErrorMessage({ status: 404 }), /no longer exists/i)
  assert.match(reassignmentErrorMessage({ status: 409 }), /reload/i)
  assert.match(reassignmentErrorMessage({ status: 422 }), /different valid Event Coordinator/i)
  assert.match(reassignmentErrorMessage({ status: 502 }), /retry/i)
})

// --- TC-FRONTEND-086 -----------------------------------------------------
test('lead dashboard presents and updates active assignments', () => {
  const source = readFileSync(
    new URL('../../../frontend/src/pages/EventCoordinatorLeadDashboard.jsx', import.meta.url),
    'utf8',
  )

  for (const contract of [
    'Coordinator oversight',
    'event.organiser?.name',
    'event.coordinator?.name',
    'listCoordinatorOverview()',
    'coordinator.id !== event.assigned_coordinator_id',
    'reassignEvent(',
    'event.coordinator_assignment_version',
    'moveAssignmentInOverview(',
    'No active events assigned.',
  ]) {
    assert.match(source, new RegExp(contract.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
})

// --- TC-FRONTEND-087 -----------------------------------------------------
test('reassignment uses the persistent in-app inbox', () => {
  const notificationSchemas = readFileSync(
    new URL('../../../backend/services/atomic/notifications/schemas.py', import.meta.url),
    'utf8',
  )
  const panel = readFileSync(
    new URL('../../../frontend/src/components/NotificationPanel.jsx', import.meta.url),
    'utf8',
  )

  assert.match(notificationSchemas, /event_reassignment/)
  assert.match(panel, /listNotifications\(\)/)
  assert.doesNotMatch(panel, /email|sms|push/i)
})
