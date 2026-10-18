import { requestJSON } from './api.js'
import { blockReasonLabel, bookingDateLabel, bookingStatusMeta, shortTime } from './venueBookings.js'
import { shiftClock, WEEK } from './venues.js'

// S-30: a venue's availability calendar. A pending request is a tentative
// hold, a confirmed one is shown as just "Booked", and Venue Staff can mark
// a venue unavailable -- since S-77 for a timed period, from a start date and
// time up to an end date and time. The venue_bookings composite decides what
// each role may see; this file only decides how the calendar looks. Dates are
// ISO "YYYY-MM-DD" strings throughout: a booking is a calendar date at the
// venue, not an instant, so no timezone ever applies to them.

export const BLOCK_REASONS = Object.freeze(['maintenance', 'equipment_failure', 'renovation', 'safety', 'other'])

const ROSE = '#B25547'
const GREEN = '#3F8F5F'
const SKY = '#3C6E96'
const INK_FAINT = '#4C5A70'
const INK = '#10192B'

// Every state carries a text label; the colour only ever repeats it, and no
// two states share one. Booked is red -- taken -- so it never reads as free.
export const STATE_META = Object.freeze({
  available: { label: 'Available', color: GREEN },
  held: { label: 'Tentatively held', color: bookingStatusMeta('pending').color },
  confirmed: { label: 'Booked', color: ROSE },
  blocked: { label: 'Unavailable', color: SKY },
  partly_blocked: { label: 'Partly unavailable', color: INK },
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

// The calendar shows one month at a time, as { year, month } with month
// 1-12. It opens on the month tomorrow falls in -- the first with a day that
// can be chosen -- and never goes earlier.
export function initialMonth(today) {
  const [year, month] = earliestFrom(today).split('-').map(Number)
  return { year, month }
}

export function isBeforeMonth(view, earliest) {
  return view.year < earliest.year || (view.year === earliest.year && view.month < earliest.month)
}

export function shiftMonth({ year, month }, delta) {
  const index = year * 12 + (month - 1) + delta
  return { year: Math.floor(index / 12), month: (index % 12) + 1 }
}

// The whole month, which is the range fetched: the days before tomorrow in
// it are shown greyed out rather than left off.
export function monthRange({ year, month }) {
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate()
  const pad = (value) => String(value).padStart(2, '0')
  return { from: `${year}-${pad(month)}-01`, to: `${year}-${pad(month)}-${pad(last)}` }
}

export const MONTH_NAMES = Object.freeze([
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
])

// The Year dropdown: the earliest month's year and the five after it, as
// DateSelect offers six years.
export function yearOptions(earliest) {
  return Array.from({ length: 6 }, (_, index) => earliest.year + index)
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
  return `Unavailable — ${blockReasonLabel(reason)}`
}

const NO_GAP = Object.freeze({ setup: 0, turnaround: 0 })

// S-75: "Setup 30 min · Turnaround 45 min", for the top of the calendar.
export function setupTurnaroundLabel({ setup, turnaround }) {
  return `Setup ${setup} min · Turnaround ${turnaround} min`
}

// The event's own time, and -- when the venue has setup or turnaround --
// the longer time the venue is in use, which is what other requests can't
// book into.
function entryItem(entry, gap = NO_GAP) {
  const meta = STATE_META[entry.state]
  const start = shortTime(entry.start_time)
  const end = shortTime(entry.end_time)
  let label = `${meta.label} ${start}–${end}`
  if (gap.setup || gap.turnaround) {
    label += ` · venue in use ${shiftClock(start, -gap.setup)}–${shiftClock(end, gap.turnaround)}`
  }
  return { state: entry.state, label, color: meta.color }
}

const MIDNIGHT = '00:00:00'

// S-77: a period runs from its start up to, not including, its end, so one
// ending at 00:00 stopped the day before.
function periodTouches(entry, iso) {
  if (entry.start_date > iso || entry.end_date < iso) return false
  return !(entry.end_date === iso && entry.end_time === MIDNIGHT)
}

function periodCovers(entry, iso) {
  const startsBefore = entry.start_date < iso || entry.start_time === MIDNIGHT
  return startsBefore && entry.end_date > iso
}

// The part of the day a period takes, for a day it only partly covers.
function periodNote(entry, iso) {
  const starts = entry.start_date === iso && entry.start_time !== MIDNIGHT
  const ends = entry.end_date === iso
  let when = `until ${shortTime(entry.end_time)}`
  if (starts && ends) when = `${shortTime(entry.start_time)}–${shortTime(entry.end_time)}`
  else if (starts) when = `from ${shortTime(entry.start_time)}`
  return { label: `Unavailable ${when} · ${blockReasonLabel(entry.reason)}`, block: entry }
}

// One day of the range. A period covering the whole day outranks
// everything, closed included -- a venue under repair is unavailable,
// whatever its hours say. A period covering part of the day is listed in the
// day's detail; with nothing else on, the day reads Partly unavailable.
function dayOf(iso, entries, operatingHours, gap) {
  const touching = entries.filter((entry) => entry.state === 'blocked' && periodTouches(entry, iso))
  const block = touching.find((entry) => periodCovers(entry, iso))
  if (block) {
    return { date: iso, state: 'blocked', label: blockLabel(block.reason), color: STATE_META.blocked.color, items: [], periods: [], block }
  }
  const periods = touching.map((entry) => periodNote(entry, iso))
  const items = entries
    .filter((entry) => entry.state !== 'blocked' && entry.start_date === iso)
    .sort((a, b) => a.start_time.localeCompare(b.start_time))
    .map((entry) => entryItem(entry, gap))
  if (items.length > 0) {
    const state = items.some((item) => item.state === 'confirmed') ? 'confirmed' : 'held'
    return { date: iso, state, label: items.map((item) => item.label).join(', '), color: STATE_META[state].color, items, periods }
  }
  if (periods.length > 0) {
    const meta = STATE_META.partly_blocked
    return { date: iso, state: 'partly_blocked', label: meta.label, color: meta.color, items: [], periods }
  }
  const state = isOpen(operatingHours, iso) ? 'available' : 'closed'
  return { date: iso, state, label: STATE_META[state].label, color: STATE_META[state].color, items: [], periods: [] }
}

export function availabilityDays({ from, to }, entries, operatingHours, gap = NO_GAP) {
  const days = []
  for (let iso = from; iso <= to; iso = addDays(iso, 1)) {
    days.push(dayOf(iso, entries, operatingHours, gap))
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
  return { venueId, startDate: from, startTime: '', endDate: from, endTime: '', reason: '', note: '' }
}

// What would stop the period being saved, before anything is sent. The
// bookings service checks the same rules again. Times are "HH:MM", so the
// date and time compare as one string.
export function validateBlockForm(form) {
  const errors = []
  if (!form.startDate || !form.startTime) errors.push('Choose when the unavailable period starts.')
  if (!form.endDate || !form.endTime) errors.push('Choose when the unavailable period ends.')
  if (errors.length === 0 && `${form.endDate}T${form.endTime}` <= `${form.startDate}T${form.startTime}`) {
    errors.push('The period must end after it starts.')
  }
  if (!form.reason) errors.push('Choose a reason.')
  else if (form.reason === 'other' && !form.note.trim()) errors.push('Describe the operational reason.')
  return errors
}

export function blockFormToPayload(form) {
  return {
    venue_id: form.venueId,
    start_date: form.startDate,
    start_time: form.startTime,
    end_date: form.endDate,
    end_time: form.endTime,
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

// S-77: tell the Coordinators of the bookings a period affects again, after
// the first attempt failed. Nobody is told twice.
export function retryBlockNotifications(id) {
  return requestJSON(`/venue-bookings/blocks/${encodeURIComponent(id)}/notify`, { method: 'POST' })
}

function affectedRow(booking) {
  return [
    booking.event_name,
    bookingDateLabel(booking.booking_date),
    `${shortTime(booking.start_time)}–${shortTime(booking.end_time)}`,
    STATE_META[booking.status]?.label ?? booking.status,
    booking.coordinator_name,
  ].join(' · ')
}

// S-77: what Venue Staff are told once a period is saved -- the bookings it
// affects, and whether their Coordinators know. `retry` shows Notify
// Coordinators. `venueName` is used when the response is a retry's, which
// carries no block.
export function affectedBookingsSummary(response, venueName = response.venue_name) {
  const heading = `${venueName} marked unavailable`
  const affected = response.affected_bookings
  if (affected == null) {
    return {
      heading,
      line: "The period is saved, but we couldn't check which bookings it affects.",
      rows: [],
      retry: true,
    }
  }
  const rows = affected.map(affectedRow)
  if (rows.length === 0) return { heading, line: 'No bookings are affected.', rows, retry: false }
  const count = rows.length === 1
    ? '1 booking needs alternative arrangements.'
    : `${rows.length} bookings need alternative arrangements.`
  if (!response.coordinators_notified) {
    return { heading, line: "The period is saved, but the Coordinators haven't been notified yet.", rows, retry: true }
  }
  return { heading, line: `${count} Their Coordinators have been notified.`, rows, retry: false }
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
