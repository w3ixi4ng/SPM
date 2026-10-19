import { requestJSON } from './api.js'

// S-17: a Coordinator submits a fully arranged planning event for the
// Operational Safety Check. The safety_checks service decides what is
// outstanding; this page only shows its list, so the two never disagree.

const coordinatorPath = (eventId) => `/safety-checks/coordinator/events/${encodeURIComponent(eventId)}`

export function getSubmissionReadiness(eventId) {
  return requestJSON(`${coordinatorPath(eventId)}/readiness`)
}

export function buildSubmissionReadiness(readiness) {
  const outstanding = readiness?.outstanding ?? []
  return {
    canSubmit: Boolean(readiness?.ready) && outstanding.length === 0,
    items: outstanding.map((item) => ({
      key: `${item.code}:${item.booking_id ?? ''}`,
      label: item.label,
      statusLabel: 'Outstanding',
    })),
  }
}

export class OutstandingArrangementsError extends Error {
  constructor(message, outstanding) {
    super(message)
    this.name = 'OutstandingArrangementsError'
    this.status = 409
    this.outstanding = outstanding
  }
}

// Takes no body on purpose: there is no override.
export async function submitForSafetyCheck(eventId) {
  try {
    return await requestJSON(`${coordinatorPath(eventId)}/submit`, { method: 'POST' })
  } catch (error) {
    if (error.status === 409 && Array.isArray(error.body?.outstanding)) {
      throw new OutstandingArrangementsError(error.message, error.body.outstanding)
    }
    throw error
  }
}

export function submissionErrorMessage(error) {
  if (error?.outstanding) return 'This event still has outstanding arrangements. Complete each item below, then submit again.'
  if (error?.status === 401) return 'Your session has expired. Please sign in again.'
  if (error?.status === 403 || error?.status === 404) return 'Only the assigned Event Coordinator can submit this event.'
  if (error?.status === 409) return `${error.message}. Reload the page to see its current status.`
  if (error?.status === 502 || error?.status === 0) {
    return 'We couldn’t check the arrangements right now, so nothing was submitted. Try again in a moment.'
  }
  return error?.message || 'Something went wrong, so nothing was submitted. Try again.'
}

// Technical Support sign-off. Returns { payload } or { error } so the form
// can say what is wrong without a round trip.
export function signoffPayload({ decision, reason = '', overrideComment = '' }) {
  if (decision === 'declined') {
    const trimmed = reason.trim()
    if (!trimmed) return { error: 'Enter a reason for declining' }
    return { payload: { decision: 'declined', reason: trimmed } }
  }
  const comment = overrideComment.trim()
  return { payload: comment ? { decision: 'approved', override_comment: comment } : { decision: 'approved' } }
}

export class EquipmentShortageError extends Error {
  constructor(message, short) {
    super(message)
    this.name = 'EquipmentShortageError'
    this.status = 409
    this.short = short
  }
}

export async function signOffEquipment(eventId, payload) {
  try {
    return await requestJSON(`/equipment-requirements/${encodeURIComponent(eventId)}/sign-off`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch (error) {
    if (error.status === 409 && Array.isArray(error.body?.short)) {
      throw new EquipmentShortageError(error.message, error.body.short)
    }
    throw error
  }
}

export function signoffErrorMessage(error) {
  if (error?.short) return 'Some equipment is short for this event. Approve only if you can cover it, and say how.'
  if (error?.status === 401) return 'Your session has expired. Please sign in again.'
  if (error?.status === 403 || error?.status === 404) return 'This event was not found or is no longer assigned to you.'
  if (error?.status === 409) return error.message || 'The event is no longer in planning. Reload the page.'
  if (error?.status === 422) return 'Check the sign-off: a decline needs a reason.'
  if (error?.status >= 500 || error?.status === 0) return 'The sign-off was not saved. Try again in a moment.'
  return error?.message || 'The sign-off was not saved. Try again.'
}

export function describeSignoff(event) {
  const decision = event?.technical_signoff_decision
  if (decision === 'approved') {
    return { label: 'Approved by Technical Support', note: event.technical_signoff_override_comment || null }
  }
  if (decision === 'declined') {
    return { label: 'Declined by Technical Support', note: event.technical_signoff_reason }
  }
  return { label: 'Awaiting Technical Support', note: null }
}
