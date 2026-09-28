import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createEquipment,
  emptyEquipmentForm,
  equipmentErrorMessage,
  equipmentFieldErrorsToForm,
  equipmentReadToForm,
  equipmentRetirementErrorMessage,
  equipmentStatusLabel,
  equipmentUpdateFormToPayload,
  canRetireEquipment,
  getEquipment,
  listEquipment,
  listEquipmentSelection,
  retireEquipment,
  updateEquipment,
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

const UPDATE_FORM = {
  type: '  Radio Microphone  ',
  description: '   ',
  totalQuantity: '18',
  operationalStatus: 'maintenance',
  id: 'must-not-be-sent',
  lifecycle_status: 'retired',
  created_by: 'must-not-be-sent',
  created_at: 'must-not-be-sent',
  updated_at: 'must-not-be-sent',
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

// --- TC-FRONTEND-044 -----------------------------------------------------
test('equipment edit mapping accepts exactly the S-41 fields and statuses', () => {
  assert.deepEqual(equipmentReadToForm(API_ITEM), {
    type: 'Wireless Microphone',
    description: 'Handheld wireless microphone with receiver',
    totalQuantity: '12',
    operationalStatus: 'available',
  })
  assert.deepEqual(equipmentUpdateFormToPayload(UPDATE_FORM), {
    type: 'Radio Microphone',
    description: null,
    total_quantity: 18,
    operational_status: 'maintenance',
  })

  for (const operationalStatus of ['available', 'unavailable', 'maintenance']) {
    assert.deepEqual(validateEquipmentForm({ ...UPDATE_FORM, operationalStatus }, { editing: true }), {})
  }
  assert.match(
    validateEquipmentForm({ ...UPDATE_FORM, operationalStatus: 'damaged' }, { editing: true }).operational_status,
    /status/i,
  )
})

// --- TC-FRONTEND-045 -----------------------------------------------------
test('equipment detail and update use authenticated Kong routes', async () => {
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
    await getEquipment('item/1')
    await updateEquipment('item/1', UPDATE_FORM)
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(({ url, options }) => [options.method ?? 'GET', url]), [
    ['GET', '/api/equipment/item%2F1'],
    ['PUT', '/api/equipment/item%2F1'],
  ])
  assert.equal(calls.every(({ options }) => options.credentials === 'include'), true)
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    type: 'Radio Microphone',
    description: null,
    total_quantity: 18,
    operational_status: 'maintenance',
  })
})

// --- TC-FRONTEND-046 -----------------------------------------------------
test('equipment catalogue status labels reflect stored state', () => {
  assert.equal(equipmentStatusLabel(API_ITEM), 'Available · Active')
  assert.equal(
    equipmentStatusLabel({ ...API_ITEM, operational_status: 'unavailable' }),
    'Unavailable · Active',
  )
  assert.equal(
    equipmentStatusLabel({ ...API_ITEM, operational_status: 'maintenance', lifecycle_status: 'retired' }),
    'Maintenance · Retired',
  )
})

// --- TC-FRONTEND-048 -----------------------------------------------------
test('retirement uses the authenticated item action without a lifecycle payload', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ ...API_ITEM, lifecycle_status: 'retired' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    const retired = await retireEquipment('item/1')
    assert.equal(retired.lifecycle_status, 'retired')
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(({ url, options }) => [options.method, url]), [
    ['POST', '/api/equipment/item%2F1/retire'],
  ])
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[0].options.body, undefined)
})

// --- TC-FRONTEND-049 -----------------------------------------------------
test('retirement actions and labels follow lifecycle state', () => {
  assert.equal(canRetireEquipment(API_ITEM), true)
  const retired = { ...API_ITEM, lifecycle_status: 'retired' }
  assert.equal(canRetireEquipment(retired), false)
  assert.equal(equipmentStatusLabel(retired), 'Available · Retired')
})

// --- TC-FRONTEND-050 -----------------------------------------------------
test('retirement failures are safe and actionable', () => {
  assert.match(equipmentRetirementErrorMessage({ status: 401 }), /sign in again/i)
  assert.match(equipmentRetirementErrorMessage({ status: 403 }), /not permitted/i)
  assert.match(equipmentRetirementErrorMessage({ status: 404 }), /could not be found/i)
  assert.match(equipmentRetirementErrorMessage({ status: 500 }), /not been retired/i)
})
