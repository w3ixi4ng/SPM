import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  listLeadReassignmentRequests,
  listMyReassignmentRequests,
  reassignmentRequestError,
  requestReassignment,
} from '../../../frontend/src/lib/reassignmentRequests.js'

test('S-88 requests use authenticated composite routes and only send a reason', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await requestReassignment('event/1', '  Cannot cover event  ')
    await listMyReassignmentRequests()
    await listLeadReassignmentRequests()
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.deepEqual(calls.map(({ url, options }) => [options.method ?? 'GET', url]), [
    ['POST', '/api/event-requests/event%2F1/reassignment-request'],
    ['GET', '/api/event-requests/reassignment-requests/mine'],
    ['GET', '/api/event-requests/reassignment-requests/lead'],
  ])
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
  assert.deepEqual(JSON.parse(calls[0].options.body), { reason: 'Cannot cover event' })
})

test('S-88 request errors and dashboard states are usable', () => {
  assert.match(reassignmentRequestError({ status: 401 }), /sign in/i)
  assert.match(reassignmentRequestError({ status: 409, message: 'Already pending' }), /already pending/i)
  assert.match(reassignmentRequestError({ status: 422 }), /reason/i)
  assert.match(reassignmentRequestError({ status: 502 }), /try again/i)

  const coordinator = readFileSync(new URL('../../../frontend/src/components/ReassignmentRequestPanel.jsx', import.meta.url), 'utf8')
  const lead = readFileSync(new URL('../../../frontend/src/pages/EventCoordinatorLeadDashboard.jsx', import.meta.url), 'utf8')
  for (const text of ['Loading reassignment requests', 'No reassignment requests yet', 'Pending', 'Actioned', 'role="alert"']) {
    assert.ok(coordinator.includes(text))
  }
  assert.ok(coordinator.includes('if (!reason.trim())'))
  for (const text of ['No reassignment requests in your scope', 'Use the reassignment control', 'loadRequests()', 'reassignEvent(']) {
    assert.ok(lead.includes(text))
  }
})
