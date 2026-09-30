import { requestJSON } from './api.js'

// S-44: Technical Support checks how much of each equipment pool is free for
// a window. The equipment_requirements composite does the counting from live
// data on every check; this file only decides what the browser sends and how
// the answer reads.

const GREEN = '#3F8F5F'
const AMBER = '#B5842B'
const ROSE = '#B25547'

export function emptyAvailabilityForm(today) {
  return { startDate: today, startTime: '', endDate: today, endTime: '', type: '', quantity: '' }
}

function isWholeNumberOfOneOrMore(value) {
  return /^\d+$/.test(value) && Number(value) >= 1
}

// Every problem at once, before anything is sent. The service checks the
// same rules again.
export function validateAvailabilityForm(form) {
  const errors = []
  const hasStart = Boolean(form.startDate && form.startTime)
  const hasEnd = Boolean(form.endDate && form.endTime)
  if (!hasStart) errors.push('Choose a start date and time.')
  if (!hasEnd) errors.push('Choose an end date and time.')
  // ISO dates and 24-hour times compare correctly as text.
  if (hasStart && hasEnd && `${form.endDate}T${form.endTime}` <= `${form.startDate}T${form.startTime}`) {
    errors.push('The end must be after the start.')
  }
  const quantity = form.quantity.trim()
  if (quantity && !isWholeNumberOfOneOrMore(quantity)) {
    errors.push('Enter a whole number of 1 or more, or leave it blank.')
  }
  return errors
}

export function availabilityQuery(form) {
  const params = new URLSearchParams({
    start_date: form.startDate,
    start_time: form.startTime,
    end_date: form.endDate,
    end_time: form.endTime,
  })
  const type = form.type.trim()
  if (type) params.set('type', type)
  const quantity = form.quantity.trim()
  if (quantity) params.set('quantity', quantity)
  return params.toString()
}

// Always a fresh request: the answer is only as current as the check.
export function checkEquipmentAvailability(form) {
  return requestJSON(`/equipment-requirements/availability?${availabilityQuery(form)}`)
}

const STATUS_LABELS = { maintenance: 'Maintenance', unavailable: 'Unavailable' }

// How one item reads: how many are free out of the pool, why none are when
// the pool is out of service, and -- given a quantity -- whether that is
// enough. Every status carries words; the colour only repeats them.
export function availabilitySummary(item) {
  const outOfService = item.operational_status !== 'available'
  let headline = `${item.available} of ${item.total} available`
  if (outOfService) headline += ` — ${STATUS_LABELS[item.operational_status] ?? item.operational_status}`
  else if (item.over_reserved) headline += ` — over-reserved by ${item.reserved - item.total}`

  let verdict = null
  if (item.sufficient === true) verdict = { label: 'Enough', color: GREEN }
  else if (item.sufficient === false) {
    verdict = { label: outOfService ? 'Not enough' : `Not enough — ${item.available} available`, color: ROSE }
  }

  return {
    headline,
    headlineColor: outOfService ? AMBER : null,
    reserved: `${item.reserved} reserved`,
    verdict,
  }
}

export function availabilityErrorMessages(error) {
  if (error.status === 422 && error.fieldErrors) {
    const messages = Object.values(error.fieldErrors)
    if (messages.length > 0) return messages
  }
  if (error.status === 401) return ['Your session has expired. Please sign in again.']
  if (error.status === 403) return ['Only Technical Support can check equipment availability.']
  return ["We couldn't check availability. Nothing is shown until it works — try again in a moment."]
}

// "Checked at 14:32", in the viewer's own clock.
export function checkedAtLabel(iso, timeZone) {
  const time = new Date(iso).toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit', hour12: false, ...(timeZone ? { timeZone } : {}),
  })
  return `Checked at ${time}`
}
