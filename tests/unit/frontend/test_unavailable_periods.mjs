import assert from 'node:assert/strict'
import test from 'node:test'

import {
  addVenueBlock,
  affectedBookingsSummary,
  availabilityDays,
  BLOCK_REASONS,
  retryBlockNotifications,
  STATE_META,
  validateBlockForm,
} from '../../../frontend/src/lib/venueAvailability.js'
import { alternativeArrangementsNotice, blockReasonLabel } from '../../../frontend/src/lib/venueBookings.js'

// S-77: marking a venue temporarily unavailable, TC-FRONTEND-107..111.

const STUDIO_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const BLOCK_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
const STUDIO_B_HOURS = ['mon', 'tue', 'wed', 'thu', 'fri'].map((day) => ({ day, open: '08:00:00', close: '18:00:00' }))
const BASE_FORM = {
  venueId: STUDIO_B,
  startDate: '2026-11-13',
  startTime: '09:00',
  endDate: '2026-11-14',
  endTime: '17:00',
  reason: 'equipment_failure',
  note: '',
}
const P = {
  start_date: '2026-11-13', start_time: '09:00:00', end_date: '2026-11-14', end_time: '17:00:00',
  reason: 'equipment_failure', note: 'Air handling unit down',
}

async function recordingFetch(answers, run) {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    const [status, body] = answers.shift()
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await run()
  } finally {
    globalThis.fetch = originalFetch
  }
  return calls
}

// --- TC-FRONTEND-107 -------------------------------------------------------
test('the Mark unavailable form needs both dates, both times, an end after the start, and a reason', () => {
  const cases = [
    [{}, []],
    [{ startTime: '' }, ['Choose when the unavailable period starts.']],
    [{ endDate: '' }, ['Choose when the unavailable period ends.']],
    [{ endDate: '2026-11-13', endTime: '09:00' }, ['The period must end after it starts.']],
    [{ endDate: '2026-11-12' }, ['The period must end after it starts.']],
    [{ reason: '' }, ['Choose a reason.']],
    [{ reason: 'other', note: '  ' }, ['Describe the operational reason.']],
    [{ reason: 'other', note: 'Fire alarm testing' }, []],
  ]
  for (const [changes, expected] of cases) {
    assert.deepEqual(validateBlockForm({ ...BASE_FORM, ...changes }), expected, JSON.stringify(changes))
  }
  assert.deepEqual(BLOCK_REASONS, ['maintenance', 'equipment_failure', 'renovation', 'safety', 'other'])
  assert.deepEqual(BLOCK_REASONS.map(blockReasonLabel), [
    'Maintenance', 'Equipment failure', 'Renovation', 'Safety concern', 'Other operational reason',
  ])
})

// --- TC-FRONTEND-108 -------------------------------------------------------
test('the period is sent with its times, and nothing the server owns', async () => {
  const calls = await recordingFetch([[201, {}], [201, {}], [200, {}]], async () => {
    await addVenueBlock(BASE_FORM)
    await addVenueBlock({ ...BASE_FORM, note: '  ' })
    await retryBlockNotifications(BLOCK_ID)
  })

  assert.equal(calls[0].url, '/api/venue-bookings/blocks')
  assert.equal(calls[0].options.method, 'POST')
  assert.equal(calls[0].options.credentials, 'include')
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    venue_id: STUDIO_B, start_date: '2026-11-13', start_time: '09:00', end_date: '2026-11-14',
    end_time: '17:00', reason: 'equipment_failure', note: null,
  })
  assert.equal(JSON.parse(calls[1].options.body).note, null)
  assert.equal(calls[2].url, `/api/venue-bookings/blocks/${BLOCK_ID}/notify`)
  assert.equal(calls[2].options.method, 'POST')
})

// --- TC-FRONTEND-109 -------------------------------------------------------
const AFFECTED = [
  { event_name: 'Alumni talk', status: 'confirmed', booking_date: '2026-11-13', start_time: '10:00:00',
    end_time: '12:00:00', coordinator_name: 'Ada Lim' },
  { event_name: 'Board lunch', status: 'held', booking_date: '2026-11-14', start_time: '15:00:00',
    end_time: '16:30:00', coordinator_name: 'Ben Tan' },
]

