import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createEventDraft,
  createSubmittedEvent,
  decideEventRequest,
  eventErrorMessage,
  eventFieldErrorsToForm,
  eventFormToPayload,
  eventInformationPayload,
  eventResponseToForm,
  eventStatusMeta,
  getEventOptions,
  getEventRequest,
  listEventRequests,
  previewAssignedEventInformation,
  organiserStatusMeta,
  organiserTabs,
  resubmitErrorMessage,
  sortEventsForOrganiser,
  submitEventDraft,
  updateAssignedEventInformation,
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
    special_requirements: 'Registration closes a week before',
    start_date: '2026-10-20',
    start_time: '18:00',
    end_date: '2026-10-20',
    end_time: '21:00',
    expected_attendance: 120,
    room_layout: null,
    required_facilities: [],
    required_accessibility: [],
    registration_required: false,
    registration_opens_at: null,
    registration_closes_at: null,
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
    specialRequirements: '',
  }, { omitEmpty: true }), {
    required_facilities: [],
    required_accessibility: [],
    registration_required: false,
  })
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
    specialRequirements: 'Registration closes a week before',
    roomLayout: '',
    requiredFacilities: [],
    requiredAccessibility: [],
    contactName: '',
    contactEmail: '',
    contactPhone: '',
    internalNotes: '',
    registrationRequired: false,
    registrationOpensDate: '',
    registrationOpensTime: '',
    registrationClosesDate: '',
    registrationClosesTime: '',
  })
})

test('S-18 coordinator mapping includes editable fields and omits server-owned state', () => {
  const event = { ...API_EVENT, edit_version: 4, edit_history: [{ change_number: 1 }] }
  const form = {
    ...eventResponseToForm(event),
    contactName: '  Sam Lee ',
    contactEmail: ' sam@example.com ',
    contactPhone: ' +65 6123 4567 ',
    internalNotes: ' Call on arrival ',
  }
  const payload = eventInformationPayload(form, event, { impactAccepted: true })
  assert.equal(payload.expected_version, 4)
  assert.equal(payload.impact_accepted, true)
  assert.equal(payload.contact_name, 'Sam Lee')
  assert.equal(payload.internal_notes, 'Call on arrival')
  assert.equal(payload.edit_history, undefined)
  assert.equal(payload.status, undefined)
  assert.equal(payload.safety_decision, undefined)
})

test('S-18 event information calls use encoded authenticated Kong routes', async () => {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ changed_fields: [], significant_fields: [] }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }
  const event = { ...API_EVENT, edit_version: 2 }
  const form = eventResponseToForm(event)
  try {
    await previewAssignedEventInformation('event 1/2', form, event)
    await updateAssignedEventInformation('event 1/2', form, event, true, ['venue:b1:capacity'])
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.deepEqual(calls.map(({ url, options }) => [url, options.method]), [
    ['/api/event-requests/event%201%2F2/information/impact', 'POST'],
    ['/api/event-requests/event%201%2F2/information/significant', 'PATCH'],
  ])
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
  assert.deepEqual(JSON.parse(calls[1].options.body).impact_ids, ['venue:b1:capacity'])
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
    // Update, submit, and submit-existing-draft all go through the
    // event_requests composite: update rechecks an assigned coordinator when
    // a submitted event's date/time changes, and the other two assign one
    // for the first time. Only create/read/list stay directly on events.
    [`/api/event-requests/${API_EVENT.id}`, 'PATCH'],
    ['/api/event-requests', 'POST'],
    [`/api/event-requests/${API_EVENT.id}/submit`, 'POST'],
    [`/api/events/${API_EVENT.id}`, 'GET'],
  ])
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
  assert.equal(JSON.parse(calls[0].options.body).organiser_id, undefined)
  assert.equal(JSON.parse(calls[0].options.body).status, undefined)
})

