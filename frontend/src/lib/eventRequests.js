const STORAGE_KEY = 'connectsphere.eventRequests'

<<<<<<< Updated upstream
function readAll() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function writeAll(records) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(records))
  } catch {
    // storage unavailable (private mode, quota) — the draft just won't survive a reload
=======
const TEXT_FIELDS = {
  name: 'name',
  purpose: 'purpose',
  venue: 'venue',
  accessibility: 'accessibility_requirements',
}

const VALUE_FIELDS = {
  startDate: 'start_date',
  endDate: 'end_date',
  startTime: 'start_time',
  endTime: 'end_time',
}

const API_TO_FORM_FIELD = {
  name: 'name',
  purpose: 'purpose',
  start_date: 'startDate',
  end_date: 'endDate',
  start_time: 'startTime',
  end_time: 'endTime',
  expected_attendance: 'attendance',
  venue: 'venue',
  equipment_requests: 'equipmentRequests',
  accessibility_requirements: 'accessibility',
}

function equipmentPayload(equipmentRequests = {}) {
  return Object.fromEntries(
    Object.entries(equipmentRequests)
      .filter(([, quantity]) => quantity !== '' && Number(quantity) > 0)
      .map(([name, quantity]) => [name, Number(quantity)]),
  )
}

export function eventFormToPayload(form, { omitEmpty = false } = {}) {
  const payload = {}

  for (const [formField, apiField] of Object.entries(TEXT_FIELDS)) {
    const value = form[formField]?.trim() ?? ''
    if (value) payload[apiField] = value
    else if (!omitEmpty) payload[apiField] = null
  }

  for (const [formField, apiField] of Object.entries(VALUE_FIELDS)) {
    const value = form[formField] || null
    if (value !== null || !omitEmpty) payload[apiField] = value
  }

  if (form.attendance !== '') {
    payload.expected_attendance = Number(form.attendance)
  } else if (!omitEmpty) {
    payload.expected_attendance = null
  }

  payload.equipment_requests = equipmentPayload(form.equipmentRequests)
  return payload
}

export function eventResponseToForm(event) {
  return {
    id: event.id,
    name: event.name ?? '',
    purpose: event.purpose ?? '',
    startDate: event.start_date ?? '',
    endDate: event.end_date ?? '',
    startTime: event.start_time?.slice(0, 5) ?? '',
    endTime: event.end_time?.slice(0, 5) ?? '',
    attendance: event.expected_attendance?.toString() ?? '',
    venue: event.venue ?? '',
    equipmentRequests: event.equipment_requests ?? {},
    accessibility: event.accessibility_requirements ?? '',
  }
}

export function eventFieldErrorsToForm(fieldErrors) {
  const mapped = {}
  for (const [path, message] of Object.entries(fieldErrors ?? {})) {
    const apiField = path.split('.')[0]
    const formField = API_TO_FORM_FIELD[apiField]
    if (formField) mapped[formField] = message
    else if (message.includes('end must be after start')) {
      mapped.endDateTime = 'The event must end after it starts.'
    }
>>>>>>> Stashed changes
  }
}

// Placeholder for the events service — swap the body for an HTTP call and
// keep this signature so callers don't change.
export function getEventRequest(id) {
  if (!id) return null
  return readAll()[id] ?? null
}

export function saveEventRequest(data, status) {
  const records = readAll()
  const id =
    data.id ||
    `evt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
  const record = { ...data, id, status, updatedAt: new Date().toISOString() }
  records[id] = record
  writeAll(records)
  return record
}
