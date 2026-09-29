import { requestJSON } from './api.js'

export function canRequestTechnicalSupport(status) {
  return status === 'planning'
}

export function getTechnicalSupportAssignment(eventId) {
  return requestJSON(
    `/event-requests/${encodeURIComponent(eventId)}/technical-support-assignment`,
  )
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
