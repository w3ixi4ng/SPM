import { requestJSON } from './api.js'
import { DAY_LABELS, optionLabel, shiftClock, venueGap, WEEK } from './venues.js'

// S-36: a Coordinator requests a venue for an event in planning; Venue Staff
// see every pending request. The venue requirements belong to the event, so
// the Coordinator chooses only the venue, the date and time, and notes. The
// venue_bookings composite is authoritative for every rule -- the event
// window, opening hours, capacity, facilities, accessibility and layout. This
// file only decides what the browser shows and sends.

export function canRequestVenue(status) {
  return status === 'planning'
}

// S-79: an event can book several venues. Once one has been asked for --
// whatever its status -- the same request screen adds another.
export function venueRequestLinkLabel(bookings) {
  return bookings.length > 0 ? 'Add another venue' : 'Request venue'
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

function weekdayOf(isoDate) {
  const [year, month, day] = isoDate.split('-').map(Number)
  return WEEK[(new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7]
}

// Whether `venue` is open for the booking `when` ({date, startTime, endTime}),
// as a problem to show, or null when it is -- or when there is no date yet.
function hoursProblem(venue, when) {
  if (!when?.date) return null
  const day = weekdayOf(when.date)
  const hours = venue.operating_hours.find((entry) => entry.day === day)
  if (!hours) return `Closed on ${DAY_LABELS[day]}s`
  if (!when.startTime || !when.endTime) return null
  const open = hours.open.slice(0, 5)
  const close = hours.close.slice(0, 5)
  // S-75: the whole occupied window, setup to turnaround, must be open.
  const { setup, turnaround } = venueGap(venue)
  if (open <= shiftClock(when.startTime, -setup) && shiftClock(when.endTime, turnaround) <= close) return null
  const base = `Open ${open}–${close} on ${DAY_LABELS[day]}s`
  return setup || turnaround ? `${base}, with ${setup} min setup and ${turnaround} min turnaround` : base
}

// Why `venue` would not suit `event`, before anything is sent -- an empty list
// when it fits. Opening hours are checked only when `when`, the booking's date
// and time, is given (S-34); the service checks them again on send.
export function venueFit(event, venue, when) {
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
  const hours = hoursProblem(venue, when)
  if (hours) problems.push(hours)
  return problems
}

// S-35: the warning shown when the selected venue doesn't meet the event's
// venue requirements -- capacity, layout, facilities or accessibility -- or
// null when it does, or when nothing is selected yet. While it is showing,
// Send request is disabled: the service would refuse the request anyway, so
// the Coordinator is steered to a venue that fits instead.
export function venueWarning(event, venue, when) {
  if (!venue) return null
  const problems = venueFit(event, venue, when)
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

export const VENUE_PREPARATION_OPTIONS = [
  { value: 'not_started', label: 'Not Started' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'ready', label: 'Ready' },
]

export function venuePreparationLabel(status) {
  return VENUE_PREPARATION_OPTIONS.find(({ value }) => value === status)?.label ?? 'Not Started'
}

export function listVenuePreparationBookings() {
  return requestJSON('/venue-bookings/preparation')
}

export function updateVenuePreparation(id, status, expectedVersion) {
  return requestJSON(`/venue-bookings/${encodeURIComponent(id)}/preparation`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, expected_version: expectedVersion }),
  })
}

export function venuePreparationErrorMessage(error) {
  if ([401, 403, 404, 409, 422].includes(error.status) && error.message) return error.message
  return "We couldn't update venue preparation. Reload and try again."
}

// The requests sent for one event, every status, oldest first.
export function listVenueBookingsForEvent(eventId) {
  return requestJSON(`/venue-bookings?event_id=${encodeURIComponent(eventId)}`)
}

export const PRIMARY_VENUE_REQUIRED = 'Choose a new primary venue so attendees know where to go.'

