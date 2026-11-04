import assert from 'node:assert/strict'
import test from 'node:test'
import { getVenue, updateVenue, venueFieldErrorsToForm, venueToEditForm, validateVenueEditForm, validateVenueForm, venueUpdateErrorMessage } from '../../../frontend/src/lib/venues.js'
import { outsideHoursWarning } from '../../../frontend/src/lib/venueBookings.js'
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
  // S-75: a venue saved before setup/turnaround existed loads them as 0.
  // S-28 reopened: opening hours are editable too; none here, so all closed.
  assert.deepEqual(form, { location: 'Block A', capacity: '250', facilities: ['projector'], accessibility: [], setupHours: '0', setupMins: '0', turnaroundHours: '0', turnaroundMins: '0', hours: {} })
  form.facilities.push('wifi')
  assert.deepEqual(venue.facilities, ['projector'])
})

test('edit validation does not require protected create fields', () => {
  // S-28 reopened: opening hours are required on edit as on create.
  const times = { setupHours: '0', setupMins: '0', turnaroundHours: '0', turnaroundMins: '0', hours: { mon: { open: '09:00', close: '18:00' } } }
  assert.deepEqual(validateVenueEditForm({ location: 'Block B', capacity: '100', ...times }), {})
  for (const capacity of ['', '0', '-1', '1.5', 'abc', '2147483648']) {
    assert.ok(validateVenueEditForm({ location: 'Block B', capacity, ...times }).capacity)
  }
  assert.ok(validateVenueEditForm({ location: ' ', capacity: '1', ...times }).location)
})

test('load and PATCH use cookies and only the editable fields', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options })
    return { ok: true, status: 200, json: async () => ({ capacity: 100 }) }
  })
  await getVenue('venue-id')
  assert.deepEqual(await updateVenue('venue-id', { location: ' Block B ', capacity: '100', facilities: [], accessibility: [], setupHours: '0', setupMins: '30', turnaroundHours: '0', turnaroundMins: '45', hours: { thu: { open: '10:00', close: '16:00' } }, name: 'Forbidden', roomLayouts: ['banquet'] }), { capacity: 100 })
  assert.equal(calls[0].url, '/api/venues/venue-id')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[1].options.method, 'PATCH')
  assert.equal(calls[1].options.credentials, 'include')
  // S-75 added setup and turnaround to the editable fields; S-28 reopened,
  // opening hours. Never the name or room layouts.
  assert.deepEqual(JSON.parse(calls[1].options.body), { location: 'Block B', capacity: 100, facilities: [], accessibility: [], setup_minutes: 30, turnaround_minutes: 45, operating_hours: [{ day: 'thu', open: '10:00', close: '16:00' }] })
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

// --- S-28 reopened: Venue Staff edit opening hours -------------------------

const TIMES = { setupHours: '0', setupMins: '0', turnaroundHours: '0', turnaroundMins: '0' }
const HOURS_VENUE = {
  name: 'Hall', location: 'Block A', capacity: 250, facilities: [], accessibility: [],
  operating_hours: [{ day: 'mon', open: '09:00:00', close: '18:00:00' }, { day: 'thu', open: '08:00:00', close: '20:00:00' }],
}

// --- TC-FRONTEND-410 -------------------------------------------------------
test("the edit form loads the venue's opening hours", () => {
  const form = venueToEditForm(HOURS_VENUE)
  assert.deepEqual(form.hours, { mon: { open: '09:00', close: '18:00' }, thu: { open: '08:00', close: '20:00' } })
  form.hours.mon.open = '11:00'
  assert.equal(HOURS_VENUE.operating_hours[0].open, '09:00:00')
})

// --- TC-FRONTEND-411 -------------------------------------------------------
test('edited opening hours are validated as on create', () => {
  const base = { location: 'Block B', capacity: '100', ...TIMES }
  const create = (hours) => validateVenueForm({ name: 'Hall', roomLayouts: ['theatre'], ...base, hours })
  const none = validateVenueEditForm({ ...base, hours: {} })
  assert.ok(none.operating_hours)
  assert.equal(none.operating_hours, create({}).operating_hours)
  const backwards = { mon: { open: '18:00', close: '09:00' } }
  assert.ok(validateVenueEditForm({ ...base, hours: backwards })['hours.mon'])
  assert.equal(validateVenueEditForm({ ...base, hours: backwards })['hours.mon'], create(backwards)['hours.mon'])
  assert.deepEqual(validateVenueEditForm({ ...base, hours: { mon: { open: '09:00', close: '18:00' } } }), {})
})

// --- TC-FRONTEND-412 -------------------------------------------------------
test('saving sends the opening hours, never layouts or name', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options })
    return { ok: true, status: 200, json: async () => ({}) }
  })
  const form = venueToEditForm(HOURS_VENUE)
  form.hours.thu = { open: '10:00', close: '16:00' }
  await updateVenue('venue-id', { ...form, name: 'Forbidden', roomLayouts: ['banquet'] })
  assert.equal(calls[0].url, '/api/venues/venue-id')
  assert.equal(calls[0].options.method, 'PATCH')
  assert.equal(calls[0].options.credentials, 'include')
  const body = JSON.parse(calls[0].options.body)
  assert.deepEqual(body.operating_hours, [{ day: 'mon', open: '09:00', close: '18:00' }, { day: 'thu', open: '10:00', close: '16:00' }])
  assert.ok(!('name' in body) && !('room_layouts' in body))
  assert.deepEqual(venueFieldErrorsToForm({ 'operating_hours.1': 'Value error, close must be after open' }, form),
    { 'hours.thu': 'close must be after open' })
})

// --- TC-FRONTEND-413 -------------------------------------------------------
test('a flagged booking says why, in words', () => {
  assert.equal(
    outsideHoursWarning({ booking_date: '2026-11-12', outside_hours: { reason: 'outside_hours', open: '10:00', close: '16:00' } }),
    "Outside the venue's opening hours: it is now open 10:00–16:00 on Thursdays. The booking is kept; review it.",
  )
  assert.equal(
    outsideHoursWarning({ booking_date: '2026-11-13', outside_hours: { reason: 'closed', open: null, close: null } }),
    'The venue is now closed on Fridays. The booking is kept; review it.',
  )
  assert.equal(outsideHoursWarning({ booking_date: '2026-11-12', outside_hours: null }), null)
})
