import { requestJSON } from './api.js'

export function validateRequirementQuantity(value) {
  const quantity = String(value ?? '').trim()
  if (!quantity) return 'Enter a required quantity.'
  if (!/^\d+$/.test(quantity) || Number(quantity) < 1) {
    return 'Required quantity must be a whole number of at least 1.'
  }
  return null
}

export function requirementErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return 'You are not permitted to manage these requirements.'
  if (error.status === 404) return 'The event or equipment item could not be found.'
  if (error.status === 409) return error.message || 'Requirements can only be edited during planning.'
  if (error.status === 422) return 'Enter a valid required quantity.'
  if (error.status >= 500) return 'Equipment requirements are temporarily unavailable.'
  return error.message || "We couldn't reach the equipment requirements service."
}

export function listEquipmentRequirements(eventId) {
  const query = eventId ? `?event_id=${encodeURIComponent(eventId)}` : ''
  return requestJSON(`/equipment-requirements${query}`)
}

export function saveEquipmentRequirement(eventId, equipmentItemId, quantity, impactAccepted = false) {
  return requestJSON(`/equipment-requirements/${encodeURIComponent(eventId)}/${encodeURIComponent(equipmentItemId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ required_quantity: Number(quantity), impact_accepted: impactAccepted }),
  })
}

export function removeEquipmentRequirement(eventId, equipmentItemId, impactAccepted = false) {
  const query = impactAccepted ? '?impact_accepted=true' : ''
  return requestJSON(`/equipment-requirements/${encodeURIComponent(eventId)}/${encodeURIComponent(equipmentItemId)}${query}`, {
    method: 'DELETE',
  })
}
