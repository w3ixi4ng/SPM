import assert from 'node:assert/strict'
import test from 'node:test'
import { getVenue, updateVenue, venueToEditForm, validateVenueEditForm, venueUpdateErrorMessage } from '../../../frontend/src/lib/venues.js'
import { PERMISSIONS, ROLE_ACCESS, hasPermission } from '../../../frontend/src/lib/access.js'

// TC-FRONTEND-036
test('only venue staff have edit permission, including unknown-role denial', () => {
  for (const role of [...Object.keys(ROLE_ACCESS), 'unknown', undefined]) {
    assert.equal(hasPermission(role, PERMISSIONS.UPDATE_VENUE), role === 'venue_staff')
  }
})

test('edit form loads only editable values and copies arrays', () => {
  const venue = { name: 'Hall', location: 'Block A', capacity: 250, facilities: ['projector'], accessibility: [] }
  const form = venueToEditForm(venue)
  assert.deepEqual(form, { location: 'Block A', capacity: '250', facilities: ['projector'], accessibility: [] })
  form.facilities.push('wifi')
  assert.deepEqual(venue.facilities, ['projector'])
})

test('edit validation does not require protected create fields', () => {
  assert.deepEqual(validateVenueEditForm({ location: 'Block B', capacity: '100' }), {})
  for (const capacity of ['', '0', '-1', '1.5', 'abc', '2147483648']) {
    assert.ok(validateVenueEditForm({ location: 'Block B', capacity }).capacity)
  }
  assert.ok(validateVenueEditForm({ location: ' ', capacity: '1' }).location)
})

test('load and PATCH use cookies and only four editable fields', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options })
    return { ok: true, status: 200, json: async () => ({ capacity: 100 }) }
  })
  await getVenue('venue-id')
  assert.deepEqual(await updateVenue('venue-id', { location: ' Block B ', capacity: '100', facilities: [], accessibility: [], name: 'Forbidden', operating_hours: [] }), { capacity: 100 })
  assert.equal(calls[0].url, '/api/venues/venue-id')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[1].options.method, 'PATCH')
  assert.equal(calls[1].options.credentials, 'include')
  assert.deepEqual(JSON.parse(calls[1].options.body), { location: 'Block B', capacity: 100, facilities: [], accessibility: [] })
})

test('update failures remain failures and have safe actionable messages', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 403, json: async () => ({ detail: 'Permission denied' }) }))
  await assert.rejects(updateVenue('id', { location: 'Block B', capacity: '100', facilities: [], accessibility: [] }), { status: 403 })
  for (const status of [0, 401, 403, 404, 422, 500]) {
    const message = venueUpdateErrorMessage({ status, message: 'private detail' })
    assert.ok(message.length > 0)
    assert.ok(!message.includes('private detail'))
  }
})
