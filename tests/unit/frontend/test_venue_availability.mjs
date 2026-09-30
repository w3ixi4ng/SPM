import assert from 'node:assert/strict'
import test from 'node:test'

import { PERMISSIONS, ROLE_ACCESS, hasPermission } from '../../../frontend/src/lib/access.js'
import { ApiError } from '../../../frontend/src/lib/api.js'
import {
  addVenueBlock,
  availabilityDays,
  availabilityErrorMessage,
  earliestFrom,
  getVenueAvailability,
  initialMonth,
  isBeforeMonth,
  monthGrids,
  monthRange,
  shiftMonth,
  yearOptions,
  removeVenueBlock,
  shortDayLabel,
  STATE_META,
  tint,
  WEEKDAY_HEADINGS,
} from '../../../frontend/src/lib/venueAvailability.js'
import {
  bookingDecisionErrorMessage,
  bookingStatusMeta,
  venueBookingErrorMessages,
} from '../../../frontend/src/lib/venueBookings.js'

const TODAY = '2026-11-10'
const STUDIO_B_HOURS = ['mon', 'tue', 'wed', 'thu', 'fri'].map((day) => ({ day, open: '08:00:00', close: '18:00:00' }))

// As TC-VENUEBOOKINGS-035 returns them.
const ENTRIES = [
  { state: 'confirmed', start_date: '2026-11-12', end_date: '2026-11-12', start_time: '09:00:00', end_time: '12:00:00' },
  { state: 'held', start_date: '2026-11-12', end_date: '2026-11-12', start_time: '14:00:00', end_time: '16:00:00' },
  { state: 'blocked', start_date: '2026-11-13', end_date: '2026-11-16', start_time: null, end_time: null, reason: 'maintenance' },
]

const CONFIRMED = 'Studio B is already confirmed on 12 Nov 2026 from 10:00 to 12:00.'
const HELD = 'Studio B is already tentatively held on 12 Nov 2026 from 10:00 to 12:00.'
const BLOCKED = 'Studio B is unavailable from 13 Nov 2026 to 16 Nov 2026.'

