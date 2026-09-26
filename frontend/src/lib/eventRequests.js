import { requestJSON } from './api.js'

const TEXT_FIELDS = {
  name: 'name',
  purpose: 'purpose',
  venue: 'venue',
  accessibility: 'accessibility_requirements',
  specialRequirements: 'special_requirements',
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
  special_requirements: 'specialRequirements',
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
    specialRequirements: event.special_requirements ?? '',
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

// Shared status display across the organiser and coordinator views. Colors
// are the project's fixed tokens (see AGENTS.md's design system), not
// page-local -- draft and submitted are both "not decided yet" (inkFaint /
// amber), planning (approved, arrangements underway) is the one success
// color, rejected and returned both need attention but are not errors in
// the same way, so returned reuses
// amber ("needs the organiser's action") rather than rose ("closed, wrong").
const STATUS_META = {
  draft: { label: 'Draft', color: '#4C5A70' },
  submitted: { label: 'Under Review', color: '#B5842B' },
  planning: { label: 'Planning', color: '#3F8F5F' },
  returned: { label: 'Action Required', color: '#B5842B' },
  rejected: { label: 'Rejected', color: '#B25547' },
}

export function eventStatusMeta(status) {
  return STATUS_META[status] ?? { label: status, color: '#4C5A70' }
}

// Organiser-only label and color treatment for the two statuses that
// dashboard cares about most (see sortEventsForOrganiser). The
// coordinator-facing shared meta above keeps its own wording and colors for
// both -- from the organiser's side, a returned request needs *their*
// action (rose, matching the same "needs attention" red used for rejected)
// and a submitted one is simply under someone else's review, so this
// reframes both without changing what a coordinator sees. draft/planning/
// rejected are untouched -- they fall through to the shared meta unchanged.
const ORGANISER_STATUS_OVERRIDES = {
  returned: { label: 'Action required', color: '#B25547' },
  submitted: { label: 'Under review' },
}

export function organiserStatusMeta(status) {
  const shared = eventStatusMeta(status)
  const override = ORGANISER_STATUS_OVERRIDES[status]
  return override ? { ...shared, ...override } : shared
}

// Surfaces requests the organiser cares about most at the top of their own
// request list: 'returned' (sent back for amendment -- the one status that
// needs the organiser to act) first, then 'submitted' (awaiting the
// coordinator's decision), then everything else. Stable within each group:
// the backend already orders by updated_at desc (see GET /events), so this
// only reorders across the three groups, never within one. Does not mutate
// its argument.
export function sortEventsForOrganiser(events) {
  const returned = events.filter((event) => event.status === 'returned')
  const submitted = events.filter((event) => event.status === 'submitted')
  const rest = events.filter((event) => event.status !== 'submitted' && event.status !== 'returned')
  return [...returned, ...submitted, ...rest]
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

// The organiser dashboard's two tabs. A rejected request is closed for good
// and can never be edited or resubmitted, so it moves out of the working
// list into its own tab; everything else -- including planning, which is
// still a live event -- stays Active, in sortEventsForOrganiser's order.
export function organiserTabs(events) {
  const active = sortEventsForOrganiser(events.filter((event) => event.status !== 'rejected'))
  const rejected = events.filter((event) => event.status === 'rejected')
  return [
    {
      id: 'active',
      label: `Active (${active.length})`,
      events: active,
      emptyMessage: 'You have no saved event requests yet.',
    },
    {
      id: 'rejected',
      label: `Rejected (${rejected.length})`,
      events: rejected,
      emptyMessage: 'No rejected requests.',
    },
  ]
}

const NO_COORDINATOR_AVAILABLE = 'No event coordinator is available for the requested date and time'

// S-13: a returned request the organiser is responding to. Every way the
// resubmission can fail has to say it was not resubmitted, so the organiser
// knows the request is still waiting on them and nothing they saved before
// was changed -- the backend guarantees that; this is what tells them.
export function resubmitErrorMessage(error) {
  if (error.status === 409 && error.message === NO_COORDINATOR_AVAILABLE) {
    return `${NO_COORDINATOR_AVAILABLE}. Your request was not resubmitted. Try a different date or time.`
  }
  if (error.status === 409 && error.message) return `${error.message} Nothing was resubmitted.`
  if (error.status >= 500) {
    return 'The event service is unavailable. Your request was not resubmitted and nothing was changed.'
  }
  if (error.status === 0) {
    return "We couldn't reach the server. Your request was not resubmitted and nothing was changed."
  }
  return eventErrorMessage(error)
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

// Coordinator-facing, read-only: events routed to the signed-in coordinator.
export function listAssignedEventRequests() {
  return requestJSON('/events/assigned')
}

export function getAssignedEventRequest(id) {
  return requestJSON(`/events/assigned/${encodeURIComponent(id)}`)
}

export function createEventDraft(form) {
  return write('/events/drafts', 'POST', form, true)
}

// Routed through event_requests, not the events service directly: editing an
// already-submitted event's date/time has to recheck the assigned
// coordinator's availability, which needs the same cross-service logic as
// submission. A draft, or an edit that leaves date/time alone, is a plain
// passthrough on the composite's side -- see PATCH /event-requests/{id}.
export function updateEventDraft(id, form) {
  return write(`/event-requests/${encodeURIComponent(id)}`, 'PATCH', form)
}

// Submission goes through the event_requests composite too, for the same
// reason: it is what assigns a free event coordinator as part of submitting.
// Draft create/read/list above stay on the events service directly -- a
// brand-new draft has no coordinator to check yet.
export function createSubmittedEvent(form) {
  return write('/event-requests', 'POST', form)
}

export function submitEventDraft(id, form) {
  return write(`/event-requests/${encodeURIComponent(id)}/submit`, 'POST', form)
}

// Coordinator-facing: record a decision on an assigned, submitted request.
// Straight to the events service -- unlike submit/update, a decision never
// touches assignment, so there is nothing for the composite to orchestrate.
export function decideEventRequest(id, { decision, reason, comment }) {
  const body = { decision }
  if (reason) body.reason = reason
  if (comment) body.comment = comment
  return requestJSON(`/events/${encodeURIComponent(id)}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
