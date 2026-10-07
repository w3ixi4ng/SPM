import assert from 'node:assert/strict'
import test from 'node:test'

import { PERMISSIONS, ROLE_ACCESS, hasPermission } from '../../../frontend/src/lib/access.js'
import { availabilityDays, setupTurnaroundLabel } from '../../../frontend/src/lib/venueAvailability.js'
import {
  bookingClashMessage,
  clashPairLabel,
  decisionNotice,
  getVenueClashes,
  pendingRequestPath,
  pendingRequestSummary,
  venueFit,
} from '../../../frontend/src/lib/venueBookings.js'
import {
  emptyVenueForm,
  filterVenues,
  emptyVenueFilters,
  validateVenueEditForm,
  validateVenueForm,
  venueFormToPayload,
  venueToEditForm,
} from '../../../frontend/src/lib/venues.js'

const STUDIO_B = {
  id: 'v1', name: 'Studio B', location: '10 Anson Road', capacity: 150, facilities: [], accessibility: [],
  room_layouts: ['theatre'], operating_hours: [{ day: 'thu', open: '08:00:00', close: '20:00:00' }],
  setup_minutes: 30, turnaround_minutes: 45,
}
const GAP = { setup: 30, turnaround: 45 }
const EVENT = { expected_attendance: 10, room_layout: null, required_facilities: [], required_accessibility: [] }

const A_CLASH = {
  booking_date: '2026-11-12', start_time: '10:00:00', end_time: '12:00:00',
  occupied_start: '09:30', occupied_end: '12:45', status: 'confirmed',
}
const B = {
  id: 'b1', event_name: 'Board lunch', venue_name: 'Studio B', booking_date: '2026-11-12',
  start_time: '12:30:00', end_time: '14:00:00', status: 'held', clashes: [A_CLASH],
}
const D = {
  id: 'd1', event_name: 'Alumni talk', venue_name: 'Studio B', booking_date: '2026-11-12',
  start_time: '12:15:00', end_time: '12:45:00', status: 'pending', clashes: [],
}

// --- TC-FRONTEND-081 -------------------------------------------------------
test('the venue form records both times, 0 or more', () => {
  const empty = emptyVenueForm()
  assert.equal(empty.setupMinutes, '0')
  assert.equal(empty.turnaroundMinutes, '0')
  const edit = venueToEditForm(STUDIO_B)
  assert.equal(edit.setupMinutes, '30')
  assert.equal(edit.turnaroundMinutes, '45')

  for (const value of ['', '-1', '1.5']) {
    for (const [field, key] of [['setupMinutes', 'setup_minutes'], ['turnaroundMinutes', 'turnaround_minutes']]) {
      assert.equal(validateVenueForm({ ...empty, [field]: value })[key], 'Enter whole minutes, 0 or more.', `${field}=${value}`)
      assert.equal(validateVenueEditForm({ ...edit, [field]: value })[key], 'Enter whole minutes, 0 or more.')
    }
  }
  assert.equal(validateVenueForm({ ...empty, setupMinutes: '0' }).setup_minutes, undefined)
  assert.deepEqual(validateVenueEditForm(edit), {})

  const payload = venueFormToPayload({ ...empty, name: 'X', location: 'Y', capacity: '5', setupMinutes: ' 30 ', turnaroundMinutes: '45' })
  assert.equal(payload.setup_minutes, 30)
  assert.equal(payload.turnaround_minutes, 45)
})

// --- TC-FRONTEND-082 -------------------------------------------------------
test('the request screen applies setup and turnaround to opening hours', () => {
  const at = (startTime, endTime) => ({ date: '2026-11-12', startTime, endTime })
  assert.deepEqual(venueFit(EVENT, STUDIO_B, at('08:30', '10:00')), [])
  for (const [start, end] of [['08:00', '10:00'], ['18:00', '19:30']]) {
    assert.deepEqual(venueFit(EVENT, STUDIO_B, at(start, end)),
      ['Open 08:00–20:00 on Thursdays, with 30 min setup and 45 min turnaround'])
  }
  const filters = { ...emptyVenueFilters(), date: '2026-11-12', startTime: '08:00', endTime: '10:00' }
  assert.deepEqual(filterVenues([STUDIO_B], filters), [])
  assert.deepEqual(filterVenues([STUDIO_B], { ...filters, startTime: '08:30' }), [STUDIO_B])

  const plain = { ...STUDIO_B, setup_minutes: 0, turnaround_minutes: 0 }
  assert.deepEqual(venueFit(EVENT, plain, at('08:00', '20:00')), [])
})

