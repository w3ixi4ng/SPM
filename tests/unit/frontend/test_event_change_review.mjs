import assert from 'node:assert/strict'
import test from 'node:test'

import {
  acceptEventChange, getEventChangeReview, rejectEventChange, resolveEventChangeImpact,
} from '../../../frontend/src/lib/eventChangeRequests.js'


test('S-60 review and decisions use authenticated scoped routes with explicit evidence', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ status: 'pending' }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }
  try {
    await getEventChangeReview('event/1', 'request/2')
    await acceptEventChange('event/1', 'request/2', {
      expected_event_updated_at: '2026-10-31T09:00:00Z', impact_ids: ['venue:B1:capacity'],
    })
    await rejectEventChange('event/1', 'request/2', 'Venue unavailable')
    await resolveEventChangeImpact('event/1', 'request/2', 'venue:B1:capacity', {
      expected_impact_version: 1, action: 'Replacement approved', evidence: { booking_id: 'B3' },
    })
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.deepEqual(calls.map(({ url, options }) => [url, options.method]), [
    ['/api/event-requests/event%2F1/change-requests/request%2F2/review', undefined],
    ['/api/event-requests/event%2F1/change-requests/request%2F2/accept', 'POST'],
    ['/api/event-requests/event%2F1/change-requests/request%2F2/reject', 'POST'],
    ['/api/event-requests/event%2F1/change-requests/request%2F2/impacts/venue%3AB1%3Acapacity/resolve', 'POST'],
  ])
  assert.ok(calls.every(({ options }) => options.credentials === 'include'))
  assert.deepEqual(JSON.parse(calls[1].options.body).impact_ids, ['venue:B1:capacity'])
  assert.deepEqual(JSON.parse(calls[3].options.body).evidence, { booking_id: 'B3' })
})


test('S-60 API errors preserve stale and incomplete status for the review UI', async () => {
  const originalFetch = globalThis.fetch
  try {
    for (const status of [409, 422, 502]) {
      globalThis.fetch = async () => new Response(JSON.stringify({ detail: `Simulated ${status}` }), {
        status, headers: { 'Content-Type': 'application/json' },
      })
      await assert.rejects(
        acceptEventChange('E', 'R', { expected_event_updated_at: '2026-10-31T09:00:00Z', impact_ids: [] }),
        (error) => error.status === status && error.message === `Simulated ${status}`,
      )
    }
  } finally {
    globalThis.fetch = originalFetch
  }
})
