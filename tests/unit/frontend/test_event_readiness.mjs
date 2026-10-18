import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildEventReadiness,
  loadEventReadiness,
} from '../../../frontend/src/lib/eventReadiness.js'

test('readiness derives every implemented area from its owning data', () => {
  const event = { equipment_preparation_status: 'ready' }
  const readiness = buildEventReadiness(event, [
    { status: 'pending' },
    { status: 'confirmed' },
  ], [{ required_quantity: 2 }])

  assert.deepEqual(readiness.areas.map(({ id, state }) => [id, state]), [
    ['venue', 'complete'],
    ['equipment', 'complete'],
    ['technical_support', 'complete'],
    ['programme', 'unavailable'],
    ['registration', 'unavailable'],
  ])
  assert.deepEqual(readiness.summary, { complete: 3, available: 3, ready: true })
})

test('readiness stays outstanding until its underlying data is complete', () => {
  const readiness = buildEventReadiness(
    { equipment_preparation_status: 'in_progress' },
    [{ status: 'held' }],
    [],
  )

  assert.deepEqual(readiness.areas.slice(0, 3).map(({ state }) => state), [
    'outstanding',
    'outstanding',
    'outstanding',
  ])
  assert.deepEqual(readiness.summary, { complete: 0, available: 3, ready: false })
})

test('readiness loads fresh venue and equipment data through Kong', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    const body = url.startsWith('/api/venue-bookings')
      ? [{ status: 'confirmed' }]
      : [{ required_quantity: 4 }]
    return { ok: true, status: 200, json: async () => body }
  }

  try {
    const result = await loadEventReadiness('event 1/2', {
      equipment_preparation_status: 'ready',
    })
    assert.equal(result.summary.ready, true)
    assert.deepEqual(calls.map(({ url }) => url), [
      '/api/venue-bookings?event_id=event%201%2F2',
      '/api/equipment-requirements?event_id=event%201%2F2',
    ])
    assert.ok(calls.every(({ options }) => options.credentials === 'include'))
  } finally {
    globalThis.fetch = originalFetch
  }
})
