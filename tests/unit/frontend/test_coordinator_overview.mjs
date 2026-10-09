import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  listCoordinatorOverview,
  moveAssignmentInOverview,
  overviewErrorMessage,
} from '../../../frontend/src/lib/eventAssignments.js'


test('overview helper uses the credentialled read-only route', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ coordinators: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    await listCoordinatorOverview()
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/event-requests/coordinator-overview')
  assert.equal(calls[0].options.method ?? 'GET', 'GET')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[0].options.body, undefined)
  assert.match(overviewErrorMessage({ status: 401 }), /sign in again/i)
  assert.match(overviewErrorMessage({ status: 403 }), /only an Event Coordinator Lead/i)
  assert.match(overviewErrorMessage({ status: 502 }), /temporarily unavailable/i)
})


test('lead dashboard renders grouped assignments and required summaries', () => {
  const source = readFileSync(
    new URL('../../../frontend/src/pages/EventCoordinatorLeadDashboard.jsx', import.meta.url),
    'utf8',
  )

  for (const contract of [
    'Coordinator oversight',
    'active_assignment_count',
    'group.coordinator.name',
    'event.name',
    'event.status',
    'event.organiser?.name',
    'formatWindow(event)',
    'Current Coordinator:',
    'Unassigned event requests',
    'reassignEvent(',
  ]) {
    assert.match(source, new RegExp(contract.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
})


test('successful reassignment updates oversight groups and counts', () => {
  const former = { id: 'a', name: 'Alex' }
  const target = { id: 'b', name: 'Blair' }
  const groups = [
    {
      coordinator: former,
      active_assignment_count: 1,
      events: [{ id: 'event-1', name: 'Forum', assigned_coordinator_id: 'a' }],
    },
    { coordinator: target, active_assignment_count: 0, events: [] },
  ]

  const updated = moveAssignmentInOverview(
    groups,
    { id: 'event-1', assigned_coordinator_id: 'b', coordinator_assignment_version: 1 },
    target,
  )

  assert.equal(updated[0].active_assignment_count, 0)
  assert.deepEqual(updated[0].events, [])
  assert.equal(updated[1].active_assignment_count, 1)
  assert.equal(updated[1].events[0].coordinator.name, 'Blair')
  assert.equal(updated[1].events[0].coordinator_assignment_version, 1)
})


test('overview exposes loading empty and retryable error states', () => {
  const source = readFileSync(
    new URL('../../../frontend/src/pages/EventCoordinatorLeadDashboard.jsx', import.meta.url),
    'utf8',
  )

  for (const copy of [
    'Loading coordinator overview',
    'No Event Coordinators are available.',
    'No active events assigned.',
    'Try again',
  ]) {
    assert.match(source, new RegExp(copy.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
})
