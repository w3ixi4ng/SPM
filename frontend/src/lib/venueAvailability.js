import { requestJSON } from './api.js'
import { bookingStatusMeta, shortTime } from './venueBookings.js'
import { optionLabel, WEEK } from './venues.js'

// S-30: a venue's availability calendar. A pending request is a tentative
// hold, a confirmed one is shown as just "Booked", and Venue Staff can mark
// whole days unavailable. The venue_bookings composite decides what each role
// may see; this file only decides how the calendar looks. Dates are ISO
// "YYYY-MM-DD" strings throughout: a booking is a calendar date at the venue,
// not an instant, so no timezone ever applies to them.

export const BLOCK_REASONS = Object.freeze(['maintenance', 'renovation', 'safety', 'internal_activity', 'other'])

const ROSE = '#B25547'
const SKY = '#3C6E96'
const INK_FAINT = '#4C5A70'

// Every state carries a text label; the colour only ever repeats it. Each
// colour is distinct: Booked keeps the green "Confirmed" has elsewhere, so
// Available takes sky rather than looking booked.
export const STATE_META = Object.freeze({
  available: { label: 'Available', color: SKY },
  held: { label: 'Tentatively held', color: bookingStatusMeta('pending').color },
  confirmed: { label: 'Booked', color: bookingStatusMeta('confirmed').color },
  blocked: { label: 'Unavailable', color: ROSE },
  closed: { label: 'Closed', color: INK_FAINT },
})

function toDate(iso) {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day))
}

function toIso(date) {
  return date.toISOString().slice(0, 10)
}

export function addDays(iso, days) {
  const date = toDate(iso)
  date.setUTCDate(date.getUTCDate() + days)
  return toIso(date)
}