export function primaryVenuePrompt(bookings) {
  const confirmed = bookings.filter(({ status }) => status === 'confirmed')
  return confirmed.length > 0 && !confirmed.some(({ is_primary }) => is_primary)
    ? PRIMARY_VENUE_REQUIRED
    : null
}

export function selectPrimaryVenueBooking(id) {
  return requestJSON(`/venue-bookings/${encodeURIComponent(id)}/primary`, { method: 'PUT' })
}

export function primaryVenueErrorMessage(error) {
  if ([401, 403, 404, 409].includes(error.status) && error.message) return error.message
  return "We couldn't change the primary venue. Reload and try again."
}

const BOOKING_STATUS_META = {
  pending: { label: 'Pending', color: '#B5842B' },
  held: { label: 'Tentatively held', color: '#B5842B' },
  confirmed: { label: 'Confirmed', color: '#3F8F5F' },
  rejected: { label: 'Rejected', color: '#B25547' },
  // S-78: its replacement was confirmed, so it no longer reserves the venue.
  replaced: { label: 'Replaced', color: '#4C5A70' },
  // S-89: its event was cancelled; kept as history, it reserves nothing.
  released: { label: 'Released', color: '#4C5A70' },
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

export function holdExpiryToIso(value, now = new Date()) {
  if (!value) return { error: 'Choose when the tentative hold expires.' }
  const parsed = new Date(`${value}:00+08:00`)
  if (Number.isNaN(parsed.getTime())) return { error: 'Choose a valid expiry date and time.' }
  if (parsed <= now) return { error: 'The hold expiry must be in the future.' }
  return { expiresAt: parsed.toISOString() }
}

export function holdExpiryLabel(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('en-SG', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: false,
    timeZone: 'Asia/Singapore',
  }).format(new Date(value))
}

export function placeVenueHold(id, expiresAt) {
  return requestJSON(`/venue-bookings/${encodeURIComponent(id)}/hold`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ expires_at: expiresAt }),
  })
}

export function releaseVenueHold(id) {
  return requestJSON(`/venue-bookings/${encodeURIComponent(id)}/release`, { method: 'POST' })
}

export function holdActionErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Only Venue Staff can manage tentative holds.'
  if (error.status === 404) return 'This booking request could not be found. Reload the list.'
  if (error.status === 409) return error.message
  if (error.status === 422) return error.message
  return "We couldn't update the tentative hold. Reload the list before trying again."
}

export function bookingDecisionErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Only Venue Staff can decide booking requests.'
  if (error.status === 404) return 'This booking request could not be found. Reload the list.'
  // An overlap (S-76's refusal, which replaced S-38's wording, naming the
  // booking in the way and its occupied period) or an S-30 block that day.
  if (error.status === 409 && (error.message?.startsWith("Can't confirm this booking:")
    || error.message?.includes('is unavailable from'))) return error.message
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

// --- S-77: unavailable periods ------------------------------------------------

// Why Venue Staff marked a venue unavailable, as the bookings service stores
// it. Keep in step with backend/services/atomic/bookings/schemas.py.
export const BLOCK_REASON_LABELS = Object.freeze({
  maintenance: 'Maintenance',
  equipment_failure: 'Equipment failure',
  renovation: 'Renovation',
  safety: 'Safety concern',
  other: 'Other operational reason',
})

export function blockReasonLabel(reason) {
  return BLOCK_REASON_LABELS[reason] ?? reason
}

// "13 Nov 2026 09:00", a period's start or end at the venue.
export function periodMomentLabel(day, time) {
  return `${bookingDateLabel(day)} ${shortTime(time)}`
}

function periodPhrase(period) {
  const why = period.note
    ? `${blockReasonLabel(period.reason)}: ${period.note}`
    : blockReasonLabel(period.reason)
  return `from ${periodMomentLabel(period.start_date, period.start_time)} `
    + `to ${periodMomentLabel(period.end_date, period.end_time)} (${why})`
}

