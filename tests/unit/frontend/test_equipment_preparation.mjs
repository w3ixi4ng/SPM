import assert from 'node:assert/strict'
import test from 'node:test'

import { hasPermission, PERMISSIONS } from '../../../frontend/src/lib/access.js'
import {
  EQUIPMENT_PREPARATION_OPTIONS,
  assignedEventWork,
  equipmentPreparationErrorMessage,
  equipmentPreparationLabel,
  updateEquipmentPreparation,
} from '../../../frontend/src/lib/technicalSupportAssignments.js'

test('preparation access labels and update request match the confirmed contract', async () => {
  const roles = ['event_organiser', 'event_coordinator', 'event_coordinator_lead', 'venue_staff', 'technical_support', 'safety_officer', 'attendee']
  assert.deepEqual(
    roles.filter((role) => hasPermission(role, PERMISSIONS.UPDATE_EQUIPMENT_PREPARATION)),
    ['technical_support'],
  )
  assert.deepEqual(EQUIPMENT_PREPARATION_OPTIONS.map(({ value, label }) => [value, label]), [
    ['not_started', 'Not Started'],
    ['in_progress', 'In Progress'],
    ['ready', 'Ready'],
  ])
  assert.equal(equipmentPreparationLabel('ready'), 'Ready')

  const originalFetch = globalThis.fetch
  let request
  globalThis.fetch = async (url, options) => {
    request = { url, options }
    return { ok: true, status: 200, json: async () => ({ equipment_preparation_status: 'ready' }) }
  }
  try {
    await updateEquipmentPreparation('event 1/2', 'ready')
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.equal(request.url, '/api/events/support-assigned/event%201%2F2/equipment-preparation')
  assert.equal(request.options.method, 'PUT')
  assert.equal(request.options.credentials, 'include')
  assert.equal(request.options.body, '{"status":"ready"}')
})

test('dashboard contracts expose editable support and read-only coordinator states', () => {
  const events = [{ id: 'e1', status: 'preparation', equipment_preparation_status: 'ready' }]
  assert.equal(assignedEventWork(events, [])[0].equipment_preparation_status, 'ready')
  assert.equal(equipmentPreparationLabel(), 'Not Started')
  assert.match(equipmentPreparationErrorMessage({ status: 500 }), /not saved/)
  assert.match(equipmentPreparationErrorMessage({ status: 409, message: 'Reload' }), /Reload/)
})
