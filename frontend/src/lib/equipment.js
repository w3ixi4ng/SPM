import { requestJSON } from './api.js'

export function emptyEquipmentForm() {
  return {
    type: '', description: '', storageLocation: '', totalQuantity: '', operationalStatus: 'available',
  }
}

export const EQUIPMENT_OPERATIONAL_STATUSES = Object.freeze([
  'available',
  'unavailable',
  'maintenance',
])

export function validateEquipmentForm(form, { editing = false } = {}) {
  const errors = {}
  if (!form.type?.trim()) errors.type = 'Enter the equipment type.'
  if ((form.storageLocation?.trim().length ?? 0) > 200) {
    errors.storage_location = 'Storage location must be 200 characters or fewer.'
  }

  const quantity = String(form.totalQuantity ?? '').trim()
  if (!quantity) errors.total_quantity = 'Enter the total quantity.'
  else if (!/^\d+$/.test(quantity) || Number(quantity) < 1) {
    errors.total_quantity = 'Total quantity must be a whole number of at least 1.'
  }
  if (editing && !EQUIPMENT_OPERATIONAL_STATUSES.includes(form.operationalStatus)) {
    errors.operational_status = 'Choose a valid operational status.'
  }
  return errors
}

export function equipmentFormToPayload(form) {
  const description = form.description?.trim() ?? ''
  const storageLocation = form.storageLocation?.trim() ?? ''
  return {
    type: form.type.trim(),
    description: description || null,
    storage_location: storageLocation || null,
    total_quantity: Number(String(form.totalQuantity).trim()),
  }
}

export function equipmentReadToForm(item) {
  return {
    type: item.type ?? '',
    description: item.description ?? '',
    storageLocation: item.storage_location ?? '',
    totalQuantity: String(item.total_quantity ?? ''),
    operationalStatus: item.operational_status ?? 'available',
  }
}

export function equipmentUpdateFormToPayload(form) {
  return {
    ...equipmentFormToPayload(form),
    operational_status: form.operationalStatus,
  }
}

function titleCaseStatus(value) {
  return String(value ?? '')
    .split('_')
    .filter(Boolean)
    .map((part) => `${part[0].toUpperCase()}${part.slice(1)}`)
    .join(' ')
}

export function equipmentStatusLabel(item) {
  return `${titleCaseStatus(item.operational_status)} · ${titleCaseStatus(item.lifecycle_status)}`
}

export function equipmentStorageLocationLabel(item) {
  return item?.storage_location ? `Stored at ${item.storage_location}` : 'Storage location not recorded'
}

export function canRetireEquipment(item) {
  return item?.lifecycle_status === 'active'
}

export function equipmentFieldErrorsToForm(fieldErrors) {
  return Object.fromEntries(
    Object.entries(fieldErrors ?? {}).map(([field, message]) => [
      field,
      message.replace(/^Value error, /, ''),
    ]),
  )
}

export function equipmentErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Your role is not permitted to manage equipment.'
  if (error.status === 404) return 'This equipment item could not be found.'
  if (error.status === 422) return 'Please check the highlighted equipment details.'
  if (error.status >= 500) return 'The equipment service is unavailable. The item has not been saved.'
  return error.message || "We couldn't reach the equipment service. The item has not been saved."
}

export function equipmentRetirementErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'Your role is not permitted to retire equipment.'
  if (error.status === 404) return 'This equipment item could not be found.'
  if (error.status >= 500) return 'The equipment service is unavailable. The item has not been retired.'
  return error.message || "We couldn't reach the equipment service. The item has not been retired."
}

export function listEquipment() {
  return requestJSON('/equipment')
}

export function listEquipmentSelection() {
  return requestJSON('/equipment/selection')
}

export function getEquipment(itemId) {
  return requestJSON(`/equipment/${encodeURIComponent(itemId)}`)
}

export function createEquipment(form) {
  return requestJSON('/equipment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(equipmentFormToPayload(form)),
  })
}

export function updateEquipment(itemId, form) {
  return requestJSON(`/equipment-requirements/equipment/${encodeURIComponent(itemId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(equipmentUpdateFormToPayload(form)),
  })
}

export function retireEquipment(itemId) {
  return requestJSON(`/equipment-requirements/equipment/${encodeURIComponent(itemId)}/retire`, {
    method: 'POST',
  })
}