// What a Coordinator sees on a booking an unavailable period affects: a
// label, never colour alone, and when and why. null when nothing affects it.
export function alternativeArrangementsNotice(booking) {
  if (!booking?.requires_alternative_arrangements) return null
  const periods = [...(booking.unavailable_periods ?? [])].sort((a, b) => (
    `${a.start_date}T${a.start_time}`.localeCompare(`${b.start_date}T${b.start_time}`)
  ))
  return {
    label: 'Needs alternative arrangements',
    color: '#B25547',
    detail: `${booking.venue_name} is unavailable ${periods.map(periodPhrase).join(' and ')}.`,
  }
}

// --- S-75: setup/turnaround clashes, and one request per page ---------------

const CLASH_STATES = { confirmed: 'confirmed', held: 'held' }

// The warning a Coordinator sees on their booking when the venue's setup
// and turnaround now make it clash. Another booking's time and state only:
// the service never sends whose it is. null when there is no clash.
export function bookingClashMessage(booking) {
  const clashes = booking?.clashes ?? []
  if (clashes.length === 0) return null
  const parts = clashes.map((clash) => (
    `another ${CLASH_STATES[clash.status] ?? clash.status} booking on ${bookingDateLabel(clash.booking_date)}, `
    + `${shortTime(clash.start_time)}–${shortTime(clash.end_time)} `
    + `(venue in use ${clash.occupied_start}–${clash.occupied_end})`
  ))
  return `Clashes with ${parts.join(' and ')} under ${booking.venue_name}'s setup and turnaround times. `
    + 'Contact Venue Staff to rearrange.'
}

export function getVenueClashes(venueId) {
  return requestJSON(`/venue-bookings/clashes?venue_id=${encodeURIComponent(venueId)}`)
}

// S-76: every venue's clashing pairs, for Venue Staff's standing review list.
export function getClashesToReview() {
  return requestJSON('/venue-bookings/clashes')
}

// "Studio B · 1 pair · setup 30 min, turnaround 45 min"
export function clashReviewHeading(venue) {
  const count = venue.pairs.length
  return `${venue.venue_name} · ${count} ${count === 1 ? 'pair' : 'pairs'} · `
    + `setup ${venue.setup_minutes} min, turnaround ${venue.turnaround_minutes} min`
}

function clashSide(side) {
  return `${side.event_name} (${bookingStatusMeta(side.status).label}, `
    + `${shortTime(side.start_time)}–${shortTime(side.end_time)})`
}

// "Alumni talk (Confirmed, 10:00–12:00) and Board lunch (Held, 12:30–14:00) on 12 Nov 2026"
export function clashPairLabel(pair) {
  return `${clashSide(pair.first)} and ${clashSide(pair.second)} on ${bookingDateLabel(pair.first.booking_date)}`
}

// One compact row in Venue Staff's request list. The details and every
// action are on the request's own page.
export function pendingRequestSummary(booking) {
  return {
    title: booking.event_name,
    line: `${booking.venue_name} · ${bookingDateLabel(booking.booking_date)}, `
      + `${shortTime(booking.start_time)}–${shortTime(booking.end_time)}`,
    status: bookingStatusMeta(booking.status),
    clash: (booking.clashes ?? []).length > 0 ? 'Clash' : null,
  }
}

export function pendingRequestPath(booking) {
  return `/venue-bookings/${encodeURIComponent(booking.id)}`
}

export function getVenueBooking(id) {
  return requestJSON(`/venue-bookings/${encodeURIComponent(id)}`)
}

// Shown once on the dashboard after a decision, then cleared.
export function decisionNotice(decision, booking) {
  const outcome = decision === 'approved' ? 'confirmed' : 'rejected'
  return `Booking for ${booking.event_name} at ${booking.venue_name} ${outcome}.`
}

// --- S-78: replacing an affected booking -------------------------------------
//
// A booking S-77 flags can be replaced by a request for another venue, at its
// own date and times and for the same event, or resolved with a note. The
// venue_bookings composite works out which venues are suitable and available,
// and copies the event's details onto the request; the browser sends only the
// venue and notes.

