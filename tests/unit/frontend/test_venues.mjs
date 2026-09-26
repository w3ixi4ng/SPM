import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createVenue,
  emptyVenueForm,
  getVenueOptions,
  listVenues,
  validateVenueForm,
  venueErrorMessage,
  venueFieldErrorsToForm,
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
    ['capacity', 'location', 'name', 'operating_hours', 'room_layouts'],
  )
  assert.match(invalid.operating_hours, /Closing time must be after opening time/)

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