test('after saving, Venue Staff are told which bookings are affected and whether Coordinators were told', () => {
  const none = affectedBookingsSummary({ venue_name: 'Studio B', affected_bookings: [], coordinators_notified: true })
  assert.deepEqual(none, { heading: 'Studio B marked unavailable', line: 'No bookings are affected.', rows: [], retry: false })

  const told = affectedBookingsSummary({ venue_name: 'Studio B', affected_bookings: AFFECTED, coordinators_notified: true })
  assert.equal(told.line, '2 bookings need alternative arrangements. Their Coordinators have been notified.')
  assert.deepEqual(told.rows, [
    'Alumni talk · 13 Nov 2026 · 10:00–12:00 · Booked · Ada Lim',
    'Board lunch · 14 Nov 2026 · 15:00–16:30 · Tentatively held · Ben Tan',
  ])
  assert.equal(told.retry, false)

  const untold = affectedBookingsSummary({ venue_name: 'Studio B', affected_bookings: AFFECTED, coordinators_notified: false })
  assert.deepEqual(untold.rows, told.rows)
  assert.equal(untold.line, "The period is saved, but the Coordinators haven't been notified yet.")
  assert.equal(untold.retry, true)

  const one = affectedBookingsSummary({ venue_name: 'Studio B', affected_bookings: AFFECTED.slice(0, 1), coordinators_notified: true })
  assert.match(one.line, /^1 booking needs alternative arrangements\. /)
})

// --- TC-FRONTEND-110 -------------------------------------------------------
test('the calendar marks a fully covered day Unavailable and a partly covered day with the times', () => {
  const entries = [
    { state: 'blocked', ...P },
    { state: 'confirmed', start_date: '2026-11-12', end_date: '2026-11-12', start_time: '10:00:00', end_time: '12:00:00' },
  ]
  const days = availabilityDays({ from: '2026-11-12', to: '2026-11-16' }, entries, STUDIO_B_HOURS)

  assert.equal(days[0].state, 'confirmed')
  assert.equal(days[0].label, 'Booked 10:00–12:00')
  assert.equal(days[1].state, 'partly_blocked')
  assert.equal(days[1].label, 'Partly unavailable')
  assert.deepEqual(days[1].periods.map((period) => period.label), ['Unavailable from 09:00 · Equipment failure'])
  assert.equal(days[2].state, 'partly_blocked')
  assert.deepEqual(days[2].periods.map((period) => period.label), ['Unavailable until 17:00 · Equipment failure'])
  assert.equal(days[3].state, 'closed')
  assert.equal(days[4].state, 'available')

  const colors = Object.values(STATE_META).map((meta) => meta.color)
  assert.equal(new Set(colors).size, colors.length, 'two states share a colour')

  // A booking on a partly covered day keeps its state and lists the period.
  const [withBooking] = availabilityDays({ from: '2026-11-13', to: '2026-11-13' }, [
    { state: 'blocked', ...P },
    { state: 'held', start_date: '2026-11-13', end_date: '2026-11-13', start_time: '07:00:00', end_time: '08:30:00' },
  ], STUDIO_B_HOURS)
  assert.equal(withBooking.state, 'held')
  assert.deepEqual(withBooking.periods.map((period) => period.label), ['Unavailable from 09:00 · Equipment failure'])

  // A migrated S-30 block covers whole days, the weekend included.
  const migrated = availabilityDays({ from: '2026-11-13', to: '2026-11-17' }, [{
    state: 'blocked', start_date: '2026-11-13', start_time: '00:00:00', end_date: '2026-11-17',
    end_time: '00:00:00', reason: 'maintenance',
  }], STUDIO_B_HOURS)
  for (const day of migrated.slice(0, 4)) {
    assert.equal(day.state, 'blocked')
    assert.equal(day.label, 'Unavailable — Maintenance')
  }
  assert.equal(migrated[4].state, 'available')
})

// --- TC-FRONTEND-111 -------------------------------------------------------
test("a Coordinator's flagged booking says it needs alternative arrangements, and why", () => {
  const notice = alternativeArrangementsNotice({
    venue_name: 'Studio B', requires_alternative_arrangements: true, unavailable_periods: [P],
  })
  assert.deepEqual(notice, {
    label: 'Needs alternative arrangements',
    color: '#B25547',
    detail: 'Studio B is unavailable from 13 Nov 2026 09:00 to 14 Nov 2026 17:00 (Equipment failure: Air handling unit down).',
  })

  const later = { ...P, start_date: '2026-11-20', end_date: '2026-11-20', reason: 'safety', note: null }
  const two = alternativeArrangementsNotice({
    venue_name: 'Studio B', requires_alternative_arrangements: true, unavailable_periods: [later, P],
  })
  assert.equal(two.detail, 'Studio B is unavailable from 13 Nov 2026 09:00 to 14 Nov 2026 17:00 '
    + '(Equipment failure: Air handling unit down) and from 20 Nov 2026 09:00 to 20 Nov 2026 17:00 (Safety concern).')

  assert.equal(alternativeArrangementsNotice({ requires_alternative_arrangements: false, unavailable_periods: [] }), null)
})