test('event API errors map to safe status and field feedback', () => {
  assert.deepEqual(eventFieldErrorsToForm({
    expected_attendance: 'Input should be greater than 0',
    body: 'Value error, end_time must be after start_time',
  }), {
    attendance: 'Input should be greater than 0',
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

// --- S-14: coordinator decisions -------------------------------------------

test('eventStatusMeta covers every backend status with a distinct label', () => {
  const statuses = ['draft', 'submitted', 'planning', 'returned', 'rejected']
  const seen = new Set()
  for (const status of statuses) {
    const { label, color } = eventStatusMeta(status)
    assert.equal(typeof label, 'string')
    assert.match(color, /^#[0-9a-f]{6}$/i)
    seen.add(label)
  }
  assert.equal(seen.size, statuses.length)
  // S-36: planning takes over the success color approved used.
  assert.deepEqual(eventStatusMeta('planning'), { label: 'Planning', color: '#3F8F5F' })
})

test('eventStatusMeta falls back safely for an unrecognised status', () => {
  const { label, color } = eventStatusMeta('made_up_status')
  assert.equal(label, 'made_up_status')
  assert.match(color, /^#[0-9a-f]{6}$/i)
})

test('decideEventRequest posts through the S-63 notification composite', async () => {
  let recorded
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    recorded = { url, options }
    return new Response(JSON.stringify({ id: 'event-1', status: 'approved' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    await decideEventRequest('event-1', { decision: 'approved' })
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(recorded.url, '/api/event-requests/event-1/decision')
  assert.equal(recorded.options.method, 'POST')
  assert.equal(recorded.options.credentials, 'include')
  assert.deepEqual(JSON.parse(recorded.options.body), { decision: 'approved' })
})

test('decideEventRequest omits reason and comment when not given', async () => {
  let body
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    body = JSON.parse(options.body)
    return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }

  try {
    await decideEventRequest('event-1', { decision: 'approved', reason: '', comment: undefined })
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(body, { decision: 'approved' })
})

test('decideEventRequest includes reason and comment when given', async () => {
  let body
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    body = JSON.parse(options.body)
    return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }

  try {
    await decideEventRequest('event-1', {
      decision: 'returned',
      reason: 'Missing risk assessment',
      comment: 'Please attach the fire safety form',
    })
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(body, {
    decision: 'returned',
    reason: 'Missing risk assessment',
    comment: 'Please attach the fire safety form',
  })
})

test('sortEventsForOrganiser sorts returned first, then submitted, then the rest, stable within each group', () => {
  const events = [
    { id: 'a', status: 'submitted' },
    { id: 'b', status: 'returned' },
    { id: 'c', status: 'draft' },
    { id: 'd', status: 'returned' },
    { id: 'e', status: 'planning' },
    { id: 'f', status: 'submitted' },
  ]

  const sorted = sortEventsForOrganiser(events)

  assert.deepEqual(sorted.map((event) => event.id), ['b', 'd', 'a', 'f', 'c', 'e'])
})

test('sortEventsForOrganiser is a no-op with neither priority status, and does not mutate its argument', () => {
  const events = [
    { id: 'a', status: 'draft' },
    { id: 'b', status: 'planning' },
    { id: 'c', status: 'draft' },
  ]

  const sorted = sortEventsForOrganiser(events)

  assert.deepEqual(sorted.map((event) => event.id), ['a', 'b', 'c'])
  assert.deepEqual(events.map((event) => event.id), ['a', 'b', 'c'])
})

test('organiserStatusMeta relabels returned as Action required, in rose', () => {
  const { label, color } = organiserStatusMeta('returned')
  assert.equal(label, 'Action required')
  assert.equal(color, '#B25547')
})

test('organiserStatusMeta relabels submitted as Under review, keeping the shared color', () => {
  const { label, color } = organiserStatusMeta('submitted')
  assert.equal(label, 'Under review')
  assert.equal(color, eventStatusMeta('submitted').color)
})

test('organiserStatusMeta falls through to the shared meta for every other status', () => {
  for (const status of ['draft', 'planning', 'rejected']) {
    assert.deepEqual(organiserStatusMeta(status), eventStatusMeta(status))
  }
})

// TC-FRONTEND-025
test('a failed resubmission tells the organiser nothing was changed', () => {
  const noCoordinator = 'No event coordinator is available for the requested date and time'
  const statusChanged = 'This request is no longer awaiting changes. Reload to see its current status.'

  assert.equal(
    resubmitErrorMessage({ status: 409, message: noCoordinator }),
    'No event coordinator is available for the requested date and time. Your request was not resubmitted. Try a different date or time.',
  )
  assert.equal(
    resubmitErrorMessage({ status: 409, message: statusChanged }),
    `${statusChanged} Nothing was resubmitted.`,
  )
  for (const status of [500, 502]) {
    assert.equal(
      resubmitErrorMessage({ status, message: 'Events service unavailable' }),
      'The event service is unavailable. Your request was not resubmitted and nothing was changed.',
    )
  }
  assert.equal(
    resubmitErrorMessage({ status: 0, message: "We couldn't reach the server. Check your connection and try again." }),
    "We couldn't reach the server. Your request was not resubmitted and nothing was changed.",
  )
  assert.equal(
    resubmitErrorMessage({ status: 422, message: 'Please check the details you entered' }),
    'Please check the highlighted event details.',
  )
})

const TAB_EVENTS = [
  { id: 'a', status: 'draft' },
  { id: 'b', status: 'rejected' },
  { id: 'c', status: 'planning' },
  { id: 'd', status: 'submitted' },
  { id: 'e', status: 'rejected' },
  { id: 'f', status: 'returned' },
]

// TC-FRONTEND-026
test('rejected requests go to the Rejected tab, everything else stays Active', () => {
  const input = TAB_EVENTS.map((event) => ({ ...event }))
  const [active, rejected] = organiserTabs(input)

  assert.deepEqual(active.events.map((event) => event.id), ['f', 'd', 'a', 'c'])
  assert.deepEqual(rejected.events.map((event) => event.id), ['b', 'e'])
  assert.deepEqual(input, TAB_EVENTS)
})

// TC-FRONTEND-027
test('tab labels carry counts, and each tab has its own empty message', () => {
  assert.deepEqual(
    organiserTabs(TAB_EVENTS).map((tab) => [tab.id, tab.label]),
    [['active', 'Active (4)'], ['rejected', 'Rejected (2)']],
  )

  const draftOnly = organiserTabs([{ id: 'a', status: 'draft' }])
  assert.deepEqual(draftOnly.map((tab) => tab.label), ['Active (1)', 'Rejected (0)'])
  assert.equal(draftOnly[1].emptyMessage, 'No rejected requests.')

  const none = organiserTabs([])
  assert.deepEqual(none.map((tab) => tab.label), ['Active (0)', 'Rejected (0)'])
  assert.equal(none[0].emptyMessage, 'You have no saved event requests yet.')
})

// --- S-36: venue requirements on the event ----------------------------------

// TC-FRONTEND-033
test("the organiser's venue requirements map both ways", () => {
  const withRequirements = {
    ...FORM,
    venue: '',
    roomLayout: 'theatre',
    requiredFacilities: ['projector'],
    requiredAccessibility: ['lift'],
  }
  const payload = eventFormToPayload(withRequirements)
  assert.equal(payload.room_layout, 'theatre')
  assert.deepEqual(payload.required_facilities, ['projector'])
  assert.deepEqual(payload.required_accessibility, ['lift'])
  assert.equal(payload.venue, null)

  assert.equal(eventFormToPayload({ ...withRequirements, roomLayout: '' }).room_layout, null)
  assert.equal(
    'room_layout' in eventFormToPayload({ ...withRequirements, roomLayout: '' }, { omitEmpty: true }),
    false,
  )

  const form = eventResponseToForm({
    ...API_EVENT,
    room_layout: 'banquet',
    required_facilities: ['stage'],
    required_accessibility: [],
    venue: null,
  })
  assert.equal(form.roomLayout, 'banquet')
  assert.deepEqual(form.requiredFacilities, ['stage'])
  assert.deepEqual(form.requiredAccessibility, [])
  assert.equal(form.venue, '')
})

// TC-FRONTEND-034
test('organisers load the option lists from the events service', async () => {
  const calls = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ room_layouts: [], facilities: [], accessibility: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  try {
    await getEventOptions()
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/events/options')
  assert.equal(calls[0].options.method ?? 'GET', 'GET')
  assert.equal(calls[0].options.credentials, 'include')
})
