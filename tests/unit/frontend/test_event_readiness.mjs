import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildEventReadiness,
  loadEventReadiness,
} from '../../../frontend/src/lib/eventReadiness.js'

test('readiness derives every implemented area from its owning data', () => {
  // TC-FRONTEND-119: a confirmed event, so preparation counts (S-26 AC2).
  const event = { status: 'confirmed', technical_signoff_decision: 'approved', equipment_preparation_status: 'ready' }
  const readiness = buildEventReadiness(event, [
    { status: 'pending' },
    { id: 'b1', status: 'confirmed', venue_name: 'Hall A', venue_preparation_status: 'ready' },
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
    { status: 'confirmed', technical_signoff_decision: 'approved', equipment_preparation_status: 'in_progress' },
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
      ? [{ id: 'b1', status: 'confirmed', venue_name: 'Hall A', venue_preparation_status: 'ready' }]
      : [{ required_quantity: 4 }]
    return { ok: true, status: 200, json: async () => body }
  }

  try {
    const result = await loadEventReadiness('event 1/2', {
      status: 'confirmed',
      technical_signoff_decision: 'approved',
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

test('venue readiness lists every confirmed venue and waits for all to be ready', () => {
  const readiness = buildEventReadiness({ status: 'confirmed', technical_signoff_decision: 'approved', equipment_preparation_status: 'ready' }, [
    { id: 'a', status: 'confirmed', venue_name: 'Hall A', venue_preparation_status: 'ready' },
    { id: 'b', status: 'confirmed', venue_name: 'Room B', venue_preparation_status: 'in_progress' },
    { id: 'c', status: 'rejected', venue_name: 'Room C', venue_preparation_status: 'ready' },
  ], [{ required_quantity: 1 }])
  const venue = readiness.areas[0]
  assert.equal(venue.state, 'outstanding')
  assert.equal(venue.detail, '1 of 2 confirmed venues Ready')
  assert.deepEqual(venue.items.map(({ label, status }) => [label, status]), [
    ['Hall A', 'Ready'], ['Room B', 'In Progress'],
  ])
})

// TC-FRONTEND-425 -- S-26 AC2: before the Safety Officer's approval,
// preparation can't be updated, so it can't hold readiness Outstanding.
test('technical support readiness counts preparation only after safety approval', () => {
  const venue = [{ id: 'b1', status: 'confirmed', venue_name: 'Hall A', venue_preparation_status: 'ready' }]
  const support = (event) => buildEventReadiness(event, venue, [{ required_quantity: 1 }]).areas
    .find(({ id }) => id === 'technical_support')
  const pick = ({ state, detail }) => ({ state, detail })

  assert.deepEqual(pick(support({
    status: 'planning', technical_signoff_decision: 'approved', equipment_preparation_status: 'not_started',
  })), { state: 'complete', detail: 'Equipment preparation starts after the safety check' })
  assert.deepEqual(pick(support({
    status: 'planning', technical_signoff_decision: null, equipment_preparation_status: 'not_started',
  })), { state: 'outstanding', detail: 'Technical Support has not approved the equipment arrangements' })
  assert.deepEqual(pick(support({
    status: 'confirmed', technical_signoff_decision: 'approved', equipment_preparation_status: 'in_progress',
  })), { state: 'outstanding', detail: 'Equipment preparation is In Progress' })
  assert.deepEqual(pick(support({
    status: 'confirmed', technical_signoff_decision: 'approved', equipment_preparation_status: 'ready',
  })), { state: 'complete', detail: 'Equipment preparation is Ready' })
})
