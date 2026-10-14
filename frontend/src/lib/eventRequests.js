import { requestJSON } from './api.js'

const TEXT_FIELDS = {
  name: 'name',
  purpose: 'purpose',
  venue: 'venue',
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
  special_requirements: 'specialRequirements',
  room_layout: 'roomLayout',
  required_facilities: 'requiredFacilities',
  required_accessibility: 'requiredAccessibility',
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

  // S-36: the venue requirements. The two lists are always sent; a blank
  // layout is null, or left out of a partial draft.
  const layout = form.roomLayout || null
  if (layout !== null || !omitEmpty) payload.room_layout = layout
  payload.required_facilities = [...(form.requiredFacilities ?? [])]
  payload.required_accessibility = [...(form.requiredAccessibility ?? [])]
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
    specialRequirements: event.special_requirements ?? '',
    roomLayout: event.room_layout ?? '',
    requiredFacilities: event.required_facilities ?? [],
    requiredAccessibility: event.required_accessibility ?? [],
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
  confirmed: { label: 'Confirmed', color: '#3F8F5F' },
  preparation: { label: 'Preparation', color: '#3F8F5F' },
  safety_rejected: { label: 'Safety Rejected', color: '#B25547' },
  safety_changes_requested: { label: 'Safety Changes Requested', color: '#B5842B' },
  returned: { label: 'Action Required', color: '#B5842B' },
  rejected: { label: 'Rejected', color: '#B25547' },
  // S-61: approved by the assigned Coordinator. Neutral, not an error.
  cancelled: { label: 'Cancelled', color: '#4C5A70' },
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

// S-36: the venue requirement option sets for the organiser's form. Served
// by the events service -- organisers cannot view venues.
export function getEventOptions() {
  return requestJSON('/events/options')
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

// S-62: an Organiser asks for a live event to be cancelled. The request is
// stored on the event and its status does not change -- the event is only
// cancelled once a later review completes it. Mirrors the events service's
// _CANCELLABLE_STATUSES, which stays authoritative.
const CANCELLABLE_STATUSES = new Set([
  'submitted', 'under_review', 'planning', 'confirmed', 'preparation', 'safety_changes_requested',
])
export const CANCELLATION_REASON_MAX = 1000

// S-61: a request is pending until the assigned Coordinator decides it.
function cancellationPending(event) {
  return Boolean(event?.cancellation_requested_at) && !event?.cancellation_decision
}

// S-61: after a decline the Organiser may ask again.
export function canRequestCancellation(event) {
  if (!CANCELLABLE_STATUSES.has(event?.status)) return false
  return !event?.cancellation_requested_at || event?.cancellation_decision === 'declined'
}

function dayLabel(value) {
  return new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function cancellationRequestedLabel(event) {
  if (!event?.cancellation_requested_at) return null
  return `Cancellation requested on ${dayLabel(event.cancellation_requested_at)}`
}

export function cancellationApprovedLabel(event) {
  if (event?.cancellation_decision !== 'approved' || !event?.cancellation_decided_at) return null
  return `Cancelled on ${dayLabel(event.cancellation_decided_at)}`
}

export function cancellationDeclinedLabel(event) {
  if (event?.cancellation_decision !== 'declined' || !event?.cancellation_decided_at) return null
  return `Cancellation declined on ${dayLabel(event.cancellation_decided_at)}`
}

// The dashboard's tag beside the status badge. A separate tag, never a
// status: the event keeps its own status until the request is reviewed. An
// approved request needs no tag -- the status already reads Cancelled.
export function organiserCancellationTag(event) {
  if (cancellationPending(event)) return 'Cancellation requested'
  if (event?.cancellation_decision === 'declined') return 'Cancellation declined'
  return null
}

// S-61: the Coordinator's side.
export function canDecideCancellation(event) {
  return cancellationPending(event)
}

export function coordinatorCancellationTag(event) {
  return cancellationPending(event) ? 'Cancellation requested' : null
}

export function validateCancellationReason(reason) {
  const trimmed = (reason ?? '').trim()
  if (!trimmed) return 'Enter a reason for cancelling.'
  if (trimmed.length > CANCELLATION_REASON_MAX) return 'Keep the reason to 1000 characters.'
  return null
}

export function cancellationSentMessage(status) {
  const label = organiserStatusMeta(status).label.toLowerCase()
  return `Cancellation request sent. Your event stays in ${label} until it has been reviewed.`
}

const UNCHANGED = 'Your event has not changed.'

export function cancellationErrorMessage(error) {
  if (error.status === 409 && error.message) return `${error.message} ${UNCHANGED}`
  if (error.status === 422) return `Enter a reason of up to 1000 characters. ${UNCHANGED}`
  if (error.status === 404) return `This event was not found or does not belong to you. ${UNCHANGED}`
  if (error.status === 401) return `Your session has expired. Sign in again and retry. ${UNCHANGED}`
  if (error.status === 403) return `Your role can't request cancellations. ${UNCHANGED}`
  if (error.status === 0) return `We couldn't reach the server. Check your connection and try again. ${UNCHANGED}`
  return `The cancellation request couldn't be sent. Try again in a moment. ${UNCHANGED}`
}

export function requestEventCancellation(id, reason) {
  return requestJSON(`/events/${encodeURIComponent(id)}/cancellation-request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason.trim() }),
  })
}

// S-61: the assigned Coordinator's decision. Through the event_requests
// composite, which also releases the event's venue bookings on approval.
export function decideCancellation(id, { decision, reason = '' }) {
  const body = { decision }
  if (decision === 'declined') body.reason = reason.trim()
  return requestJSON(`/event-requests/${encodeURIComponent(id)}/cancellation-decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function validateDeclineReason(reason) {
  const trimmed = (reason ?? '').trim()
  if (!trimmed) return 'Enter a reason for declining.'
  if (trimmed.length > CANCELLATION_REASON_MAX) return 'Keep the reason to 1000 characters.'
  return null
}

export function cancellationApprovalSummary(bookingCount) {
  const venue = bookingCount === 0
    ? 'No venue bookings to release.'
    : bookingCount === 1
      ? '1 venue booking will be removed and its time freed.'
      : `${bookingCount} venue bookings will be removed and their times freed.`
  return `${venue} Equipment reserved for this event is freed.`
}

export function cancellationApprovedNotice(released) {
  if (!released) return 'Event cancelled. It had no venue bookings to release.'
  return released === 1
    ? 'Event cancelled. 1 venue booking was released.'
    : `Event cancelled. ${released} venue bookings were released.`
}

const NOTHING_CHANGED = 'Nothing was changed.'

// 409 and 502 carry the service's own explanation -- a 502 after approval
// says the event is cancelled but its bookings weren't released, which is
// exactly what the Coordinator needs to read.
export function cancellationDecisionErrorMessage(error) {
  if ((error.status === 409 || error.status === 502) && error.message) return error.message
  if (error.status === 422) return `Enter a reason of up to 1000 characters. ${NOTHING_CHANGED}`
  if (error.status === 404) return `This event was not found or is not assigned to you. ${NOTHING_CHANGED}`
  if (error.status === 401) return `Your session has expired. Sign in again and retry. ${NOTHING_CHANGED}`
  if (error.status === 403) return `Your role can't decide cancellation requests. ${NOTHING_CHANGED}`
  if (error.status === 0) return `We couldn't reach the server. Check your connection and try again. ${NOTHING_CHANGED}`
  return `The decision couldn't be saved. Try again in a moment. ${NOTHING_CHANGED}`
}

// The Organiser's banner about the decision on their request, by status.
// Null means no banner: before a decision there is nothing to say, and a
// cancelled event is explained by its cancellation section instead. Every
// status that shows a banner has words, so it is never an empty box.
const DECISION_BANNER = {
  planning: 'This request has been approved and is in planning.',
  confirmed: 'This request has been approved and the event is confirmed.',
  preparation: 'This request has been approved and the event is in preparation.',
  safety_rejected: 'This request was approved, but the event did not pass its safety check.',
  safety_changes_requested: 'This request was approved, but its safety check asked for changes.',
  rejected: 'This request has been rejected and is closed.',
  returned: 'This request was returned for amendment. Fix the issue below, then resubmit.',
}

export function organiserDecisionBanner(status) {
  return DECISION_BANNER[status] ?? null
}
