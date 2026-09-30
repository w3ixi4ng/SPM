import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createVenue,
  emptyVenueFilters,
  emptyVenueForm,
  filterVenues,
  getVenueOptions,
  listVenues,
  validateVenueForm,
  venueErrorMessage,
  venueFieldErrorsToForm,
  venueFiltersFromEvent,
} from '../../../frontend/src/lib/venues.js'

// The valid venue from tests/unit/atomic/venues/TEST_CASES.md, in form shape.
const COMPLETE_FORM = {
  name: '  Harbourfront Hall  ',
  location: '1 Harbourfront Walk, Singapore 098585',
  capacity: '250',
  description: 'Waterfront hall with a raised stage.',
  facilities: ['projector', 'wifi', 'stage'],
  accessibility: ['wheelchair_access', 'accessible_toilets'],
  roomLayouts: ['theatre', 'banquet'],
  // Deliberately out of week order: the payload must not depend on it.
  hours: {
    sat: { open: '10:00', close: '22:00' },
    mon: { open: '09:00', close: '18:00' },
  },
  created_by: 'must-not-be-sent',
}

const API_VENUE = {
  id: '22222222-2222-2222-2222-222222222222',
  name: 'Harbourfront Hall',
  capacity: 250,
}

async function recordingFetch(run) {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify(API_VENUE), {
      status: 200,
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

// --- TC-FRONTEND-010 -------------------------------------------------------
test('venue form reports every missing required field', () => {
  assert.deepEqual(
    Object.keys(validateVenueForm(emptyVenueForm())).sort(),
    ['capacity', 'location', 'name', 'operating_hours', 'room_layouts'],
  )

  const invalid = validateVenueForm({
    ...emptyVenueForm(),
    name: '  ',
    location: '  ',
    capacity: '0',
    roomLayouts: [],
    hours: { mon: { open: '18:00', close: '09:00' } },
  })
  assert.deepEqual(
    Object.keys(invalid).sort(),
    ['capacity', 'hours.mon', 'location', 'name', 'operating_hours', 'room_layouts'],
  )
  assert.match(invalid['hours.mon'], /Closing time must be after opening time/)
  assert.match(invalid.operating_hours, /Monday/)

  assert.deepEqual(validateVenueForm(COMPLETE_FORM), {})
})

// --- TC-FRONTEND-011 -------------------------------------------------------
test('venue API functions use Kong paths, methods, JSON, and credentials', async () => {
  const calls = await recordingFetch(async () => {
    await listVenues()
    await getVenueOptions()
    await createVenue(COMPLETE_FORM)
  })

  assert.deepEqual(
    calls.map(({ url, options }) => [options.method ?? 'GET', url]),
    [
      ['GET', '/api/venues'],
      ['GET', '/api/venues/options'],
      ['POST', '/api/venues'],
    ],
  )
  for (const { options } of calls) assert.equal(options.credentials, 'include')

  assert.deepEqual(JSON.parse(calls[2].options.body), {
    name: 'Harbourfront Hall',
    location: '1 Harbourfront Walk, Singapore 098585',
    capacity: 250,
    facilities: ['projector', 'wifi', 'stage'],
    accessibility: ['wheelchair_access', 'accessible_toilets'],
    room_layouts: ['theatre', 'banquet'],
    operating_hours: [
      { day: 'mon', open: '09:00', close: '18:00' },
      { day: 'sat', open: '10:00', close: '22:00' },
    ],
    description: 'Waterfront hall with a raised stage.',
  })
})

// --- TC-FRONTEND-012 -------------------------------------------------------
test('venue API errors map to safe status and field feedback', () => {
  assert.match(venueErrorMessage({ status: 401 }), /sign in again/)
  assert.match(venueErrorMessage({ status: 403 }), /not permitted/)
  assert.match(venueErrorMessage({ status: 409 }), /already exists.*another name/)
  assert.match(venueErrorMessage({ status: 422 }), /highlighted/)
  assert.match(venueErrorMessage({ status: 500 }), /was not saved/)

  const mapped = venueFieldErrorsToForm(
    {
      capacity: 'Input should be greater than or equal to 1',
      'operating_hours.0': 'Value error, close must be after open',
    },
    COMPLETE_FORM,
  )
  assert.deepEqual(mapped, {
    capacity: 'Input should be greater than or equal to 1',
    'hours.mon': 'close must be after open',
  })
})

// --- S-34: search and filter venues ----------------------------------------

const hours = (day, open, close) => ({ day, open: `${open}:00`, close: `${close}:00` })
const FILTER_VENUES = [
  {
    name: 'Harbour Hall', location: '1 Harbourfront Walk', capacity: 250,
    room_layouts: ['theatre', 'banquet'], facilities: ['projector', 'stage'], accessibility: ['lift'],
    operating_hours: [hours('mon', '09:00', '18:00'), hours('thu', '08:00', '20:00')],
  },
  {
    name: 'Studio B', location: '10 Anson Road', capacity: 80,
    room_layouts: ['classroom', 'boardroom'], facilities: ['projector'], accessibility: [],
    operating_hours: [hours('thu', '08:00', '20:00')],
  },
  {
    name: 'Anson Suite', location: '12 Anson Road', capacity: 150,
    room_layouts: ['theatre', 'cocktail'], facilities: ['stage'], accessibility: ['lift', 'hearing_loop'],
    operating_hours: [hours('sat', '10:00', '16:00')],
  },
]

function names(filters) {
  return filterVenues(FILTER_VENUES, { ...emptyVenueFilters(), ...filters }).map((venue) => venue.name)
}

// --- TC-FRONTEND-057 -------------------------------------------------------
test('no filters shows every venue, in order', () => {
  const before = FILTER_VENUES.map((venue) => venue.name)
  assert.deepEqual(names({}), ['Harbour Hall', 'Studio B', 'Anson Suite'])
  assert.deepEqual(FILTER_VENUES.map((venue) => venue.name), before)
})

// --- TC-FRONTEND-058 -------------------------------------------------------
test('the text search matches location or name, ignoring case', () => {
  assert.deepEqual(names({ query: 'anson' }), ['Studio B', 'Anson Suite'])
  assert.deepEqual(names({ query: '  HARBOUR ' }), ['Harbour Hall'])
  assert.deepEqual(names({ query: 'studio' }), ['Studio B'])
  assert.deepEqual(names({ query: 'nowhere' }), [])
})

// --- TC-FRONTEND-059 -------------------------------------------------------
test('"holds at least" keeps venues with enough capacity', () => {
  assert.deepEqual(names({ attendance: '150' }), ['Harbour Hall', 'Anson Suite'])
  assert.deepEqual(names({ attendance: '151' }), ['Harbour Hall'])
  assert.deepEqual(names({ attendance: '' }), ['Harbour Hall', 'Studio B', 'Anson Suite'])
})

// --- TC-FRONTEND-060 -------------------------------------------------------
test('facilities and accessibility need every one ticked', () => {
  assert.deepEqual(names({ facilities: ['projector'] }), ['Harbour Hall', 'Studio B'])
  assert.deepEqual(names({ facilities: ['projector', 'stage'] }), ['Harbour Hall'])
  assert.deepEqual(names({ accessibility: ['lift'] }), ['Harbour Hall', 'Anson Suite'])
  assert.deepEqual(names({ accessibility: ['lift', 'hearing_loop'] }), ['Anson Suite'])
})

// --- TC-FRONTEND-061 -------------------------------------------------------
test('date and time keep venues open then', () => {
  assert.deepEqual(names({ date: '2026-11-12' }), ['Harbour Hall', 'Studio B'])
  assert.deepEqual(names({ date: '2026-11-12', startTime: '09:00', endTime: '19:00' }), ['Harbour Hall', 'Studio B'])
  assert.deepEqual(names({ date: '2026-11-12', startTime: '07:00', endTime: '10:00' }), [])
  assert.deepEqual(names({ date: '2026-11-14', startTime: '10:00', endTime: '16:00' }), ['Anson Suite'])
  assert.deepEqual(names({ startTime: '09:00', endTime: '12:00' }), ['Harbour Hall', 'Studio B', 'Anson Suite'])
})

// --- TC-FRONTEND-062 -------------------------------------------------------
test('results match every applied filter at once', () => {
  const all = {
    query: 'anson', attendance: '100', layout: 'theatre', facilities: ['stage'],
    accessibility: ['lift'], date: '2026-11-14', startTime: '10:00', endTime: '12:00',
  }
  assert.deepEqual(names(all), ['Anson Suite'])
  assert.deepEqual(names({ ...all, date: '2026-11-12' }), [])
})

// --- TC-FRONTEND-063 -------------------------------------------------------
test("the request screen's filters start from the event", () => {
  const event = {
    expected_attendance: 100,
    room_layout: 'theatre',
    required_facilities: ['stage'],
    required_accessibility: ['lift'],
    start_date: '2026-11-14',
    start_time: '10:00:00',
    end_time: '12:00:00',
  }
  assert.deepEqual(venueFiltersFromEvent(event), {
    query: '',
    attendance: '100',
    layout: 'theatre',
    facilities: ['stage'],
    accessibility: ['lift'],
    date: '2026-11-14',
    startTime: '10:00',
    endTime: '12:00',
  })
  assert.equal(venueFiltersFromEvent({ ...event, room_layout: null }).layout, '')
})

// --- TC-FRONTEND-064 -------------------------------------------------------
test('the room layout filter keeps venues that offer it', () => {
  assert.deepEqual(names({ layout: 'theatre' }), ['Harbour Hall', 'Anson Suite'])
  assert.deepEqual(names({ layout: 'boardroom' }), ['Studio B'])
  assert.deepEqual(names({ layout: 'banquet' }), ['Harbour Hall'])
  assert.deepEqual(names({ layout: '' }), ['Harbour Hall', 'Studio B', 'Anson Suite'])
})
