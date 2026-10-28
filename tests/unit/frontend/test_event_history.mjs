import assert from 'node:assert/strict'
import test from 'node:test'

import {
  HISTORY_ACTIONS,
  describeChanges,
  describeEntry,
  entryActor,
  entryTime,
  historyPath,
} from '../../../frontend/src/lib/eventHistory.js'

// TC-FRONTEND-274
test('each role reads history from its own route', () => {
  assert.equal(historyPath('event_coordinator', 'E1'), '/event-requests/E1/history')
  assert.equal(historyPath('event_coordinator_lead', 'E1'), '/event-requests/E1/history')
  assert.equal(historyPath('safety_officer', 'E1'), '/safety-checks/E1/history')
  for (const role of ['event_organiser', 'technical_support', 'venue_staff', 'attendee', undefined]) {
    assert.equal(historyPath(role, 'E1'), null)
  }
})

// TC-FRONTEND-275
test('each action reads as a plain sentence', () => {
  const people = { C: 'Alex Coordinator', C2: 'Blair Coordinator', T: 'Tay Support' }
  const cases = [
    ['submitted', {}, 'Submitted the event request'],
    ['submitted', { resubmission: true }, 'Resubmitted the event request'],
    ['request_approved', {}, 'Approved the event request'],
    ['request_returned', { reason: 'Add a contact' }, 'Returned the event request: Add a contact'],
    ['coordinator_assigned', { coordinator_id: 'C' }, 'Assigned Alex Coordinator'],
    ['coordinator_reassigned', { from_coordinator_id: 'C', to_coordinator_id: 'C2' },
      'Reassigned from Alex Coordinator to Blair Coordinator'],
    ['technical_support_assigned', { technical_support_id: 'T' }, 'Assigned Tay Support to technical support'],
    ['venue_confirmed', { venue_name: 'Hall One' }, 'Confirmed Hall One'],
    ['venue_rejected', { venue_name: 'Hall One', reason: 'Under renovation' }, 'Rejected Hall One: Under renovation'],
    ['equipment_requirement_set', { item_name: 'Projector', from_quantity: 2, to_quantity: 5 },
      'Changed Projector from 2 to 5'],
    ['safety_changes_requested', { reason: 'Fire exit blocked' }, 'Requested safety changes: Fire exit blocked'],
    ['coordinator_assigned', { coordinator_id: 'Z' }, 'Assigned a removed account'],
    ['made_up', {}, 'Made up'],
  ]
  for (const [action, details, expected] of cases) {
    assert.equal(describeEntry({ action, details }, people), expected)
  }

  const recorded = [
    'submitted', 'edited', 'request_approved', 'request_rejected', 'request_returned',
    'cancellation_requested', 'cancellation_approved', 'cancellation_declined',
    'coordinator_assigned', 'reassignment_requested', 'coordinator_reassigned', 'technical_support_assigned',
    'technical_signoff_approved', 'technical_signoff_declined', 'equipment_preparation_changed',
    'safety_submitted', 'safety_resubmitted', 'safety_approved', 'safety_changes_requested', 'safety_rejected',
    'venue_requested', 'venue_request_changed', 'venue_request_withdrawn', 'venue_replacement_requested',
    'venue_alternative_resolved', 'venue_held', 'venue_released', 'venue_confirmed', 'venue_rejected',
    'equipment_requirement_set', 'equipment_requirement_removed',
  ]
  assert.deepEqual([...recorded].sort(), [...HISTORY_ACTIONS].sort())
})

// TC-FRONTEND-276
test('an edit lists each changed field', () => {
  assert.deepEqual(
    describeChanges({
      expected_attendance: { before: 120, after: 150 },
      internal_notes: { before: null, after: 'Check lift access' },
      required_accessibility: { before: ['lift'], after: ['lift', 'hearing_loop'] },
      start_date: { before: '2026-11-18', after: '2026-11-19' },
    }),
    [
      'Expected attendance: 120 → 150',
      'Internal notes: (none) → Check lift access',
      'Accessibility: Lift → Lift, Hearing loop',
      'Start date: 18 Nov 2026 → 19 Nov 2026',
    ],
  )
})

// TC-FRONTEND-277
test('who and when are shown plainly', () => {
  assert.equal(
    entryActor({ actor: { name: 'Blair Coordinator', role: 'event_coordinator' } }),
    'Blair Coordinator, Event Coordinator',
  )
  assert.equal(entryActor({ actor: { name: null, role: 'venue_staff' } }), 'A removed account, Venue Staff')
  assert.equal(entryActor({ actor: null }), 'Not recorded')
  assert.equal(entryTime({ occurred_at: '2026-10-27T06:05:00Z' }), '27 Oct 2026, 2:05 pm')
  assert.equal(entryTime({ occurred_at: '2026-10-27T16:30:00Z' }), '28 Oct 2026, 12:30 am')
})
