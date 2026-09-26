import { requestJSON } from './api.js'

// S-36: a Coordinator requests a venue for an event in planning; Venue Staff
// see every pending request. The venue_bookings composite is authoritative
// for every rule -- the event window, opening hours, capacity, facilities,
// accessibility and layout. This file only decides what the browser shows
// and sends.

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
    roomLayout: '',
    requiredFacilities: [],
    requiredAccessibility: [],
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
    required_facilities: [...form.requiredFacilities],
    required_accessibility: [...form.requiredAccessibility],
  }
  if (form.roomLayout) payload.room_layout = form.roomLayout
  const notes = form.notes.trim()
  if (notes) payload.notes = notes
  return payload
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

// Only pending exists until Venue Staff can approve or reject.
const BOOKING_STATUS_META = {
  pending: { label: 'Pending', color: '#B5842B' },
}

export function bookingStatusMeta(status) {
  return BOOKING_STATUS_META[status] ?? { label: status, color: '#4C5A70' }
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
