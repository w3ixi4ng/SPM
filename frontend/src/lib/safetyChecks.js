import { requestJSON } from './api.js'


export function listSafetyChecks() {
  return requestJSON('/safety-checks')
}


export function getSafetyCheck(eventId) {
  return requestJSON(`/safety-checks/${eventId}`)
}


export function decideSafetyCheck(eventId, decision) {
  return requestJSON(`/safety-checks/${eventId}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(decision),
  })
}


export function getReturnedSafetyReview(eventId) {
  return requestJSON(`/safety-checks/coordinator/events/${encodeURIComponent(eventId)}`)
}


export function resubmitSafetyReview(eventId) {
  return requestJSON(`/safety-checks/coordinator/events/${encodeURIComponent(eventId)}/resubmit`, {
    method: 'POST',
  })
}


export function safetyCheckErrorMessage(error) {
  if (error?.status === 401) return 'Your session has expired. Please sign in again.'
  if (error?.status === 403) return 'Only Safety Officers can conduct operational safety checks.'
  if (error?.status === 404) return 'This event was not found.'
  if (error?.status === 409) return 'This safety check changed or has already been decided. Reload it before trying again.'
  if (error?.status === 422) return error.message || 'Check the decision and provide a reason where required.'
  if (error?.status === 502 || error?.status === 0) return 'Safety review information is temporarily unavailable. Try again.'
  return error?.message || 'Something went wrong. Please try again.'
}


export function safetyReturnErrorMessage(error) {
  if (error?.status === 401) return 'Your session has expired. Please sign in again.'
  if (error?.status === 403 || error?.status === 404) {
    return 'Only the assigned Event Coordinator can manage this returned event.'
  }
  if (error?.status === 409) {
    return error.message || 'This event is no longer awaiting safety changes or has already been resubmitted.'
  }
  if (error?.status === 502 || error?.status === 0) {
    return 'Safety feedback is temporarily unavailable. Try again.'
  }
  return error?.message || 'Something went wrong. Please try again.'
}


export function formatSafetyWindow(event) {
  if (!event?.start_date || !event?.start_time || !event?.end_date || !event?.end_time) {
    return 'Schedule unavailable'
  }
  const short = (value) => String(value).slice(0, 5)
  return `${event.start_date} ${short(event.start_time)} – ${event.end_date} ${short(event.end_time)}`
}