const ACTIVE_REPLACEMENT = ['pending', 'held']
export const RESOLUTION_NOTE_MAX = 500

function replacementsOf(booking, bookings) {
  return bookings.filter((row) => row.replaces_booking_id === booking.id)
}

// What a booking's row offers and says about replacing it: `actions` is what
// the Coordinator can do ("replace", "resolve"), `label` the state in words.
export function replacementState(booking, bookings = []) {
  if (booking.status === 'replaced') {
    const replacement = bookings.find((row) => row.id === booking.replaced_by_booking_id)
    return { actions: [], label: `Replaced by ${replacement?.venue_name ?? 'another venue'}` }
  }
  if (booking.status === 'rejected' && !booking.replaces_booking_id) {
    // S-17: a rejection blocks the safety-check submission until a
    // replacement is confirmed. There is nothing to resolve with a note.
    const latest = replacementsOf(booking, bookings).at(-1)
    if (latest && ACTIVE_REPLACEMENT.includes(latest.status)) {
      return { actions: [], label: `Replacement requested: ${latest.venue_name}, waiting for Venue Staff` }
    }
    return {
      actions: ['replace'],
      label: latest?.status === 'rejected' ? `${latest.venue_name} declined the replacement request` : null,
    }
  }
  if (booking.requires_alternative_arrangements) {
    const latest = replacementsOf(booking, bookings).at(-1)
    if (latest && ACTIVE_REPLACEMENT.includes(latest.status)) {
      return {
        actions: ['resolve'],
        label: `Replacement requested: ${latest.venue_name}, waiting for Venue Staff`,
      }
    }
    return {
      actions: ['replace', 'resolve'],
      label: latest?.status === 'rejected' ? `${latest.venue_name} declined the replacement request` : null,
    }
  }
  if (booking.alternative_resolution_note) {
    return { actions: [], label: `Resolved: ${booking.alternative_resolution_note}` }
  }
  if (booking.replaces_booking_id) {
    const original = bookings.find((row) => row.id === booking.replaces_booking_id)
    return { actions: [], label: original ? `Replacement for ${original.venue_name}` : 'Replacement request' }
  }
  return { actions: [], label: null }
}

// For Venue Staff: which booking a replacement request replaces, or null.
export function replacementOriginLabel(booking) {
  return booking?.replaces ? `Replacement for ${booking.replaces.venue_name}` : null
}

export function validateResolutionNote(note) {
  const trimmed = (note ?? '').trim()
  if (!trimmed) return "Say what you've arranged instead."
  if (trimmed.length > RESOLUTION_NOTE_MAX) return `Keep the note to ${RESOLUTION_NOTE_MAX} characters.`
  return null
}

export function resolutionPayload(note) {
  return { note: note.trim() }
}

export function replacementPath(eventId, bookingId) {
  return `/coordinator/events/${encodeURIComponent(eventId)}/bookings/${encodeURIComponent(bookingId)}/replacement`
}

export function searchReplacementVenues(bookingId) {
  return requestJSON(`/venue-bookings/${encodeURIComponent(bookingId)}/replacement-venues`)
}

export function requestReplacementVenue(bookingId, { venueId, notes = '' }) {
  return requestJSON(`/venue-bookings/${encodeURIComponent(bookingId)}/replacement`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ venue_id: venueId, notes: notes.trim() || null }),
  })
}

export function resolveAlternativeArrangements(bookingId, note) {
  return requestJSON(`/venue-bookings/${encodeURIComponent(bookingId)}/resolution`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(resolutionPayload(note)),
  })
}

function whenLabel(booking) {
  return `on ${bookingDateLabel(booking.booking_date)} from ${shortTime(booking.start_time)} to ${shortTime(booking.end_time)}`
}

// The line above the replacement screen's venue list.
export function replacementSearchSummary({ booking, venues }) {
  if (venues.length === 0) {
    return `No venue can take this event ${whenLabel(booking)}. `
      + "Resolve the booking with a note if you've made other arrangements."
  }
  return `${venues.length} ${venues.length === 1 ? 'venue' : 'venues'} can take this event ${whenLabel(booking)}.`
}