// --- TC-FRONTEND-083 -------------------------------------------------------
test('the calendar shows the event time and the time the venue is in use', () => {
  const entries = [
    { state: 'confirmed', start_date: '2026-11-12', end_date: '2026-11-12', start_time: '10:00:00', end_time: '12:00:00' },
    { state: 'held', start_date: '2026-11-12', end_date: '2026-11-12', start_time: '12:30:00', end_time: '14:00:00' },
  ]
  const [day] = availabilityDays({ from: '2026-11-12', to: '2026-11-12' }, entries, STUDIO_B.operating_hours, GAP)
  assert.deepEqual(day.items.map((item) => item.label), [
    'Booked 10:00–12:00 · venue in use 09:30–12:45',
    'Tentatively held 12:30–14:00 · venue in use 12:00–14:45',
  ])
  const [plain] = availabilityDays({ from: '2026-11-12', to: '2026-11-12' }, entries, STUDIO_B.operating_hours)
  assert.equal(plain.items[0].label, 'Booked 10:00–12:00')
  assert.equal(setupTurnaroundLabel(GAP), 'Setup 30 min · Turnaround 45 min')
})

// --- TC-FRONTEND-084 -------------------------------------------------------
test('a clashing booking shows a warning to its Coordinator', () => {
  assert.equal(bookingClashMessage(B),
    'Clashes with another confirmed booking on 12 Nov 2026, 10:00–12:00 (venue in use 09:30–12:45) '
    + "under Studio B's setup and turnaround times. Contact Venue Staff to rearrange.")
  assert.equal(bookingClashMessage(D), null)
  assert.equal(bookingClashMessage({ ...D, clashes: undefined }), null)
})

// --- TC-FRONTEND-085 -------------------------------------------------------
test('Venue Staff see the clashes after saving', async () => {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ pairs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await getVenueClashes('v1')
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.equal(calls[0].url, '/api/venue-bookings/clashes?venue_id=v1')
  assert.equal(calls[0].options.credentials, 'include')

  const side = (name, status, start, end) => ({ event_name: name, status, booking_date: '2026-11-12', start_time: start, end_time: end })
  assert.equal(
    clashPairLabel({ first: side('Alumni talk', 'confirmed', '10:00:00', '12:00:00'), second: side('Board lunch', 'held', '12:30:00', '14:00:00') }),
    'Alumni talk (Confirmed, 10:00–12:00) and Board lunch (Tentatively held, 12:30–14:00) on 12 Nov 2026',
  )
})

// --- TC-FRONTEND-086 -------------------------------------------------------
test('each pending request is one compact row that opens its page', () => {
  const d = pendingRequestSummary(D)
  assert.equal(d.title, 'Alumni talk')
  assert.equal(d.line, 'Studio B · 12 Nov 2026, 12:15–12:45')
  assert.equal(d.status.label, 'Pending')
  assert.equal(d.clash, null)
  const b = pendingRequestSummary(B)
  assert.equal(b.status.label, 'Tentatively held')
  assert.equal(b.clash, 'Clash')
  assert.equal(pendingRequestPath(B), '/venue-bookings/b1')
})

// --- TC-FRONTEND-087 -------------------------------------------------------
test('the request page is Venue Staff only, and a decision notice reads once', () => {
  for (const role of Object.keys(ROLE_ACCESS)) {
    assert.equal(hasPermission(role, PERMISSIONS.VIEW_PENDING_VENUE_BOOKINGS), role === 'venue_staff', role)
  }
  const booking = { event_name: 'Alumni talk', venue_name: 'Studio B' }
  assert.equal(decisionNotice('approved', booking), 'Booking for Alumni talk at Studio B confirmed.')
  assert.equal(decisionNotice('rejected', booking), 'Booking for Alumni talk at Studio B rejected.')
})
