import { requestJSON } from './api.js'

export function canRequestTechnicalSupport(status) {
  return status === 'planning'
}

export function getTechnicalSupportAssignment(eventId) {
  return requestJSON(
    `/event-requests/${encodeURIComponent(eventId)}/technical-support-assignment`,
  )
}

export function listTechnicalSupportEvents() {
  return requestJSON('/events/support-assigned')
}

export function getTechnicalSupportEvent(eventId) {
  return requestJSON(`/events/support-assigned/${encodeURIComponent(eventId)}`)
}

export const EQUIPMENT_PREPARATION_OPTIONS = Object.freeze([
  Object.freeze({ value: 'not_started', label: 'Not Started' }),
  Object.freeze({ value: 'in_progress', label: 'In Progress' }),
  Object.freeze({ value: 'ready', label: 'Ready' }),
])

export function equipmentPreparationLabel(status) {
  return EQUIPMENT_PREPARATION_OPTIONS.find((option) => option.value === status)?.label
    ?? status
    ?? 'Not Started'
}

export function updateEquipmentPreparation(eventId, status) {
  return requestJSON(
    `/events/support-assigned/${encodeURIComponent(eventId)}/equipment-preparation`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    },
  )
}

export function equipmentPreparationErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Your role is not permitted to update equipment preparation.'
  if (error.status === 404) return 'This event was not found or is no longer assigned to you.'
  if (error.status === 409) return error.message || 'The event changed. Reload and try again.'
  if (error.status >= 500) return 'The preparation status was not saved. Try again in a moment.'
  return error.message || "We couldn't save the preparation status."
}

export function assignedEventWork(events, requirements) {
  const activeEvents = events.filter((event) => (
    event.status === 'planning' || event.status === 'confirmed' || event.status === 'preparation'
  ))
  const byEvent = new Map(activeEvents.map((event) => [event.id, []]))

  for (const requirement of requirements) {
    if (byEvent.has(requirement.event_id)) {
      byEvent.get(requirement.event_id).push(requirement)
    }
  }

  return activeEvents.map((event) => ({
    ...event,
    equipment_requirements: byEvent.get(event.id),
  }))
}

export function technicalSupportWorkErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Your role is not permitted to view Technical Support assignments.'
  if (error.status === 404) return 'This event was not found or is no longer assigned to you.'
  if (error.status >= 500) return 'Your assigned events are temporarily unavailable. Try again in a moment.'
  return error.message || "We couldn't load your assigned events. Try again in a moment."
}

export function requestTechnicalSupportAssignment(eventId, supportDetails) {
  const details = supportDetails?.trim() ?? ''
  return requestJSON(
    `/event-requests/${encodeURIComponent(eventId)}/technical-support-assignment`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ support_details: details || null }),
    },
  )
}

export function technicalSupportAssignmentErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Your role is not permitted to request Technical Support.'
  if (error.status === 404) return 'This event was not found or is not assigned to you.'
  if (error.status === 409) return error.message || 'Technical Support can only be requested while the event is in planning.'
  if (error.status >= 500) return 'The assignment service is unavailable. Your request has not been saved.'
  return error.message || "We couldn't reach the assignment service. Your request has not been saved."
}