const BACK_TO_EVENT = 'Go back to the event to see its current state.'

// Always a list, like venueBookingErrorMessages: a refused venue can fail
// several checks at once. Used for the search, the request and resolving.
export function replacementErrorMessages(error) {
  if (error.status === 422 && error.fieldErrors) {
    const messages = Object.values(error.fieldErrors)
    if (messages.length > 0) return messages
  }
  if (error.status === 401) return ['Your session has expired. Please sign in again.']
  if (error.status === 403) return ['Only the Coordinator of this event can replace its venues.']
  if (error.status === 404) return ["We couldn't find this booking. Go back to the event and try again."]
  if (error.status === 409) {
    if (error.message === "This booking doesn't need a replacement venue") {
      return [`This booking no longer needs a replacement. ${BACK_TO_EVENT}`]
    }
    if (error.message === "This booking doesn't need alternative arrangements") {
      return [`This booking no longer needs alternative arrangements. ${BACK_TO_EVENT}`]
    }
    if (error.message === 'A replacement request for this booking is already with Venue Staff') {
      return ["You've already asked for a replacement for this booking. Wait for Venue Staff's decision."]
    }
    if (error.message === "This event's venue bookings can no longer be changed"
      || error.message === 'This booking can no longer be replaced') {
      return [`${error.message}. ${BACK_TO_EVENT}`]
    }
    return [error.message, 'Choose another venue.']
  }
  return ["We couldn't reach the booking service. Try again in a moment."]
}

// S-80: one booking of an event, changed or cancelled by its Coordinator.
// The venue_bookings composite is authoritative; this decides what the page
// offers and says.
const CHANGEABLE = new Set(['pending', 'held', 'confirmed'])

export function canChangeVenueBooking(booking, eventStatus) {
  return canRequestVenue(eventStatus) && CHANGEABLE.has(booking?.status)
}

export function bookingToChangeForm(booking) {
  return {
    eventId: booking.event_id,
    venueId: booking.venue_id,
    bookingDate: booking.booking_date,
    startTime: shortTime(booking.start_time),
    endTime: shortTime(booking.end_time),
    notes: booking.notes ?? '',
  }
}

export function cancelVenueBookingPrompt(booking) {
  return (
    `Cancel ${booking.venue_name} on ${bookingDateLabel(booking.booking_date)}, `
    + `${shortTime(booking.start_time)}–${shortTime(booking.end_time)}? `
    + 'Its time is freed for other events. Your other venue bookings stay as they are.'
  )
}

export const VENUE_BOOKING_CHANGED = "Venue booking changed. It's pending until Venue Staff review it again."
export const VENUE_BOOKING_CANCELLED = 'Venue booking cancelled. Its time is free for other events.'

export function changeVenueBooking(id, form) {
  const { event_id: _eventId, ...change } = venueBookingFormToPayload(form)
  return requestJSON(`/venue-bookings/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes: null, ...change }),
  })
}

export function cancelVenueBooking(id) {
  return requestJSON(`/venue-bookings/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

const UNCHANGED = 'The booking has not changed.'

// A 409 carries the service's own reason (a clash, a block, the event out of
// planning); every other failure says the booking is as it was.
export function venueBookingChangeErrorMessage(error) {
  if (error.status === 409 && error.message) return error.message
  if (error.status === 422) return `Check the venue, date and times. ${UNCHANGED}`
  if (error.status === 404) return `This booking or its event wasn't found. ${UNCHANGED}`
  if (error.status === 401) return `Your session has expired. Sign in again and retry. ${UNCHANGED}`
  if (error.status === 403) return `Your role can't change venue bookings. ${UNCHANGED}`
  if (error.status === 0) return `We couldn't reach the server. Check your connection and try again. ${UNCHANGED}`
  return `The booking service is unavailable. Try again in a moment. ${UNCHANGED}`
}
