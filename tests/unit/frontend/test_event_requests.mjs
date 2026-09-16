import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createEventDraft,
  createSubmittedEvent,
  eventErrorMessage,
  eventFieldErrorsToForm,
  eventFormToPayload,
  eventResponseToForm,
  getEventRequest,
  listEventRequests,
  submitEventDraft,
  updateEventDraft,
} from '../../../frontend/src/lib/eventRequests.js'

const FORM = {
  id: 'client-id-must-not-be-sent',
  organiser_id: 'client-organiser-must-not-be-sent',
  status: 'submitted',
  name: '  Alumni evening  ',
  purpose: 'Connect alumni',
  startDate: '2026-10-20',
  startTime: '18:00',
  endDate: '2026-10-20',
  endTime: '21:00',
  attendance: '120',
  venue: 'Main auditorium',
  equipmentRequests: { projector: '2', microphone: '', chairs: '0' },
  accessibility: '  Wheelchair access  ',
  specialRequirements: '  Registration closes a week before  ',
  created_at: 'must-not-be-sent',
  updated_at: 'must-not-be-sent',
}

const API_EVENT = {
  id: '33333333-3333-4333-8333-333333333333',
  organiser_id: '11111111-1111-4111-8111-111111111111',
  status: 'draft',
  name: 'Alumni evening',
  purpose: 'Connect alumni',
  start_date: '2026-10-20',
  start_time: '18:00:00',
  end_date: '2026-10-20',
  end_time: '21:00:00',
  expected_attendance: 120,
  venue: 'Main auditorium',
  equipment_requests: { projector: 2 },
  accessibility_requirements: 'Wheelchair access',
  special_requirements: 'Registration closes a week before',
  submitted_at: null,
  created_at: '2026-09-14T00:00:00Z',
  updated_at: '2026-09-14T00:00:00Z',
}

test('form mapping uses the backend contract and omits server-owned fields', () => {
  assert.deepEqual(eventFormToPayload(FORM), {
    name: 'Alumni evening',
    purpose: 'Connect alumni',
    venue: 'Main auditorium',
    accessibility_requirements: 'Wheelchair access',
    special_requirements: 'Registration closes a week before',
    start_date: '2026-10-20',
    start_time: '18:00',
    end_date: '2026-10-20',
    end_time: '21:00',
    expected_attendance: 120,
    equipment_requests: { projector: 2 },
  })

  assert.deepEqual(eventFormToPayload({
    ...FORM,
    name: '',
    purpose: '',
    startDate: '',
    startTime: '',
    endDate: '',
    endTime: '',
    attendance: '',
    venue: '',
    accessibility: '',
    specialRequirements: '',
    equipmentRequests: {},
  }, { omitEmpty: true }), { equipment_requests: {} })
})

test('API responses populate the existing React state shape', () => {
  assert.deepEqual(eventResponseToForm(API_EVENT), {
    id: API_EVENT.id,
    name: 'Alumni evening',
    purpose: 'Connect alumni',
    startDate: '2026-10-20',
    startTime: '18:00',
    endDate: '2026-10-20',
    endTime: '21:00',
    attendance: '120',
    venue: 'Main auditorium',
    equipmentRequests: { projector: 2 },
    accessibility: 'Wheelchair access',
    specialRequirements: 'Registration closes a week before',
  })
})

test('event list loads the authenticated organisers saved requests', async () => {
  const originalFetch = globalThis.fetch
  let recordedCall
  globalThis.fetch = async (url, options = {}) => {
    recordedCall = { url, options }
    return new Response(JSON.stringify([API_EVENT]), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    assert.deepEqual(await listEventRequests(), [API_EVENT])
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(recordedCall.url, '/api/events')
  assert.equal(recordedCall.options.method, undefined)
  assert.equal(recordedCall.options.credentials, 'include')
})

test('event API functions use Kong paths, methods, JSON, and credentials', async () => {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify(API_EVENT), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    await createEventDraft(FORM)
    await updateEventDraft(API_EVENT.id, FORM)
    await createSubmittedEvent(FORM)
    await submitEventDraft(API_EVENT.id, FORM)
    await getEventRequest(API_EVENT.id)
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(({ url, options }) => [url, options.method ?? 'GET']), [
    ['/api/events/drafts', 'POST'],
    [`/api/events/${API_EVENT.id}`, 'PATCH'],
    ['/api/events', 'POST'],
    [`/api/events/${API_EVENT.id}/submit`, 'POST'],
    [`/api/events/${API_EVENT.id}`, 'GET'],
  ])
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
  assert.equal(JSON.parse(calls[0].options.body).organiser_id, undefined)
  assert.equal(JSON.parse(calls[0].options.body).status, undefined)
})

test('event API errors map to safe status and field feedback', () => {
  assert.deepEqual(eventFieldErrorsToForm({
    expected_attendance: 'Input should be greater than 0',
    'equipment_requests.projector': 'Input should be greater than 0',
    body: 'Value error, end_time must be after start_time',
  }), {
    attendance: 'Input should be greater than 0',
    equipmentRequests: 'Input should be greater than 0',
    endTime: 'End time must be after the start time.',
  })

  assert.deepEqual(eventFieldErrorsToForm({
    body: 'Value error, end_date must be on or after start_date',
  }), {
    endDate: 'End date must be on or after the start date.',
  })

  assert.match(eventErrorMessage({ status: 401 }), /session/i)
  assert.match(eventErrorMessage({ status: 403 }), /role/i)
  assert.match(eventErrorMessage({ status: 404 }), /not found/i)
  assert.equal(eventErrorMessage({ status: 409, message: 'Already submitted' }), 'Already submitted')
  assert.match(eventErrorMessage({ status: 422 }), /highlighted/i)
  assert.match(eventErrorMessage({ status: 500 }), /not been saved/i)
})
