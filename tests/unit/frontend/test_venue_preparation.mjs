import assert from 'node:assert/strict'
import test from 'node:test'

import {
  listVenuePreparationBookings,
  updateVenuePreparation,
  venuePreparationErrorMessage,
  venuePreparationLabel,
} from '../../../frontend/src/lib/venueBookings.js'

test('venue preparation calls use the gateway and optimistic version', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return { ok: true, status: 200, json: async () => [] }
  }
  try {
    await listVenuePreparationBookings()
    await updateVenuePreparation('booking 1/2', 'ready', 3)
    assert.equal(calls[0].url, '/api/venue-bookings/preparation')
    assert.equal(calls[1].url, '/api/venue-bookings/booking%201%2F2/preparation')
    assert.equal(calls[1].options.method, 'PUT')
    assert.deepEqual(JSON.parse(calls[1].options.body), { status: 'ready', expected_version: 3 })
    assert.ok(calls.every(({ options }) => options.credentials === 'include'))
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('venue preparation labels and failures stay specific', () => {
  assert.equal(venuePreparationLabel('not_started'), 'Not Started')
  assert.equal(venuePreparationLabel('in_progress'), 'In Progress')
  assert.equal(venuePreparationLabel('ready'), 'Ready')
  assert.equal(venuePreparationErrorMessage({ status: 409, message: 'Reload first' }), 'Reload first')
  assert.match(venuePreparationErrorMessage({ status: 500 }), /couldn't update/)
})
