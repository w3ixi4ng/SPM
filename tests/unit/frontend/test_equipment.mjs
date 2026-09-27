import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createEquipment,
  emptyEquipmentForm,
  equipmentErrorMessage,
  equipmentFieldErrorsToForm,
  listEquipment,
  listEquipmentSelection,
  validateEquipmentForm,
} from '../../../frontend/src/lib/equipment.js'

const COMPLETE_FORM = {
  type: '  Wireless Microphone  ',
  description: '  Handheld wireless microphone with receiver  ',
  totalQuantity: '12',
  id: 'must-not-be-sent',
  operational_status: 'maintenance',
  lifecycle_status: 'retired',
  created_by: 'must-not-be-sent',
}

const API_ITEM = {
  id: '22222222-2222-4222-8222-222222222222',
  type: 'Wireless Microphone',
  description: 'Handheld wireless microphone with receiver',
  total_quantity: 12,
  operational_status: 'available',
  lifecycle_status: 'active',
}

// --- TC-FRONTEND-036 ----------------------------------------------------
test('equipment form validates required catalogue fields', () => {
  assert.deepEqual(validateEquipmentForm(emptyEquipmentForm()), {
    type: 'Enter the equipment type.',
    total_quantity: 'Enter the total quantity.',
  })

  for (const totalQuantity of ['0', '-1', '1.5']) {
    assert.match(
      validateEquipmentForm({ ...COMPLETE_FORM, totalQuantity }).total_quantity,
      /whole number of at least 1/,
    )
  }

  assert.deepEqual(validateEquipmentForm(COMPLETE_FORM), {})
})

// --- TC-FRONTEND-037 ----------------------------------------------------
test('equipment operations use authenticated Kong routes and safe payloads', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify(API_ITEM), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    await listEquipment()
    await listEquipmentSelection()
    await createEquipment(COMPLETE_FORM)
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(({ url, options }) => [options.method ?? 'GET', url]), [
    ['GET', '/api/equipment'],
    ['GET', '/api/equipment/selection'],
    ['POST', '/api/equipment'],
  ])
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    type: 'Wireless Microphone',
    description: 'Handheld wireless microphone with receiver',
    total_quantity: 12,
  })
})

// --- TC-FRONTEND-038 ----------------------------------------------------
test('equipment errors are safe and actionable', () => {
  assert.match(equipmentErrorMessage({ status: 401 }), /sign in again/i)
  assert.match(equipmentErrorMessage({ status: 403 }), /not permitted/i)
  assert.match(equipmentErrorMessage({ status: 422 }), /highlighted/i)
  assert.match(equipmentErrorMessage({ status: 500 }), /not been saved/i)
  assert.deepEqual(
    equipmentFieldErrorsToForm({
      type: 'String should have at least 1 character',
      total_quantity: 'Input should be greater than 0',
    }),
    {
      type: 'String should have at least 1 character',
      total_quantity: 'Input should be greater than 0',
    },
  )
})
