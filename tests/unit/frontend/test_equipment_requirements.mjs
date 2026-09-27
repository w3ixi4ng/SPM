import assert from 'node:assert/strict'
import test from 'node:test'

import {
  listEquipmentRequirements,
  removeEquipmentRequirement,
  requirementErrorMessage,
  saveEquipmentRequirement,
  validateRequirementQuantity,
} from '../../../frontend/src/lib/equipmentRequirements.js'

test('requirement quantity accepts only positive whole numbers', () => {
  assert.equal(validateRequirementQuantity('4'), null)
  assert.match(validateRequirementQuantity(''), /enter/i)
  assert.match(validateRequirementQuantity('0'), /at least 1/i)
  assert.match(validateRequirementQuantity('-2'), /at least 1/i)
  assert.match(validateRequirementQuantity('1.5'), /whole number/i)
})

test('requirement API uses the composite route and numeric quantity', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    if (options.method === 'DELETE') return new Response(null, { status: 204 })
    return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }

  try {
    await listEquipmentRequirements('event id')
    await listEquipmentRequirements()
    await saveEquipmentRequirement('event-1', 'item-1', '3')
    await removeEquipmentRequirement('event-1', 'item-1')
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(calls[0].url, '/api/equipment-requirements?event_id=event%20id')
  assert.equal(calls[1].url, '/api/equipment-requirements')
  assert.equal(calls[2].url, '/api/equipment-requirements/event-1/item-1')
  assert.equal(calls[2].options.method, 'PUT')
  assert.deepEqual(JSON.parse(calls[2].options.body), { required_quantity: 3 })
  assert.equal(calls[3].options.method, 'DELETE')
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
})

test('requirement errors give safe role, lifecycle and dependency feedback', () => {
  assert.match(requirementErrorMessage({ status: 403 }), /not permitted/i)
  assert.equal(requirementErrorMessage({ status: 409, message: 'Planning only' }), 'Planning only')
  assert.match(requirementErrorMessage({ status: 502 }), /temporarily unavailable/i)
})