async function recordingFetch(answers, run) {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    const [status, body] = answers.shift()
    return new Response(body === null ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  try {
    await run()
  } finally {
    globalThis.fetch = originalFetch
  }
  return calls
}

// --- TC-FRONTEND-067 -------------------------------------------------------
test('the calendar opens on the month tomorrow falls in, and shows a whole month', () => {
  assert.deepEqual(initialMonth(TODAY), { year: 2026, month: 11 })
  // On the last day of a month, tomorrow is in the next one.
  assert.deepEqual(initialMonth('2026-11-30'), { year: 2026, month: 12 })
  assert.deepEqual(initialMonth('2026-12-31'), { year: 2027, month: 1 })

  assert.deepEqual(monthRange({ year: 2026, month: 11 }), { from: '2026-11-01', to: '2026-11-30' })
  assert.deepEqual(monthRange({ year: 2028, month: 2 }), { from: '2028-02-01', to: '2028-02-29' })
})

test('the arrows move one month, across years, and never before the first month', () => {
  const november = { year: 2026, month: 11 }
  assert.deepEqual(shiftMonth(november, 1), { year: 2026, month: 12 })
  assert.deepEqual(shiftMonth(november, 2), { year: 2027, month: 1 })
  assert.deepEqual(shiftMonth({ year: 2027, month: 1 }, -1), { year: 2026, month: 12 })

  assert.equal(isBeforeMonth(shiftMonth(november, -1), november), true)
  assert.equal(isBeforeMonth(november, november), false)
  assert.equal(isBeforeMonth({ year: 2027, month: 3 }, november), false)
  assert.deepEqual(yearOptions(november), [2026, 2027, 2028, 2029, 2030, 2031])
})

// --- TC-FRONTEND-068 -------------------------------------------------------
test('each day gets one state and label, and a block outranks everything', () => {
  const days = availabilityDays({ from: '2026-11-11', to: '2026-11-17' }, ENTRIES, STUDIO_B_HOURS)

  assert.deepEqual(days.map((day) => day.date), [
    '2026-11-11', '2026-11-12', '2026-11-13', '2026-11-14', '2026-11-15', '2026-11-16', '2026-11-17',
  ])
  assert.equal(days[0].state, 'available')
  assert.equal(days[0].label, 'Available')
  assert.deepEqual(days[1].items.map((item) => item.label), ['Booked 09:00–12:00', 'Tentatively held 14:00–16:00'])
  for (const day of days.slice(2, 6)) {
    assert.equal(day.state, 'blocked')
    assert.equal(day.label, 'Unavailable — Maintenance')
  }
  assert.equal(days[6].state, 'available')

  const [booked, held] = days[1].items
  assert.equal(held.color, bookingStatusMeta('pending').color)
  assert.equal(booked.color, '#B25547')
  assert.equal(days[2].color, '#3C6E96')
  const colors = Object.values(STATE_META).map((meta) => meta.color)
  assert.equal(new Set(colors).size, colors.length, 'two states share a colour')
  for (const day of days) assert.ok(day.label.length > 0)
})

test('each block names its state', () => {
  const days = availabilityDays({ from: '2026-11-11', to: '2026-11-14' }, ENTRIES, STUDIO_B_HOURS)
  assert.deepEqual(days.map(shortDayLabel), ['Available', 'Booked + Held', 'Unavailable', 'Unavailable'])
  const [closed] = availabilityDays({ from: '2026-11-15', to: '2026-11-15' }, [], STUDIO_B_HOURS)
  assert.equal(shortDayLabel(closed), 'Closed')
  assert.equal(tint('#3F8F5F'), 'rgba(63, 143, 95, 0.16)')
})

test('a day with only holds reads as held, and holds sort by start time', () => {
  const holds = [
    { ...ENTRIES[1], start_time: '15:00:00', end_time: '16:00:00' },
    { ...ENTRIES[1], start_time: '09:00:00', end_time: '10:00:00' },
  ]
  const [day] = availabilityDays({ from: '2026-11-12', to: '2026-11-12' }, holds, STUDIO_B_HOURS)

  assert.equal(day.state, 'held')
  assert.deepEqual(day.items.map((item) => item.label), ['Tentatively held 09:00–10:00', 'Tentatively held 15:00–16:00'])
})

// --- TC-FRONTEND-069 -------------------------------------------------------
test('days before tomorrow are greyed and disabled', () => {
  const [november] = monthGrids(monthRange({ year: 2026, month: 11 }), TODAY)

  assert.deepEqual(WEEKDAY_HEADINGS, ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'])
  // 1 Nov 2026 is a Sunday, so the grid starts with no blanks.
  assert.equal(november.cells[0].day, 1)
  const days = november.cells.filter(Boolean)
  assert.equal(days.length, 30)
  for (const cell of days) {
    assert.equal(cell.disabled, cell.day <= 10, `day ${cell.day}`)
  }
  assert.equal(earliestFrom(TODAY), '2026-11-11')
})

test('a later month is fully selectable, with leading blanks before the 1st', () => {
  const grids = monthGrids(monthRange({ year: 2026, month: 12 }), TODAY)

  assert.deepEqual(grids.map((grid) => grid.label), ['December 2026'])
  // 1 Dec 2026 is a Tuesday: two blanks for Sunday and Monday.
  assert.deepEqual(grids[0].cells.slice(0, 3).map((cell) => cell?.day ?? null), [null, null, 1])
  assert.ok(grids[0].cells.filter(Boolean).every((cell) => !cell.disabled))
})

// --- TC-FRONTEND-070 -------------------------------------------------------
test('closed weekdays read as Closed, not Available', () => {
  const days = availabilityDays({ from: '2026-11-14', to: '2026-11-16' }, [], STUDIO_B_HOURS)

  assert.deepEqual(days.map((day) => [day.state, day.label]), [
    ['closed', 'Closed'],
    ['closed', 'Closed'],
    ['available', 'Available'],
  ])
})

// --- TC-FRONTEND-071 -------------------------------------------------------
test('the API helpers call the composite fresh each time', async () => {
  const answers = [
    [200, { entries: [] }],
    [200, { entries: [] }],
    [201, { id: 'x1' }],
    [204, null],
  ]
  let removed
  const calls = await recordingFetch(answers, async () => {
    await getVenueAvailability('v1', '2026-11-11', '2026-12-08')
    await getVenueAvailability('v1', '2026-11-11', '2026-12-08')
    await addVenueBlock({ venueId: 'v1', startDate: '2026-11-13', endDate: '2026-11-16', reason: 'maintenance', note: '   ' })
    removed = await removeVenueBlock('x1')
  })

  assert.equal(calls.length, 4)
  for (const call of calls.slice(0, 2)) {
    assert.equal(call.url, '/api/venue-bookings/availability?venue_id=v1&from=2026-11-11&to=2026-12-08')
    assert.equal(call.options.credentials, 'include')
  }
  assert.equal(calls[2].url, '/api/venue-bookings/blocks')
  assert.equal(calls[2].options.method, 'POST')
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    venue_id: 'v1', start_date: '2026-11-13', end_date: '2026-11-16', reason: 'maintenance', note: null,
  })
  assert.equal(calls[3].url, '/api/venue-bookings/blocks/x1')
  assert.equal(calls[3].options.method, 'DELETE')
  assert.equal(removed, null)
})

