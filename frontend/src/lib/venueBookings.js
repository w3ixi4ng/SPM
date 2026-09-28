import { requestJSON } from './api.js'
import { optionLabel } from './venues.js'

// S-36: a Coordinator requests a venue for an event in planning; Venue Staff
// see every pending request. The venue requirements belong to the event, so
// the Coordinator chooses only the venue, the date and time, and notes. The
// venue_bookings composite is authoritative for every rule -- the event
// window, opening hours, capacity, facilities, accessibility and layout. This
// file only decides what the browser shows and sends.

export function canRequestVenue(status) {
  return status === 'planning'
}

export function emptyVenueBookingForm(eventId) {
  return {
    eventId,
    venueId: '',
    bookingDate: '',
    startTime: '',
    endTime: '',
    notes: '',
  }
}

export function venueBookingFormToPayload(form) {
  const payload = {
    event_id: form.eventId,
    venue_id: form.venueId,
    booking_date: form.bookingDate,
    start_time: form.startTime,
    end_time: form.endTime,
  }
  const notes = form.notes.trim()
  if (notes) payload.notes = notes
  return payload
}

function missing(required, offered) {
  return (required ?? []).filter((code) => !(offered ?? []).includes(code))
}

// Why `venue` would not suit `event`, before anything is sent -- an empty list
// when it fits. Opening hours are left out: they depend on the date and time,
// which the service checks on send.
export function venueFit(event, venue) {
  const problems = []
  if (event.expected_attendance > venue.capacity) {
    problems.push(`Too small: holds ${venue.capacity}, event expects ${event.expected_attendance}`)
  }
  if (event.room_layout && !venue.room_layouts.includes(event.room_layout)) {
    problems.push(`No ${optionLabel(event.room_layout)} layout`)
  }
  const facilities = missing(event.required_facilities, venue.facilities)
  if (facilities.length > 0) problems.push(`Missing: ${facilities.map(optionLabel).join(', ')}`)
  const accessibility = missing(event.required_accessibility, venue.accessibility)
  if (accessibility.length > 0) problems.push(`Missing: ${accessibility.map(optionLabel).join(', ')}`)
  return problems
}

// S-35: the warning shown when the selected venue doesn't meet the event's
// venue requirements -- capacity, layout, facilities or accessibility -- or
// null when it does, or when nothing is selected yet. While it is showing,
// Send request is disabled: the service would refuse the request anyway, so
// the Coordinator is steered to a venue that fits instead.
export function venueWarning(event, venue) {
  if (!venue) return null
  const problems = venueFit(event, venue)
  if (problems.length === 0) return null
  return `${venue.name} doesn't suit this event: ${problems.join('; ')}. Choose a venue that fits.`
}

// Always a list: a refused request can fail several checks at once, and the
// Coordinator should see every one of them, not just the first.
export function venueBookingErrorMessages(error) {
  if (error.status === 422 && error.fieldErrors) {
    const messages = Object.values(error.fieldErrors)
    if (messages.length > 0) return messages
  }
  if (error.status === 401) return ['Your session has expired. Please sign in again.']
  if (error.status === 403) return ['Your role is not permitted to request venues.']
  if (error.status === 404 || error.status === 409 || error.status === 422) return [error.message]
  return ["We couldn't send the venue request. Nothing was submitted — try again in a moment."]
}

export function pendingListErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Your role is not permitted to see booking requests.'
  return "We couldn't load pending booking requests. Try again in a moment."
}

export function submitVenueBooking(form) {
  return requestJSON('/venue-bookings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(venueBookingFormToPayload(form)),
  })
}

export function listPendingVenueBookings() {
  return requestJSON('/venue-bookings/pending')
}

// The requests sent for one event, every status, oldest first.
export function listVenueBookingsForEvent(eventId) {
  return requestJSON(`/venue-bookings?event_id=${encodeURIComponent(eventId)}`)
}

const BOOKING_STATUS_META = {
  pending: { label: 'Pending', color: '#B5842B' },
  confirmed: { label: 'Confirmed', color: '#3F8F5F' },
  rejected: { label: 'Rejected', color: '#B25547' },
}

export function bookingStatusMeta(status) {
  return BOOKING_STATUS_META[status] ?? { label: status, color: '#4C5A70' }
}

export function validateBookingDecision({ decision, reason = '', alternative = '' }) {
  if (!['approved', 'rejected'].includes(decision)) return 'Choose Approve or Reject.'
  if (decision === 'rejected' && !reason.trim() && !alternative.trim()) {
    return 'Provide a reason or alternative to reject this request.'
  }
  return null
}

export function decideVenueBooking(id, { decision, reason = '', alternative = '' }) {
  return requestJSON(`/venue-bookings/${encodeURIComponent(id)}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, reason: reason.trim() || null, alternative: alternative.trim() || null }),
  })
}

export function bookingDecisionErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Only Venue Staff can decide booking requests.'
  if (error.status === 404) return 'This booking request could not be found. Reload the list.'
  if (error.status === 409) return 'This request has already been decided. Reload the list to see the latest requests.'
  if (error.status === 422) return 'Check your decision. Rejection needs a reason or alternative.'
  return 'We could not confirm whether your decision was saved. Reload the list before trying again.'
}

// "09:00:00" -> "09:00"
export function shortTime(value) {
  return value ? value.slice(0, 5) : ''
}

// "2026-11-12" -> "12 Nov 2026", independent of the viewer's timezone: the
// booking is a calendar date at the venue, not an instant.
export function bookingDateLabel(value) {
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}
