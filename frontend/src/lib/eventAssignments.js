import { requestJSON } from './api.js'

export function listUnassignedEventRequests() {
  return requestJSON('/event-requests/unassigned')
}

export function listAssignmentCoordinators() {
  return requestJSON('/event-requests/coordinators')
}

export function assignEventRequest(eventId, coordinatorId) {
  return requestJSON(`/event-requests/${encodeURIComponent(eventId)}/assignment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ coordinator_id: coordinatorId }),
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