test('a failed load rejects with a message and never an empty calendar', async () => {
  for (const [status, expected] of [
    [401, 'Your session has expired. Please sign in again.'],
    [403, 'Your role is not permitted to view venue availability.'],
    [404, 'Venue not found'],
    [502, "We couldn't load this venue's availability. Try again in a moment."],
  ]) {
    let failure
    await recordingFetch([[status, { detail: status === 404 ? 'Venue not found' : 'Bookings service unavailable' }]], async () => {
      failure = await getVenueAvailability('v1', '2026-11-11', '2026-12-08').then(() => null, (error) => error)
    })
    assert.ok(failure instanceof ApiError, `status ${status} rejected`)
    assert.equal(availabilityErrorMessage(failure), expected)
  }
})

// --- TC-FRONTEND-072 -------------------------------------------------------
test('hold and block conflicts are shown in the server\'s words', () => {
  for (const detail of [CONFIRMED, HELD, BLOCKED]) {
    assert.deepEqual(venueBookingErrorMessages(new ApiError(detail, 409)), [detail])
  }
  assert.equal(bookingDecisionErrorMessage(new ApiError(BLOCKED, 409)), BLOCKED)
  assert.equal(bookingDecisionErrorMessage(new ApiError(CONFIRMED, 409)), CONFIRMED)
  assert.match(
    bookingDecisionErrorMessage(new ApiError('This booking request has already been decided', 409)),
    /^This request has already been decided/,
  )
})

// --- TC-FRONTEND-073 -------------------------------------------------------
test('Coordinators and Venue Staff see the calendar, and only staff manage blocks', () => {
  assert.equal(PERMISSIONS.VIEW_VENUE_AVAILABILITY, 'venue_bookings:view_availability')
  assert.equal(PERMISSIONS.MANAGE_VENUE_BLOCKS, 'venue_bookings:manage_blocks')
  for (const role of Object.keys(ROLE_ACCESS)) {
    assert.equal(
      hasPermission(role, PERMISSIONS.VIEW_VENUE_AVAILABILITY),
      ['event_coordinator', 'venue_staff'].includes(role),
      role,
    )
    assert.equal(hasPermission(role, PERMISSIONS.MANAGE_VENUE_BLOCKS), role === 'venue_staff', role)
  }
})
