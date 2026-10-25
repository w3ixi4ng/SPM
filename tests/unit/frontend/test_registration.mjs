import assert from 'node:assert/strict'
import test from 'node:test'

import {
  attendeeCountLabel,
  closeRegistration,
  describeRegistration,
  joinWaitingList,
  listEventAttendees,
  listMyRegistrations,
  registrationClosureControl,
  registrationStatusLabel,
  registrationCountdown,
  registrationWindow,
  reopenRegistration,
  validateRegistrationSettings,
  waitingListLabel,
  waitingListPlace,
} from '../../../frontend/src/lib/registration.js'
import {
  eventFieldErrorsToForm,
  eventFormToPayload,
  eventResponseToForm,
} from '../../../frontend/src/lib/eventRequests.js'

const EVENT_START = { startDate: '2026-11-20', startTime: '18:00' }
const EVENT = {
  registration_required: true,
  registration_opens_at: '2026-11-01T09:00:00',
  registration_closes_at: '2026-11-15T18:00:00',
}

// --- TC-FRONTEND-144 -------------------------------------------------------
test("the Organiser's registration settings are checked before saving", () => {
  const off = { required: false, opensAt: null, closesAt: null }
  const on = (opensAt, closesAt) => ({ required: true, opensAt, closesAt })

  assert.deepEqual(validateRegistrationSettings(off, EVENT_START, { submitting: true }), {})
  assert.deepEqual(validateRegistrationSettings(on(null, null), EVENT_START, { submitting: true }), {
    opens: 'Choose when registration opens.',
    closes: 'Choose when registration closes.',
  })
  assert.deepEqual(validateRegistrationSettings(on(null, null), EVENT_START, { submitting: false }), {})
  assert.deepEqual(
    validateRegistrationSettings(on('2026-11-15T18:00', '2026-11-15T18:00'), EVENT_START),
    { closes: 'Registration must close after it opens.' },
  )
  assert.deepEqual(
    validateRegistrationSettings(on('2026-11-01T09:00', '2026-11-20T18:00'), EVENT_START),
    { closes: 'Registration must close before the event starts.' },
  )
  assert.deepEqual(
    validateRegistrationSettings(on('2026-10-01T09:00', '2026-11-15T18:00'), EVENT_START, { submitting: true }),
    {},
  )
})

// --- TC-FRONTEND-145 -------------------------------------------------------
test('where now falls in the registration period', () => {
  assert.equal(registrationWindow(EVENT, new Date('2026-11-01T00:59:00Z')), 'not_open')
  assert.equal(registrationWindow(EVENT, new Date('2026-11-01T01:00:00Z')), 'open')
  assert.equal(registrationWindow(EVENT, new Date('2026-11-15T09:59:00Z')), 'open')
  assert.equal(registrationWindow(EVENT, new Date('2026-11-15T10:00:00Z')), 'closed')

  const off = { registration_required: false, registration_opens_at: null, registration_closes_at: null }
  assert.equal(registrationWindow(off, new Date('2026-11-05T00:00:00Z')), 'not_required')
})

// --- TC-FRONTEND-146 -------------------------------------------------------
test('the period is described in words Attendees can read', () => {
  const period = 'Registration opens 1 Nov 2026, 9:00 am and closes 15 Nov 2026, 6:00 pm.'

  const before = describeRegistration(EVENT, new Date('2026-10-25T02:00:00Z'))
  assert.equal(before.period, period)
  assert.equal(
    before.status,
    "Registration hasn't opened yet. It's open from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm.",
  )

  const after = describeRegistration(EVENT, new Date('2026-11-16T00:00:00Z'))
  assert.equal(after.period, period)
  assert.equal(
    after.status,
    'Registration has closed. It was open from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm.',
  )

  const off = describeRegistration({ registration_required: false }, new Date())
  assert.equal(off.period, null)
  assert.equal(off.status, "This event doesn't need registration.")
})

// Supports TC-EVENTS-171 from the page's side: once submitted, the form
// never sends the settings, so an ordinary edit is not refused.
test('the form sends the period as one date-time, and can leave it out', () => {
  const form = eventResponseToForm({ ...EVENT, name: 'Alumni evening' })
  assert.equal(form.registrationOpensDate, '2026-11-01')
  assert.equal(form.registrationOpensTime, '09:00')

  const payload = eventFormToPayload(form)
  assert.equal(payload.registration_required, true)
  assert.equal(payload.registration_opens_at, '2026-11-01T09:00')
  assert.equal(payload.registration_closes_at, '2026-11-15T18:00')

  const locked = eventFormToPayload(form, { includeRegistration: false })
  assert.equal('registration_required' in locked, false)
  assert.equal('registration_opens_at' in locked, false)

  const off = eventFormToPayload({ ...form, registrationRequired: false })
  assert.equal(off.registration_opens_at, null)
  assert.equal(off.registration_closes_at, null)

  assert.deepEqual(
    eventFieldErrorsToForm({
      registration_opens_at: 'Value error, Choose when registration opens.',
      body: 'Value error, Registration must close before the event starts.',
    }),
    {
      registrationOpensDate: 'Choose when registration opens.',
      registrationClosesDate: 'Registration must close before the event starts.',
    },
  )
})

// --- TC-FRONTEND-254 -------------------------------------------------------
test('the registration lists are read from the composite', async (t) => {
  const calls = []
  const realFetch = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return new Response(JSON.stringify([{ event_id: 'e' }]), { status: 200 })
  }
  t.after(() => { globalThis.fetch = realFetch })

  assert.deepEqual(await listMyRegistrations(), [{ event_id: 'e' }])
  await listEventAttendees('22222222-2222-4222-8222-222222222222')

  assert.equal(calls[0].url, '/api/event-registrations/me/registrations')
  assert.equal(
    calls[1].url,
    '/api/event-registrations/events/22222222-2222-4222-8222-222222222222/attendees',
  )
  for (const call of calls) assert.equal(call.options.credentials, 'include')
})

