import { getRoleAccess } from './access.js'
import { requestJSON } from './api.js'

// S-82: an event's change history -- who changed or decided what, and when.
// The Coordinator and the Lead read it through event_requests; the Safety
// Officer reads the safety review's part of it through safety_checks.
const HISTORY_ROUTES = {
  event_coordinator: (id) => `/event-requests/${id}/history`,
  event_coordinator_lead: (id) => `/event-requests/${id}/history`,
  safety_officer: (id) => `/safety-checks/${id}/history`,
}

export function historyPath(role, eventId) {
  return HISTORY_ROUTES[role]?.(eventId) ?? null
}

export function loadEventHistory(role, eventId) {
  const path = historyPath(role, eventId)
  if (!path) return Promise.reject(new Error('Your role has no access to event history.'))
  return requestJSON(path)
}

// Times are shown in Singapore time whatever the viewer's own timezone, the
// same as every other date in the app.
const SINGAPORE_OFFSET_MS = 8 * 60 * 60 * 1000
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function clock(hours, minutes) {
  const suffix = hours < 12 ? 'am' : 'pm'
  return `${hours % 12 || 12}:${String(minutes).padStart(2, '0')} ${suffix}`
}

function day(isoDate) {
  const [year, month, date] = isoDate.split('-').map(Number)
  return `${date} ${MONTHS[month - 1]} ${year}`
}

export function entryTime(entry) {
  const local = new Date(new Date(entry.occurred_at).getTime() + SINGAPORE_OFFSET_MS)
  const isoDate = local.toISOString().slice(0, 10)
  return `${day(isoDate)}, ${clock(local.getUTCHours(), local.getUTCMinutes())}`
}

const REMOVED = 'a removed account'

export function entryActor(entry) {
  if (!entry.actor) return 'Not recorded'
  const role = getRoleAccess(entry.actor.role)?.label ?? entry.actor.role
  const name = entry.actor.name || 'A removed account'
  return role ? `${name}, ${role}` : name
}

function person(people, id) {
  return people?.[id] || REMOVED
}

function withReason(sentence, details) {
  return details?.reason ? `${sentence}: ${details.reason}` : sentence
}

