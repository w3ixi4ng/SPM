import { requestJSON } from './api.js'

// S-51: an event's registration period is Singapore wall-clock time, stored
// without a timezone ("2026-11-01T09:00:00"). Every comparison here is on
// that wall-clock text, with "now" converted to Singapore time first, so the
// page agrees with the event_registrations service whatever the viewer's
// own timezone.
const SINGAPORE_OFFSET_MS = 8 * 60 * 60 * 1000
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// "2026-11-01T09:00:00" and "2026-11-01T09:00" compare the same.
function minutePrecision(value) {
  return value ? value.slice(0, 16) : ''
}

function singaporeNow(now) {
  return new Date(now.getTime() + SINGAPORE_OFFSET_MS).toISOString().slice(0, 16)
}

function eventStart(event) {
  const date = event?.startDate ?? event?.start_date
  const time = event?.startTime ?? event?.start_time
  return date && time ? `${date}T${time.slice(0, 5)}` : ''
}

// The Organiser's settings, checked the way the events service checks them.
// A draft may turn registration on and pick the dates later; submitting
// needs both. Opening in the past is fine -- registration simply opens now.
export function validateRegistrationSettings(settings, event, { submitting = false } = {}) {
  const errors = {}
  if (!settings.required) return errors

  const opens = minutePrecision(settings.opensAt)
  const closes = minutePrecision(settings.closesAt)
  if (submitting && !opens) errors.opens = 'Choose when registration opens.'
  if (submitting && !closes) errors.closes = 'Choose when registration closes.'

  const start = eventStart(event)
  if (opens && closes && closes <= opens) {
    errors.closes = 'Registration must close after it opens.'
  } else if (closes && start && closes >= start) {
    errors.closes = 'Registration must close before the event starts.'
  }
  return errors
}

// Where `now` falls: not_required, not_open, open or closed. Opening is
// inclusive and closing exclusive, as on the service.
export function registrationWindow(event, now = new Date()) {
  if (!event?.registration_required) return 'not_required'
  const current = singaporeNow(now)
  if (current < minutePrecision(event.registration_opens_at)) return 'not_open'
  if (current >= minutePrecision(event.registration_closes_at)) return 'closed'
  return 'open'
}

// "1 Nov 2026, 9:00 am" -- the service's wording for the same moment.
export function formatRegistrationMoment(value) {
  const [date, time] = minutePrecision(value).split('T')
  const [year, month, day] = date.split('-').map(Number)
  const [hour, minute] = time.split(':').map(Number)
  const hour12 = hour % 12 || 12
  const meridiem = hour < 12 ? 'am' : 'pm'
  return `${day} ${MONTHS[month - 1]} ${year}, ${hour12}:${String(minute).padStart(2, '0')} ${meridiem}`
}

// The period in words, and a one-line status for right now.
export function describeRegistration(event, now = new Date()) {
  const state = registrationWindow(event, now)
  if (state === 'not_required') {
    return { state, period: null, status: "This event doesn't need registration." }
  }
  const opens = formatRegistrationMoment(event.registration_opens_at)
  const closes = formatRegistrationMoment(event.registration_closes_at)
  const status = {
    not_open: `Registration opens on ${opens}.`,
    open: `Registration is open until ${closes}.`,
    closed: `Registration closed on ${closes}.`,
  }[state]
  return { state, period: `Registration opens ${opens} and closes ${closes}.`, status }
}

// "20 Nov 2026, 6:00 pm to 9:00 pm", or both dates when it runs overnight.
export function formatEventWhen(event) {
  if (!event?.start_date || !event?.start_time) return 'Date to be confirmed'
  const start = formatRegistrationMoment(`${event.start_date}T${event.start_time}`)
  if (!event.end_date || !event.end_time) return start
  const end = `${event.end_date}T${event.end_time}`
  if (event.end_date === event.start_date) {
    return `${start} to ${formatRegistrationMoment(end).split(', ')[1]}`
  }
  return `${start} to ${formatRegistrationMoment(end)}`
}

// The moment the current state ends -- opening while not yet open, closing
// while open -- and how far off it is, for the live countdown.
export function registrationCountdown(event, now = new Date()) {
  const state = registrationWindow(event, now)
  const target = { not_open: event?.registration_opens_at, open: event?.registration_closes_at }[state]
  if (!target) return null
  // The target is Singapore wall-clock time; as an instant it is 8h earlier in UTC.
  const at = Date.parse(`${minutePrecision(target)}:00Z`) - SINGAPORE_OFFSET_MS
  const minutes = Math.max(0, Math.floor((at - now.getTime()) / 60000))
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const mins = minutes % 60
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
  let remaining
  if (days) remaining = `${plural(days, 'day')} ${plural(hours, 'hour')}`
  else if (hours) remaining = `${plural(hours, 'hour')} ${plural(mins, 'minute')}`
  else if (mins) remaining = plural(mins, 'minute')
  else remaining = 'less than a minute'
  return { state, label: state === 'not_open' ? 'Opens in' : 'Closes in', remaining }
}

export function listPublicEvents() {
  return requestJSON('/event-registrations/events')
}

export function getPublicEvent(id) {
  return requestJSON(`/event-registrations/events/${encodeURIComponent(id)}`)
}

export function getMyRegistration(id) {
  return requestJSON(`/event-registrations/events/${encodeURIComponent(id)}/registration`)
}

export function registerForEvent(id) {
  return requestJSON(`/event-registrations/events/${encodeURIComponent(id)}/registration`, {
    method: 'POST',
  })
}
