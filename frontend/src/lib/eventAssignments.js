import { requestJSON } from './api.js'

export function listUnassignedEventRequests() {
  return requestJSON('/event-requests/unassigned')
}

export function listAssignmentCoordinators() {
  return requestJSON('/event-requests/coordinators')
}

export function coordinatorOptionLabel(coordinator) {
  return coordinator.email || coordinator.name
}

export function listActiveAssignments() {
  return requestJSON('/event-requests/assigned-active')
}

export function listCoordinatorOverview() {
  return requestJSON('/event-requests/coordinator-overview')
}

export function listCoordinatorActiveEvents(coordinatorId) {
  return requestJSON(`/event-requests/coordinators/${encodeURIComponent(coordinatorId)}/active-events`)
}

export function moveAssignmentInOverview(groups, updatedEvent, targetCoordinator) {
  let currentEvent = null
  const withoutEvent = groups.map((group) => {
    const matched = group.events.find((event) => event.id === updatedEvent.id)
    if (matched) currentEvent = matched
    const events = group.events.filter((event) => event.id !== updatedEvent.id)
    return { ...group, events, active_assignment_count: events.length }
  })

  if (!currentEvent) return withoutEvent

  const moved = {
    ...currentEvent,
    ...updatedEvent,
    coordinator: targetCoordinator,
  }
  return withoutEvent.map((group) => {
    if (group.coordinator.id !== targetCoordinator.id) return group
    const events = [moved, ...group.events]
    return { ...group, events, active_assignment_count: events.length }
  })
}

export function assignEventRequest(eventId, coordinatorId) {
  return requestJSON(`/event-requests/${encodeURIComponent(eventId)}/assignment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ coordinator_id: coordinatorId }),
  })
}

export function reassignEvent(eventId, coordinatorId, expectedCoordinatorId, expectedAssignmentVersion) {
  return requestJSON(`/event-requests/${encodeURIComponent(eventId)}/reassignment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      coordinator_id: coordinatorId,
      expected_coordinator_id: expectedCoordinatorId,
      expected_assignment_version: expectedAssignmentVersion,
    }),
  })
}

export function assignmentErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Only an Event Coordinator Lead can assign requests.'
  if (error.status === 404) return 'This event request no longer exists.'
  if (error.status === 409) return error.message || 'This request was assigned by another Lead.'
  if (error.status === 422) return error.message || 'Choose a valid Event Coordinator.'
  if (error.status >= 500) return 'Assignment services are temporarily unavailable. Please retry.'
  return error.message || "We couldn't assign this request."
}

export function reassignmentErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Only an Event Coordinator Lead can reassign events.'
  if (error.status === 404) return 'This event no longer exists.'
  if (error.status === 409) return error.message || 'This assignment changed. Reload before trying again.'
  if (error.status === 422) return error.message || 'Choose a different valid Event Coordinator.'
  if (error.status >= 500) return 'Reassignment services are temporarily unavailable. Please retry.'
  return error.message || "We couldn't reassign this event."
}

export function overviewErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Only an Event Coordinator Lead can view coordinator oversight.'
  if (error.status >= 500) return 'Coordinator oversight is temporarily unavailable. Please retry.'
  return error.message || "We couldn't load coordinator oversight."
}
