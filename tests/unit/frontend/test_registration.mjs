import assert from 'node:assert/strict'
import test from 'node:test'

import {
  attendeeCountLabel,
  describeRegistration,
  listEventAttendees,
  listMyRegistrations,
  registrationWindow,
  validateRegistrationSettings,
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

// --- TC-FRONTEND-251 -------------------------------------------------------
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

// --- TC-FRONTEND-252 -------------------------------------------------------
test('the attendee count reads as a sentence', () => {
  assert.equal(attendeeCountLabel(0), 'No one has registered yet.')
  assert.equal(attendeeCountLabel(1), '1 attendee registered')
  assert.equal(attendeeCountLabel(2), '2 attendees registered')
})
