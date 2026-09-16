import { requestJSON } from './api.js'

const TEXT_FIELDS = {
  name: 'name',
  purpose: 'purpose',
  venue: 'venue',
  accessibility: 'accessibility_requirements',
}

const VALUE_FIELDS = {
  startDate: 'start_date',
  startTime: 'start_time',
  endDate: 'end_date',
  endTime: 'end_time',
}

const API_TO_FORM_FIELD = {
  name: 'name',
  purpose: 'purpose',
  start_date: 'startDate',
  start_time: 'startTime',
  end_date: 'endDate',
  end_time: 'endTime',
  expected_attendance: 'attendance',
  venue: 'venue',
  equipment_requests: 'equipmentRequests',
  accessibility_requirements: 'accessibility',
}

function equipmentPayload(equipmentRequests = {}) {
  return Object.fromEntries(
    Object.entries(equipmentRequests)
      .filter(([, quantity]) => quantity !== '' && Number(quantity) > 0)
      .map(([name, quantity]) => [name, Number(quantity)]),
  )
}

export function eventFormToPayload(form, { omitEmpty = false } = {}) {
  const payload = {}

  for (const [formField, apiField] of Object.entries(TEXT_FIELDS)) {
    const value = form[formField]?.trim() ?? ''
    if (value) payload[apiField] = value
    else if (!omitEmpty) payload[apiField] = null
  }

  for (const [formField, apiField] of Object.entries(VALUE_FIELDS)) {
    const value = form[formField] || null
    if (value !== null || !omitEmpty) payload[apiField] = value
  }

  if (form.attendance !== '') {
    payload.expected_attendance = Number(form.attendance)
  } else if (!omitEmpty) {
    payload.expected_attendance = null
  }

  payload.equipment_requests = equipmentPayload(form.equipmentRequests)
  return payload
}

export function eventResponseToForm(event) {
  return {
    id: event.id,
    name: event.name ?? '',
    purpose: event.purpose ?? '',
    startDate: event.start_date ?? '',
    startTime: event.start_time?.slice(0, 5) ?? '',
    endDate: event.end_date ?? '',
    endTime: event.end_time?.slice(0, 5) ?? '',
    attendance: event.expected_attendance?.toString() ?? '',
    venue: event.venue ?? '',
    equipmentRequests: event.equipment_requests ?? {},
    accessibility: event.accessibility_requirements ?? '',
  }
}

export function eventFieldErrorsToForm(fieldErrors) {
  const mapped = {}
  for (const [path, message] of Object.entries(fieldErrors ?? {})) {
    const apiField = path.split('.')[0]
    const formField = API_TO_FORM_FIELD[apiField]
    if (formField) mapped[formField] = message
    else if (message.includes('end_time must be after start_time')) {
      mapped.endTime = 'End time must be after the start time.'
    } else if (message.includes('end_date must be on or after start_date')) {
      mapped.endDate = 'End date must be on or after the start date.'
    }
  }
  return mapped
}

export function eventErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Your role is not permitted to access event requests.'
  if (error.status === 404) return 'This event request was not found or does not belong to you.'
  if (error.status === 409) return error.message || 'This event is no longer an editable draft.'
  if (error.status === 422) return 'Please check the highlighted event details.'
  if (error.status >= 500) return 'The event service is unavailable. Your changes have not been saved.'
  return error.message || "We couldn't reach the event service. Your changes have not been saved."
}

function write(path, method, form, omitEmpty = false) {
  return requestJSON(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(eventFormToPayload(form, { omitEmpty })),
  })
}

export function getEventRequest(id) {
  return requestJSON(`/events/${encodeURIComponent(id)}`)
}

export function listEventRequests() {
  return requestJSON('/events')
}

export function createEventDraft(form) {
  return write('/events/drafts', 'POST', form, true)
}

export function updateEventDraft(id, form) {
  return write(`/events/${encodeURIComponent(id)}`, 'PATCH', form)
}

export function createSubmittedEvent(form) {
  return write('/events', 'POST', form)
}

export function submitEventDraft(id, form) {
  return write(`/events/${encodeURIComponent(id)}/submit`, 'POST', form)
}
