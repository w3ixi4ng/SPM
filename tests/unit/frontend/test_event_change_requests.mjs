import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CHANGE_REQUEST_STATUSES, changeValues, changedFields, durationMinutes,
  endFromDuration, equipmentSnapshot, getEventChangeRequests,
  submitEventChangeRequest,
} from '../../../frontend/src/lib/eventChangeRequests.js'

const accepted = {
  start_date: '2026-11-18', start_time: '09:00:00',
  end_date: '2026-11-18', end_time: '12:00:00',
  expected_attendance: 120, venue: 'Main Hall', special_requirements: null,
  room_layout: 'theatre', required_facilities: ['projector'], required_accessibility: [],
}
const projector = '22222222-2222-4222-8222-222222222222'

test('S-59 action is available in all seven confirmed statuses', () => {
  for (const status of ['submitted', 'under_review', 'returned', 'planning', 'pending_safety_check', 'confirmed', 'preparation']) {
    assert.equal(CHANGE_REQUEST_STATUSES.has(status), true)
  }
  for (const status of ['draft', 'completed', 'cancelled', 'rejected', 'safety_rejected']) {
    assert.equal(CHANGE_REQUEST_STATUSES.has(status), false)
  }
})

test('S-59 comparison normalizes time, whitespace and unordered options', () => {
  const proposed = {
    ...accepted, start_time: '09:00', venue: ' Main Hall ',
    required_facilities: ['projector', 'projector'],
  }
  assert.deepEqual(changedFields(accepted, proposed, [], []), [])
  assert.equal(changeValues(proposed).venue, 'Main Hall')
  assert.deepEqual(changedFields(accepted, { ...proposed, expected_attendance: 150 }, [], []), ['expected_attendance'])
})

test('S-59 equipment and duration changes are explicit', () => {
  const before = [{ equipment_item_id: projector, required_quantity: 2 }]
  const after = [{ equipment_item_id: projector, required_quantity: 3 }]
  assert.deepEqual(changedFields(accepted, accepted, before, after), ['equipment'])
  assert.deepEqual(equipmentSnapshot(after), after)
  assert.equal(durationMinutes(accepted), 180)
  assert.deepEqual(endFromDuration(accepted, 240), { end_date: '2026-11-18', end_time: '13:00' })
})

test('S-59 API calls use authenticated composite routes and send only proposal fields', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return { ok: true, status: options?.method === 'POST' ? 201 : 200, json: async () => ({ status: 'pending' }) }
  }
  try {
    await getEventChangeRequests('event-id')
    await submitEventChangeRequest('event-id', accepted, [{ equipment_item_id: projector, required_quantity: 3 }])
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.equal(calls[0].url, '/api/event-requests/event-id/change-requests')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[1].options.method, 'POST')
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    values: accepted,
    equipment: [{ equipment_item_id: projector, required_quantity: 3 }],
  })
  assert.equal('organiser_id' in JSON.parse(calls[1].options.body), false)
})
