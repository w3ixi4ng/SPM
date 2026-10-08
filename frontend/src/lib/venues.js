import { requestJSON } from './api.js'

// Week order for display and for the payload. The allowed facility, layout
// and accessibility values are NOT listed here -- they come from
// GET /api/venues/options, so the form can never offer something the venues
// service would reject.
export const WEEK = Object.freeze(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'])

export const DAY_LABELS = Object.freeze({
  mon: 'Monday',
  tue: 'Tuesday',
  wed: 'Wednesday',
  thu: 'Thursday',
  fri: 'Friday',
  sat: 'Saturday',
  sun: 'Sunday',
})

// Only the codes whose plain humanised form reads wrong. Anything not listed
// here -- including an option added to the service later -- is humanised.
const OPTION_LABELS = {
  wifi: 'Wi-Fi',
  u_shape: 'U-shape',
  video_conferencing: 'Video conferencing',
}

export function optionLabel(code) {
  if (OPTION_LABELS[code]) return OPTION_LABELS[code]
  const words = code.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export const DEFAULT_HOURS = Object.freeze({ open: '09:00', close: '18:00' })

export function emptyVenueForm() {
  return {
    name: '',
    location: '',
    capacity: '',
    description: '',
    facilities: [],
    accessibility: [],
    roomLayouts: [],
    // A day is open when it has an entry here; a missing day is closed.
    hours: {},
    // S-75: time to prepare before an event and reset after it, entered as
    // hours and minutes and sent as total minutes.
    setupHours: '0',
    setupMins: '0',
    turnaroundHours: '0',
    turnaroundMins: '0',
  }
}

// S-75: the two times, each kept as hours and minutes in the form. Keys are
// the API field names, so a service error lands on the right pair of boxes.
const DURATIONS = [['setup', 'setup_minutes'], ['turnaround', 'turnaround_minutes']]

// The boxes take digits only: anything else is dropped as it is typed.
export function digitsOnly(value) {
  return String(value ?? '').replace(/\D/g, '')
}

// 135 -> { hours: '2', mins: '15' }
export function splitMinutes(total) {
  const minutes = Number(total ?? 0)
  return { hours: String(Math.floor(minutes / 60)), mins: String(minutes % 60) }
}

function minutesErrors(form) {
  const errors = {}
  for (const [name, key] of DURATIONS) {
    const hours = String(form[`${name}Hours`] ?? '').trim()
    const mins = String(form[`${name}Mins`] ?? '').trim()
    if (!/^\d+$/.test(hours) || !/^\d+$/.test(mins)) errors[key] = 'Enter whole hours and minutes, 0 or more.'
    else if (Number(mins) > 59) errors[key] = 'Minutes must be between 0 and 59.'
  }
  return errors
}

function minutesPayload(form) {
  const total = (name) => Number(form[`${name}Hours`]) * 60 + Number(form[`${name}Mins`])
  return { setup_minutes: total('setup'), turnaround_minutes: total('turnaround') }
}

// "HH:MM" moved by `minutes`, kept within the day: an occupied window never
// crosses midnight, because it must fit inside opening hours.
export function shiftClock(clock, minutes) {
  const [hours, mins] = clock.slice(0, 5).split(':').map(Number)
  const total = Math.min(24 * 60, Math.max(0, hours * 60 + mins + minutes))
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

// A venue's setup and turnaround, 0 for one saved before S-75.
export function venueGap(venue) {
  return { setup: venue?.setup_minutes ?? 0, turnaround: venue?.turnaround_minutes ?? 0 }
}

function openDays(form) {
  return WEEK.filter((day) => form.hours?.[day])
}

// Mirrors the venues service's required-field rules so the form can say
// what is missing before anything is sent. The service still validates.
// Keys are the API field names.
export function validateVenueForm(form) {
  const errors = {}

  if (!form.name?.trim()) errors.name = 'Enter the venue name.'
  if (!form.location?.trim()) errors.location = 'Enter where the venue is.'

  const capacity = String(form.capacity ?? '').trim()
  if (!capacity) errors.capacity = 'Enter how many people the venue holds.'
  else if (!/^\d+$/.test(capacity) || Number(capacity) < 1) {
    errors.capacity = 'Capacity must be a whole number of at least 1.'
  }

  if (!form.roomLayouts?.length) {
    errors.room_layouts = 'Choose at least one room layout.'
  }

  Object.assign(errors, minutesErrors(form))

  const days = openDays(form)
  if (!days.length) {
    errors.operating_hours = 'Set opening hours for at least one day.'
  } else {
    // Each bad day gets its own `hours.<day>` key, which outlines that row.
    // operating_hours sums them up, added after them so the first bad row is
    // what a failed save focuses.
    for (const day of days) {
      const { open, close } = form.hours[day]
      if (!open || !close) {
        errors[`hours.${day}`] = 'Set both opening and closing times.'
      } else if (close <= open) {
        errors[`hours.${day}`] = 'Closing time must be after opening time.'
      }
    }
    const badDays = days.filter((day) => errors[`hours.${day}`])
    if (badDays.length) {
      const names = badDays.map((day) => DAY_LABELS[day]).join(', ')
      errors.operating_hours = `Check the opening hours for ${names}.`
    }
  }

  return errors
}

export function venueFormToPayload(form) {
  const description = form.description?.trim() ?? ''
  return {
    name: form.name.trim(),
    location: form.location.trim(),
    capacity: Number(String(form.capacity).trim()),
    facilities: [...form.facilities],
    accessibility: [...form.accessibility],
    room_layouts: [...form.roomLayouts],
    operating_hours: openDays(form).map((day) => ({
      day,
      open: form.hours[day].open,
      close: form.hours[day].close,
    })),
    description: description || null,
    ...minutesPayload(form),
  }
}

// The service reports a bad hours entry by its index in the list that was
// sent ("operating_hours.0"). The list is built in week order from the open
// days, so the same walk maps the index back to the day's row.
export function venueFieldErrorsToForm(fieldErrors, form) {
  const days = openDays(form)
  const mapped = {}
  for (const [path, message] of Object.entries(fieldErrors ?? {})) {
    const [field, index] = path.split('.')
    if (field === 'operating_hours' && index !== undefined && days[Number(index)]) {
      mapped[`hours.${days[Number(index)]}`] = message.replace(/^Value error, /, '')
    } else {
      mapped[field] = message.replace(/^Value error, /, '')
    }
  }
  return mapped
}

export function venueErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Your role is not permitted to add venues.'
  if (error.status === 409) return 'A venue with that name already exists. Choose another name.'
  if (error.status === 422) return 'Please check the highlighted venue details.'
  if (error.status >= 500) return 'The venue service is unavailable. The venue was not saved.'
  return error.message || "We couldn't reach the venue service. The venue was not saved."
}

export function listVenues() {
  return requestJSON('/venues')
}

export function getVenueOptions() {
  return requestJSON('/venues/options')
}

export function createVenue(form) {
  return requestJSON('/venues', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(venueFormToPayload(form)),
  })
}

function durationFields(name, total) {
  const { hours, mins } = splitMinutes(total)
  return { [`${name}Hours`]: hours, [`${name}Mins`]: mins }
}

export function venueToEditForm(venue) {
  return {
    location: venue.location,
    capacity: String(venue.capacity),
    facilities: [...venue.facilities],
    accessibility: [...venue.accessibility],
    ...durationFields('setup', venue.setup_minutes),
    ...durationFields('turnaround', venue.turnaround_minutes),
  }
}

export function validateVenueEditForm(form) {
  const errors = {}
  if (!form.location?.trim()) errors.location = 'Enter where the venue is.'
  const capacity = String(form.capacity ?? '').trim()
  if (!/^\d+$/.test(capacity) || Number(capacity) < 1 || Number(capacity) > 2147483647) {
    errors.capacity = 'Capacity must be a whole number between 1 and 2147483647.'
  }
  return { ...errors, ...minutesErrors(form) }
}

export function getVenue(id) {
  return requestJSON(`/venues/${encodeURIComponent(id)}`)
}

export function updateVenue(id, form) {
  return requestJSON(`/venues/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      location: form.location.trim(),
      capacity: Number(form.capacity),
      facilities: [...form.facilities],
      accessibility: [...form.accessibility],
      ...minutesPayload(form),
    }),
  })
}

export function venueUpdateErrorMessage(error) {
  if (error.status === 403) return 'Your role is not permitted to edit venues.'
  if (error.status === 404) return 'This venue could not be found. Return to the catalogue.'
  if (!error.status || error.status >= 500) return 'We could not confirm that your changes were saved. Reload the venue before trying again.'
  return venueErrorMessage(error)
}

// --- S-34: search and filter venues ----------------------------------------
//
// Filtering happens in the browser over the full list from GET /venues. A
// venue is kept only when it matches every filter that is set; an unset
// filter (blank text, no ticks) keeps everything.

export function emptyVenueFilters() {
  return {
    query: '',
    attendance: '',
    layout: '',
    facilities: [],
    accessibility: [],
    date: '',
    startTime: '',
    endTime: '',
  }
}

// The request screen's starting filters: what the event needs, on its date.
export function venueFiltersFromEvent(event) {
  return {
    ...emptyVenueFilters(),
    attendance: event.expected_attendance != null ? String(event.expected_attendance) : '',
    layout: event.room_layout ?? '',
    facilities: [...(event.required_facilities ?? [])],
    accessibility: [...(event.required_accessibility ?? [])],
    date: event.start_date ?? '',
    startTime: event.start_time?.slice(0, 5) ?? '',
    endTime: event.end_time?.slice(0, 5) ?? '',
  }
}

function weekdayOf(isoDate) {
  const [year, month, day] = isoDate.split('-').map(Number)
  // getUTCDay counts from Sunday; WEEK starts on Monday.
  return WEEK[(new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7]
}

// Open on that date and, when both times are given, for the whole of them.
// Times without a date say nothing about which day, so they are ignored.
function openThen(venue, { date, startTime, endTime }) {
  if (!date) return true
  const hours = venue.operating_hours.find((entry) => entry.day === weekdayOf(date))
  if (!hours) return false
  if (!startTime || !endTime) return true
  // S-75: the whole occupied window, setup to turnaround, must be open.
  const { setup, turnaround } = venueGap(venue)
  return hours.open.slice(0, 5) <= shiftClock(startTime, -setup)
    && shiftClock(endTime, turnaround) <= hours.close.slice(0, 5)
}

export function filterVenues(venues, filters) {
  const query = filters.query.trim().toLowerCase()
  const atLeast = Number(filters.attendance)
  return venues.filter((venue) => (
    (!query || venue.name.toLowerCase().includes(query) || venue.location.toLowerCase().includes(query))
    && (!(atLeast > 0) || venue.capacity >= atLeast)
    && (!filters.layout || venue.room_layouts.includes(filters.layout))
    && filters.facilities.every((code) => venue.facilities.includes(code))
    && filters.accessibility.every((code) => venue.accessibility.includes(code))
    && openThen(venue, filters)
  ))
}
