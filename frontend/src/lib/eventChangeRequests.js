import { requestJSON } from './api.js'

export const CHANGE_REQUEST_STATUSES = new Set([
  'submitted', 'under_review', 'returned', 'planning',
  'pending_safety_check', 'confirmed', 'preparation',
])

export const CHANGE_FIELDS = [
  ['start_date', 'Start date'], ['start_time', 'Start time'],
  ['end_date', 'End date'], ['end_time', 'End time'],
  ['expected_attendance', 'Expected attendance'],
  ['venue', 'Venue preference'], ['special_requirements', 'Special requirements'],
  ['room_layout', 'Room layout'], ['required_facilities', 'Facilities'],
  ['required_accessibility', 'Accessibility'],
]

const LIST_FIELDS = new Set(['required_facilities', 'required_accessibility'])

export function changeValues(event) {
  return Object.fromEntries(CHANGE_FIELDS.map(([field]) => {
    let value = event[field]
    if (LIST_FIELDS.has(field)) value = [...new Set(value ?? [])].sort()
    else if (field === 'expected_attendance') value = value === '' || value == null ? null : Number(value)
    else if (field.endsWith('_time')) value = value?.slice(0, 5) ?? ''
    else if (typeof value === 'string') {
      value = value.trim()
      if (['venue', 'special_requirements', 'room_layout'].includes(field) && !value) value = null
    }
    return [field, value ?? null]
  }))
}

export function equipmentSnapshot(items) {
  return items.map((item) => ({
    equipment_item_id: item.equipment_item_id,
    required_quantity: Number(item.required_quantity),
  })).sort((a, b) => a.equipment_item_id.localeCompare(b.equipment_item_id))
}

export function durationMinutes(values) {
  const start = Date.parse(`${values.start_date}T${values.start_time}Z`)
  const end = Date.parse(`${values.end_date}T${values.end_time}Z`)
  return Number.isFinite(start) && Number.isFinite(end) ? Math.round((end - start) / 60000) : 0
}

export function endFromDuration(values, minutes) {
  const start = Date.parse(`${values.start_date}T${values.start_time}Z`)
  if (!Number.isFinite(start) || !Number.isInteger(minutes) || minutes <= 0) return null
  const end = new Date(start + minutes * 60000)
  return { end_date: end.toISOString().slice(0, 10), end_time: end.toISOString().slice(11, 16) }
}

export function changedFields(accepted, proposed, acceptedEquipment, proposedEquipment) {
  const before = changeValues(accepted)
  const after = changeValues(proposed)
  const changed = CHANGE_FIELDS.filter(([field]) => JSON.stringify(before[field]) !== JSON.stringify(after[field]))
    .map(([field]) => field)
  if (JSON.stringify(equipmentSnapshot(acceptedEquipment)) !== JSON.stringify(equipmentSnapshot(proposedEquipment))) {
    changed.push('equipment')
  }
  return changed
}

export function getEventChangeRequests(id) {
  return requestJSON(`/event-requests/${encodeURIComponent(id)}/change-requests`)
}

export function submitEventChangeRequest(id, values, equipment) {
  return requestJSON(`/event-requests/${encodeURIComponent(id)}/change-requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values, equipment: equipmentSnapshot(equipment) }),
  })
}