// Today in the browser's own calendar, as DateSelect in EventRequestForm.jsx
// reads it.
export function localToday(now = new Date()) {
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

// DateSelect's earliest-selectable rule: a plain date is strictly in the
// future, and an end date may not fall before its start.
export function earliestFrom(today) {
  return addDays(today, 1)
}

export function earliestTo(from) {
  return from
}

export function defaultAvailabilityRange(today) {
  return { from: addDays(today, 1), to: addDays(today, 28) }
}

function weekdayOf(iso) {
  // getUTCDay counts from Sunday; WEEK starts on Monday.
  return WEEK[(toDate(iso).getUTCDay() + 6) % 7]
}

function isOpen(operatingHours, iso) {
  return operatingHours.some((entry) => entry.day === weekdayOf(iso))
}

// A state's colour as a light fill, so a whole day can be coloured while
// ink text on it keeps its contrast.
export function tint(hex, alpha = 0.16) {
  const [r, g, b] = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

// What a day's block says in the month grid: its state, or for a day with
// both bookings and holds, both of them.
export function shortDayLabel(day) {
  if (day.items.length === 0) return STATE_META[day.state].label.replace('Tentatively held', 'Held')
  const states = new Set(day.items.map((item) => item.state))
  return [states.has('confirmed') && 'Booked', states.has('held') && 'Held'].filter(Boolean).join(' + ')
}

export function blockLabel(reason) {
  return `Unavailable — ${optionLabel(reason)}`
}

function entryItem(entry) {
  const meta = STATE_META[entry.state]
  return {
    state: entry.state,
    label: `${meta.label} ${shortTime(entry.start_time)}–${shortTime(entry.end_time)}`,
    color: meta.color,
  }
}

// One day of the range. A block outranks everything, closed included -- a
// venue under repair is unavailable, whatever its hours say.
function dayOf(iso, entries, operatingHours) {
  const block = entries.find((entry) => entry.state === 'blocked' && entry.start_date <= iso && iso <= entry.end_date)
  if (block) {
    return { date: iso, state: 'blocked', label: blockLabel(block.reason), color: ROSE, items: [], block }
  }
  const items = entries
    .filter((entry) => entry.state !== 'blocked' && entry.start_date === iso)
    .sort((a, b) => a.start_time.localeCompare(b.start_time))
    .map(entryItem)
  if (items.length > 0) {
    const state = items.some((item) => item.state === 'confirmed') ? 'confirmed' : 'held'
    return { date: iso, state, label: items.map((item) => item.label).join(', '), color: STATE_META[state].color, items }
  }
  const state = isOpen(operatingHours, iso) ? 'available' : 'closed'
  return { date: iso, state, label: STATE_META[state].label, color: STATE_META[state].color, items: [] }
}

export function availabilityDays({ from, to }, entries, operatingHours) {
  const days = []
  for (let iso = from; iso <= to; iso = addDays(iso, 1)) {
    days.push(dayOf(iso, entries, operatingHours))
  }
  return days
}

export const WEEKDAY_HEADINGS = Object.freeze(['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'])

// A month grid per month the range touches, weeks starting on Sunday as in
// DateSelect. A day before tomorrow, or outside the range, is disabled: it is
// shown greyed out and cannot be selected.
export function monthGrids({ from, to }, today) {
  const earliest = earliestFrom(today)
  const grids = []
  let [year, month] = from.split('-').map(Number)
  const [lastYear, lastMonth] = to.split('-').map(Number)
  while (year < lastYear || (year === lastYear && month <= lastMonth)) {
    const first = new Date(Date.UTC(year, month - 1, 1))
    const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate()
    const cells = Array.from({ length: first.getUTCDay() }, () => null)
    for (let day = 1; day <= daysInMonth; day += 1) {
      const date = toIso(new Date(Date.UTC(year, month - 1, day)))
      cells.push({ date, day, disabled: date < earliest || date < from || date > to })
    }
    grids.push({
      key: `${year}-${month}`,
      label: first.toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' }),
      cells,
    })
    month += 1
    if (month > 12) {
      month = 1
      year += 1
    }
  }
  return grids
}

// Every call is a fresh request: opening the calendar, changing the range and
// pressing Refresh all show what is saved now.
export function getVenueAvailability(venueId, from, to) {
  const query = new URLSearchParams({ venue_id: venueId, from, to })
  return requestJSON(`/venue-bookings/availability?${query}`)
}

export function availabilityErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Your role is not permitted to view venue availability.'
  if (error.status === 404) return error.message
  return "We couldn't load this venue's availability. Try again in a moment."
}

export function emptyBlockForm(venueId, from) {
  return { venueId, startDate: from, endDate: from, reason: '', note: '' }
}

// What would stop the block being saved, before anything is sent. The
// bookings service checks the same rules again.
export function validateBlockForm(form) {
  const errors = []
  if (!form.startDate || !form.endDate) errors.push('Choose the first and last unavailable day.')
  else if (form.endDate < form.startDate) errors.push('The last day must be on or after the first day.')
  if (!form.reason) errors.push('Choose a reason.')
  else if (form.reason === 'other' && !form.note.trim()) errors.push('Add a note saying why the venue is unavailable.')
  return errors
}

export function blockFormToPayload(form) {
  return {
    venue_id: form.venueId,
    start_date: form.startDate,
    end_date: form.endDate,
    reason: form.reason,
    note: form.note.trim() || null,
  }
}

export function addVenueBlock(form) {
  return requestJSON('/venue-bookings/blocks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(blockFormToPayload(form)),
  })
}

export function removeVenueBlock(id) {
  return requestJSON(`/venue-bookings/blocks/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function blockErrorMessages(error) {
  if (error.status === 422 && error.fieldErrors) {
    const messages = Object.values(error.fieldErrors)
    if (messages.length > 0) return messages
  }
  if (error.status === 401) return ['Your session has expired. Please sign in again.']
  if (error.status === 403) return ['Only Venue Staff can mark a venue unavailable.']
  if (error.status === 404) return [error.message]
  return ["We couldn't save this change. Nothing was changed — try again in a moment."]
}