function humanise(text) {
  const words = String(text).replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

const PREPARATION = { not_started: 'Not started', in_progress: 'In progress', ready: 'Ready' }

const SENTENCES = {
  submitted: (d) => (d.resubmission ? 'Resubmitted the event request' : 'Submitted the event request'),
  edited: () => 'Edited the event',
  change_request_accepted: () => 'Accepted the event change request after impact review',
  change_request_rejected: (d) => `Rejected the event change request: ${d.reason || 'No reason recorded'}`,
  change_impact_resolved: (d) => `Resolved arrangement impact ${d.impact_id || ''}: ${d.action || 'reviewed'}`,
  request_approved: () => 'Approved the event request',
  request_rejected: (d) => withReason('Rejected the event request', d),
  request_returned: (d) => withReason('Returned the event request', d),
  cancellation_requested: (d) => withReason('Asked to cancel the event', d),
  cancellation_approved: (d) => withReason('Approved the cancellation', d),
  cancellation_declined: (d) => withReason('Declined the cancellation', d),
  cancelled_venue_unavailable: (d) => {
    const sentence = withReason('Cancelled the event as no alternative venue could be found', d)
    return d.alternatives_considered
      ? `${sentence}. Alternatives considered: ${d.alternatives_considered}`
      : sentence
  },
  coordinator_assigned: (d, p) => `Assigned ${person(p, d.coordinator_id)}`,
  reassignment_requested: (d) => withReason('Asked to be reassigned', d),
  coordinator_reassigned: (d, p) =>
    `Reassigned from ${person(p, d.from_coordinator_id)} to ${person(p, d.to_coordinator_id)}`,
  technical_support_assigned: (d, p) => `Assigned ${person(p, d.technical_support_id)} to technical support`,
  technical_signoff_approved: () => 'Signed off the equipment',
  technical_signoff_declined: (d) => withReason('Declined the equipment sign-off', d),
  equipment_preparation_changed: (d) => `Set equipment preparation to ${PREPARATION[d.to] ?? humanise(d.to)}`,
  equipment_requirement_set: (d) => (d.from_quantity == null
    ? `Added ${d.item_name}, quantity ${d.to_quantity}`
    : `Changed ${d.item_name} from ${d.from_quantity} to ${d.to_quantity}`),
  equipment_requirement_removed: (d) => `Removed ${d.item_name}`,
  venue_requested: (d) => `Requested ${d.venue_name}`,
  venue_request_changed: (d) => `Changed the request for ${d.venue_name}`,
  venue_request_withdrawn: (d) => `Withdrew the request for ${d.venue_name}`,
  venue_replacement_requested: (d) => `Requested ${d.venue_name} to replace ${d.replaced_venue_name}`,
  venue_alternative_resolved: (d) => `Arranged an alternative for ${d.venue_name}`,
  venue_held: (d) => `Held ${d.venue_name}`,
  venue_released: (d) => `Released the hold on ${d.venue_name}`,
  venue_confirmed: (d) => `Confirmed ${d.venue_name}`,
  venue_rejected: (d) => withReason(`Rejected ${d.venue_name}`, d),
  safety_submitted: () => 'Submitted for the safety check',
  safety_resubmitted: () => 'Resubmitted for the safety check',
  safety_approved: () => 'Approved the safety check',
  safety_changes_requested: (d) => withReason('Requested safety changes', d),
  safety_rejected: (d) => withReason('Rejected the safety check', d),
}

export const HISTORY_ACTIONS = Object.freeze(Object.keys(SENTENCES))

export function describeEntry(entry, people = {}) {
  const sentence = SENTENCES[entry.action]
  return sentence ? sentence(entry.details ?? {}, people) : humanise(entry.action)
}

const FIELD_LABELS = {
  name: 'Name',
  purpose: 'Purpose',
  contact_name: 'Contact name',
  contact_email: 'Contact email',
  contact_phone: 'Contact phone',
  internal_notes: 'Internal notes',
  start_date: 'Start date',
  start_time: 'Start time',
  end_date: 'End date',
  end_time: 'End time',
  expected_attendance: 'Expected attendance',
  venue: 'Venue preference',
  special_requirements: 'Special requirements',
  room_layout: 'Room layout',
  required_facilities: 'Facilities',
  required_accessibility: 'Accessibility',
  assigned_coordinator_id: 'Coordinator',
}

function value(field, raw, people) {
  if (raw == null || raw === '' || (Array.isArray(raw) && raw.length === 0)) return '(none)'
  if (Array.isArray(raw)) return raw.map(humanise).join(', ')
  if (field === 'assigned_coordinator_id') return person(people, raw)
  if (field.endsWith('_date')) return day(String(raw))
  if (field.endsWith('_time')) {
    const [hours, minutes] = String(raw).split(':').map(Number)
    return clock(hours, minutes)
  }
  if (field === 'room_layout') return humanise(raw)
  return String(raw)
}

// One line per changed field: "Expected attendance: 120 → 150".
export function describeChanges(changes, people = {}) {
  return Object.entries(changes ?? {}).map(([field, change]) => {
    const label = FIELD_LABELS[field] ?? humanise(field)
    return `${label}: ${value(field, change.before, people)} → ${value(field, change.after, people)}`
  })
}

function slot(times) {
  const [startDate, startTime] = times.start.split('T')
  const endTime = times.end.split('T')[1]
  const [sh, sm] = startTime.split(':').map(Number)
  const [eh, em] = endTime.split(':').map(Number)
  return `${times.venue_name ? `${times.venue_name}, ` : ''}${day(startDate)}, ${clock(sh, sm)} to ${clock(eh, em)}`
}

// The detail lines shown under an entry's sentence.
export function entryLines(entry, people = {}) {
  const details = entry.details ?? {}
  if (entry.action === 'edited') return describeChanges(details.changes, people)
  if (entry.action === 'venue_request_changed' && details.from && details.to) {
    return [`${slot(details.from)} → ${slot(details.to)}`]
  }
  if (entry.action === 'request_returned' && details.comment) return [details.comment]
  if (details.backfilled) return ['Rebuilt from the event’s earlier records']
  return []
}
