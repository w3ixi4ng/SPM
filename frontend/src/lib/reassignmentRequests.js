import { requestJSON } from './api.js'

export function requestReassignment(eventId, reason) {
  return requestJSON(`/event-requests/${encodeURIComponent(eventId)}/reassignment-request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason.trim() }),
  })
}

export function listMyReassignmentRequests() {
  return requestJSON('/event-requests/reassignment-requests/mine')
}

export function listLeadReassignmentRequests() {
  return requestJSON('/event-requests/reassignment-requests/lead')
}

export function reassignmentRequestError(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403 || error.status === 404) return 'This event is no longer assigned to you.'
  if (error.status === 409) return error.message || 'This assignment changed. Reload and try again.'
  if (error.status === 422) return 'Enter a reason for the request.'
  return 'Reassignment requests are unavailable. Try again.'
}
