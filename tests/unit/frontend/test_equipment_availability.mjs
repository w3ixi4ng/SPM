import assert from 'node:assert/strict'
import test from 'node:test'

import { PERMISSIONS, ROLE_ACCESS, hasPermission } from '../../../frontend/src/lib/access.js'
import { ApiError } from '../../../frontend/src/lib/api.js'
import {
  availabilityErrorMessages,
  availabilitySummary,
  checkEquipmentAvailability,
  checkedAtLabel,
  emptyAvailabilityForm,
  validateAvailabilityForm,
} from '../../../frontend/src/lib/equipmentAvailability.js'

const WINDOW = { startDate: '2026-11-12', startTime: '09:00', endDate: '2026-11-12', endTime: '12:00' }

// As TC-EQUIPMENTREQUIREMENTS-012 and 014 return them.
const MIC = { type: 'Wireless Microphone', operational_status: 'available', total: 12, reserved: 10, unavailable: 0, available: 2, over_reserved: false, sufficient: null }
const PROJECTOR = { type: 'Projector', operational_status: 'maintenance', total: 4, reserved: 1, unavailable: 4, available: 0, over_reserved: false, sufficient: null }
const OVER = { ...MIC, reserved: 14, available: 0, over_reserved: true }

// --- TC-FRONTEND-074 -------------------------------------------------------
test('the check form is validated before anything is sent', () => {
  const blank = { ...emptyAvailabilityForm(''), startDate: '', endDate: '' }
  assert.deepEqual(validateAvailabilityForm(blank), ['Choose a start date and time.', 'Choose an end date and time.'])

  const same = { ...emptyAvailabilityForm(''), ...WINDOW, endTime: '09:00' }
  assert.deepEqual(validateAvailabilityForm(same), ['The end must be after the start.'])
  const reversed = { ...emptyAvailabilityForm(''), ...WINDOW, endDate: '2026-11-11' }
  assert.deepEqual(validateAvailabilityForm(reversed), ['The end must be after the start.'])

  for (const quantity of ['0', '-2', '1.5']) {
    assert.deepEqual(
      validateAvailabilityForm({ ...emptyAvailabilityForm(''), ...WINDOW, quantity }),
      ['Enter a whole number of 1 or more, or leave it blank.'],
      quantity,
    )
  }
  assert.deepEqual(validateAvailabilityForm({ ...emptyAvailabilityForm(''), ...WINDOW }), [])
  assert.deepEqual(emptyAvailabilityForm('2026-11-10'), {
    startDate: '2026-11-10', startTime: '', endDate: '2026-11-10', endTime: '', type: '', quantity: '',
  })
})

// --- TC-FRONTEND-075 -------------------------------------------------------
test('each item reads as available, short, unavailable or over-reserved', () => {
  const mic = availabilitySummary(MIC)
  assert.equal(mic.headline, '2 of 12 available')
  assert.equal(mic.reserved, '10 reserved')
  assert.equal(mic.verdict, null)

  const enough = availabilitySummary({ ...MIC, sufficient: true }).verdict
  assert.deepEqual(enough, { label: 'Enough', color: '#3F8F5F' })
  const short = availabilitySummary({ ...MIC, sufficient: false }).verdict
  assert.deepEqual(short, { label: 'Not enough — 2 available', color: '#B25547' })

  const projector = availabilitySummary(PROJECTOR)
  assert.equal(projector.headline, '0 of 4 available — Maintenance')
  assert.equal(projector.headlineColor, '#B5842B')
  assert.equal(availabilitySummary({ ...PROJECTOR, sufficient: false }).verdict.label, 'Not enough')

  assert.equal(availabilitySummary(OVER).headline, '0 of 12 available — over-reserved by 2')
})

// --- TC-FRONTEND-076 -------------------------------------------------------
test('the API helper sends only what was filled in', async () => {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await checkEquipmentAvailability({ ...WINDOW, type: ' Mic ', quantity: '3' })
    await checkEquipmentAvailability({ ...WINDOW, type: '', quantity: '' })
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(calls.length, 2)
  assert.equal(calls[0].url, '/api/equipment-requirements/availability?start_date=2026-11-12&start_time=09%3A00&end_date=2026-11-12&end_time=12%3A00&type=Mic&quantity=3')
  assert.equal(calls[1].url, '/api/equipment-requirements/availability?start_date=2026-11-12&start_time=09%3A00&end_date=2026-11-12&end_time=12%3A00')
  assert.equal(calls[0].options.credentials, 'include')
})

// --- TC-FRONTEND-077 -------------------------------------------------------
test('only Technical Support can open the check', () => {
  assert.equal(PERMISSIONS.CHECK_EQUIPMENT_AVAILABILITY, 'equipment:check_availability')
  for (const role of Object.keys(ROLE_ACCESS)) {
    assert.equal(hasPermission(role, PERMISSIONS.CHECK_EQUIPMENT_AVAILABILITY), role === 'technical_support', role)
  }
})

// --- TC-FRONTEND-078 -------------------------------------------------------
test('failures are shown, never an empty result, and the check time is shown', () => {
  assert.deepEqual(availabilityErrorMessages(new ApiError('x', 401)), ['Your session has expired. Please sign in again.'])
  assert.deepEqual(availabilityErrorMessages(new ApiError('x', 403)), ['Only Technical Support can check equipment availability.'])
  assert.deepEqual(
    availabilityErrorMessages(new ApiError('Please check', 422, { end_time: 'The end must be after the start' })),
    ['The end must be after the start'],
  )
  assert.deepEqual(
    availabilityErrorMessages(new ApiError('Equipment service unavailable', 502)),
    ["We couldn't check availability. Nothing is shown until it works — try again in a moment."],
  )
  assert.equal(checkedAtLabel('2026-11-10T06:32:10Z', 'UTC'), 'Checked at 06:32')
})
