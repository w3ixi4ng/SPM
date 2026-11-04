import { requestJSON } from './api.js'

// S-89: the assigned Coordinator cancels an event venue unavailability left
// without an alternative. These helpers only decide what to show; the
// event_requests composite checks the assignment, the unavailability and the
// event version itself.

export const VENUE_CANCELLATION_TEXT_MAX = 1000

// The statuses in which an event's venue bookings may still change -- the
// same set S-78 lets a Coordinator replace a venue for.
const CANCELLABLE_STATUSES = new Set([
  'planning', 'pending_safety_check', 'confirmed', 'preparation', 'safety_changes_requested',
])

function organiserRequestWaiting(event) {
  return Boolean(event?.cancellation_requested_at) && !event?.cancellation_decision
}

export function canCancelForUnavailableVenue(event, bookings) {
  if (!event || !CANCELLABLE_STATUSES.has(event.status)) return false
  if (organiserRequestWaiting(event)) return false
  return (bookings ?? []).some((booking) => booking.requires_alternative_arrangements)
}

// Cancelled, but releases or notifications are still to be finished.
export function venueCancellationIncomplete(event) {
  return Boolean(event?.venue_cancelled_at) && !event?.venue_cancellation_completed_at
}

export function venueCancellationErrors({ reason, alternativesConsidered }) {
  const errors = {}
  const trimmedReason = (reason ?? '').trim()
  const trimmedAlternatives = (alternativesConsidered ?? '').trim()
  if (!trimmedReason) errors.reason = 'Enter why the event is being cancelled.'
  else if (trimmedReason.length > VENUE_CANCELLATION_TEXT_MAX) errors.reason = 'Keep the reason to 1000 characters.'
  if (!trimmedAlternatives) {
    errors.alternatives_considered = 'Describe the alternatives you discussed with the Organiser.'
  } else if (trimmedAlternatives.length > VENUE_CANCELLATION_TEXT_MAX) {
    errors.alternatives_considered = 'Keep the alternatives to 1000 characters.'
  }
  return errors
}

export function venueCancellationBody({ reason, alternativesConsidered }, event) {
  return {
    reason: (reason ?? '').trim(),
    alternatives_considered: (alternativesConsidered ?? '').trim(),
    expected_version: event?.edit_version ?? 0,
  }
}

const NOTHING_CANCELLED = 'Nothing was cancelled.'

// What to tell the Coordinator after a refused or failed request. `retry`
// means the event is already cancelled and calling again finishes it.
export function venueCancellationErrorMessage(error) {
  if (error.status === 502 && error.message) return { message: error.message, retry: true }
  if (error.status === 409 && error.message) return { message: error.message, retry: false }
  if (error.status === 422) {
    const fields = error.fieldErrors ?? {}
    const fieldErrors = {}
    if (fields.reason) fieldErrors.reason = 'Enter why the event is being cancelled, up to 1000 characters.'
    if (fields.alternatives_considered) {
      fieldErrors.alternatives_considered = 'Describe the alternatives you discussed, up to 1000 characters.'
    }
    return { message: `Check the highlighted fields. ${NOTHING_CANCELLED}`, retry: false, fieldErrors }
  }
  if (error.status === 404) return { message: 'This event is no longer assigned to you.', retry: false }
  if (error.status === 401) return { message: `Your session has expired. Sign in again and retry. ${NOTHING_CANCELLED}`, retry: false }
  if (error.status === 403) return { message: `Your role can't cancel events. ${NOTHING_CANCELLED}`, retry: false }
  // The request may have arrived before the connection dropped, so whether
  // anything was cancelled is unknown until the event is reloaded.
  if (error.status === 0) {
    return { message: "We couldn't reach the server. Reload the event to see whether it was cancelled.", retry: false }
  }
  return { message: 'The cancellation could not be confirmed. Reload the event to see its status.', retry: true }
}

export function cancelForUnavailableVenue(eventId, body) {
  return requestJSON(`/event-requests/${encodeURIComponent(eventId)}/venue-cancellation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