// --- TC-FRONTEND-255 -------------------------------------------------------
test('the attendee count reads as a sentence', () => {
  assert.equal(attendeeCountLabel(0), 'No one has registered yet.')
  assert.equal(attendeeCountLabel(1), '1 attendee registered')
  assert.equal(attendeeCountLabel(2), '2 attendees registered')
})

// --- S-50 ------------------------------------------------------------------
const NOW = new Date('2026-11-05T04:00:00Z') // 12:00 in Singapore
const CLOSED_AT = '2026-11-03T06:15:00+00:00'

// --- TC-FRONTEND-256 -------------------------------------------------------
test("a full event's status offers the waiting list", () => {
  const full = { ...EVENT, is_full: true, registration_closed_by_organiser: false }
  const { state, status } = describeRegistration(full, NOW)
  assert.equal(state, 'full')
  assert.equal(status, 'This event is full. You can join the waiting list.')
  assert.equal(registrationCountdown(full, NOW), null)
})

// --- TC-FRONTEND-257 -------------------------------------------------------
test('registration closed by the Organiser, and which message wins', () => {
  const closed = { ...EVENT, is_full: false, registration_closed_by_organiser: true }
  const message = 'The organiser has closed registration for this event.'

  let described = describeRegistration(closed, NOW)
  assert.equal(described.state, 'closed_by_organiser')
  assert.equal(described.status, message)
  assert.equal(registrationCountdown(closed, NOW), null)

  described = describeRegistration({ ...closed, is_full: true }, NOW)
  assert.equal(described.state, 'closed_by_organiser')
  assert.equal(described.status, message)

  described = describeRegistration(closed, new Date('2026-11-16T04:00:00Z'))
  assert.equal(described.state, 'closed')
  assert.equal(
    described.status,
    'Registration has closed. It was open from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm.',
  )

  const fullEarly = { ...EVENT, is_full: true, registration_closed_by_organiser: false }
  assert.equal(describeRegistration(fullEarly, new Date('2026-10-30T04:00:00Z')).state, 'not_open')
})

// --- TC-FRONTEND-258 -------------------------------------------------------
test('when the Organiser can close or reopen, and what it says', () => {
  const confirmed = { ...EVENT, status: 'confirmed', registration_closed_at: null }
  assert.deepEqual(registrationClosureControl(confirmed, NOW), { action: 'close', status: null })
  assert.deepEqual(
    registrationClosureControl({ ...confirmed, registration_closed_at: CLOSED_AT }, NOW),
    {
      action: 'reopen',
      status: "You closed registration on 3 Nov 2026, 2:15 pm. Attendees can't register until you reopen it.",
    },
  )
  assert.equal(registrationClosureControl({ ...confirmed, status: 'planning' }, NOW), null)
  assert.equal(
    registrationClosureControl({ ...confirmed, registration_required: false }, NOW),
    null,
  )
  assert.equal(registrationClosureControl(confirmed, new Date('2026-11-16T04:00:00Z')), null)
})

// --- TC-FRONTEND-259 -------------------------------------------------------
test('the waiting list and close/reopen calls go to the right services', async (t) => {
  const calls = []
  const realFetch = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ ok: true }), { status: 200 })
  }
  t.after(() => { globalThis.fetch = realFetch })

  assert.deepEqual(await joinWaitingList('E'), { ok: true })
  assert.deepEqual(await closeRegistration('E'), { ok: true })
  assert.deepEqual(await reopenRegistration('E'), { ok: true })

  assert.deepEqual(
    calls.map((call) => [call.options.method, call.url]),
    [
      ['POST', '/api/event-registrations/events/E/waiting-list'],
      ['PUT', '/api/events/E/registration-closure'],
      ['DELETE', '/api/events/E/registration-closure'],
    ],
  )
  for (const call of calls) assert.equal(call.options.credentials, 'include')
})

// --- TC-FRONTEND-260 -------------------------------------------------------
test('the waiting-list count reads as a sentence', () => {
  assert.equal(waitingListLabel(0), 'No one is on the waiting list.')
  assert.equal(waitingListLabel(1), '1 person on the waiting list')
  assert.equal(waitingListLabel(3), '3 people on the waiting list')
})

// --- TC-FRONTEND-261 -------------------------------------------------------
test('the place in line reads as a sentence', () => {
  const cases = {
    1: "You're next in line.",
    2: "You're 2nd in line.",
    3: "You're 3rd in line.",
    4: "You're 4th in line.",
    11: "You're 11th in line.",
    12: "You're 12th in line.",
    13: "You're 13th in line.",
    21: "You're 21st in line.",
    22: "You're 22nd in line.",
    23: "You're 23rd in line.",
    111: "You're 111th in line.",
  }
  for (const [n, expected] of Object.entries(cases)) {
    assert.equal(waitingListPlace(Number(n)), expected)
  }
  assert.equal(waitingListPlace(null), '')
})

// --- TC-FRONTEND-262 -------------------------------------------------------
test('a dashboard row says confirmed or waiting', () => {
  assert.equal(registrationStatusLabel({ status: 'confirmed' }), 'Confirmed')
  assert.equal(registrationStatusLabel({ status: 'waitlisted', position: 1 }), 'Waiting list · next in line')
  assert.equal(registrationStatusLabel({ status: 'waitlisted', position: 3 }), 'Waiting list · 3rd in line')
  assert.equal(registrationStatusLabel({ status: 'waitlisted', position: null }), 'Waiting list')
})
