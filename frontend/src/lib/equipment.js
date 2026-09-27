import { requestJSON } from './api.js'

export function emptyEquipmentForm() {
  return { type: '', description: '', totalQuantity: '' }
}

export function validateEquipmentForm(form) {
  const errors = {}
  if (!form.type?.trim()) errors.type = 'Enter the equipment type.'

  const quantity = String(form.totalQuantity ?? '').trim()
  if (!quantity) errors.total_quantity = 'Enter the total quantity.'
  else if (!/^\d+$/.test(quantity) || Number(quantity) < 1) {
    errors.total_quantity = 'Total quantity must be a whole number of at least 1.'
  }
  return errors
}

export function equipmentFormToPayload(form) {
  const description = form.description?.trim() ?? ''
  return {
    type: form.type.trim(),
    description: description || null,
    total_quantity: Number(String(form.totalQuantity).trim()),
  }
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
  if (error.status === 422) return 'Please check the highlighted equipment details.'
  if (error.status >= 500) return 'The equipment service is unavailable. The item has not been saved.'
  return error.message || "We couldn't reach the equipment service. The item has not been saved."
}

export function listEquipment() {
  return requestJSON('/equipment')
}

export function listEquipmentSelection() {
  return requestJSON('/equipment/selection')
}

export function createEquipment(form) {
  return requestJSON('/equipment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(equipmentFormToPayload(form)),
  })
}
