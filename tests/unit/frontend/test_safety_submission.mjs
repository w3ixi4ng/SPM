import assert from 'node:assert/strict'
import test from 'node:test'

import { eventStatusMeta, organiserStatusMeta, organiserTabs } from '../../../frontend/src/lib/eventRequests.js'
import {
  buildSubmissionReadiness,
  describeSignoff,
  signOffEquipment,
  signoffPayload,
  submissionErrorMessage,
  submitForSafetyCheck,
} from '../../../frontend/src/lib/safetySubmission.js'

function stubFetch(status, body) {
  const calls = []
  const original = globalThis.fetch
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }
  return { calls, restore: () => { globalThis.fetch = original } }
}

const SIX = [
  { code: 'venue_missing', label: 'No venue booking has been confirmed yet' },
  { code: 'venue_awaiting', booking_id: 'b2', label: 'Studio 2 on 20 Nov 2026 is waiting for Venue Staff' },
  { code: 'venue_rejected', booking_id: 'b3', label: 'Room 5 on 20 Nov 2026 was rejected — request a replacement venue' },
  { code: 'technical_support_unassigned', label: 'Technical Support has not been assigned' },
  { code: 'technical_signoff_awaiting', label: 'Technical Support has not approved the equipment arrangements' },
  { code: 'equipment_preparation', label: 'Equipment preparation is Not Started' },
]

// TC-FRONTEND-132
test('labels the new stage', () => {
  assert.deepEqual(eventStatusMeta('pending_safety_check'), { label: 'Pending Safety Check', color: '#B5842B' })
  assert.deepEqual(eventStatusMeta('confirmed'), { label: 'Confirmed', color: '#3F8F5F' })
  assert.equal(eventStatusMeta('preparation').label, 'Preparation')
  assert.equal(organiserStatusMeta('pending_safety_check').label, 'Pending Safety Check')
  const [active] = organiserTabs([{ id: 'e1', status: 'pending_safety_check' }])
  assert.deepEqual(active.events.map((event) => event.id), ['e1'])
})

// TC-FRONTEND-133
test('builds readiness from the server', () => {
  assert.deepEqual(buildSubmissionReadiness({ ready: true, outstanding: [] }), { canSubmit: true, items: [] })

  const view = buildSubmissionReadiness({ ready: false, outstanding: SIX })
  assert.equal(view.canSubmit, false)
  assert.deepEqual(view.items.map((item) => item.label), SIX.map((item) => item.label))
  assert.ok(view.items.every((item) => item.statusLabel === 'Outstanding'))
  assert.equal(new Set(view.items.map((item) => item.key)).size, 6)
})

// TC-FRONTEND-134
test('handles each submit outcome', async () => {
  let fake = stubFetch(200, { status: 'pending_safety_check' })
  try {
    assert.deepEqual(await submitForSafetyCheck('E1'), { status: 'pending_safety_check' })
    assert.equal(fake.calls[0].url, '/api/safety-checks/coordinator/events/E1/submit')
    assert.equal(fake.calls[0].options.method, 'POST')
    assert.equal(fake.calls[0].options.body, undefined)
    assert.equal(fake.calls[0].options.credentials, 'include')
  } finally { fake.restore() }

  fake = stubFetch(409, { detail: 'This event has outstanding arrangements', outstanding: SIX.slice(0, 2) })
  try {
    await assert.rejects(submitForSafetyCheck('E1'), (error) => {
      assert.deepEqual(error.outstanding, SIX.slice(0, 2))
      assert.match(submissionErrorMessage(error), /Complete each item below/)
      return true
    })
  } finally { fake.restore() }

  fake = stubFetch(409, { detail: 'This event is not in planning' })
  try {
    await assert.rejects(submitForSafetyCheck('E1'), (error) => {
      assert.equal(error.outstanding, undefined)
      assert.equal(submissionErrorMessage(error), 'This event is not in planning. Reload the page to see its current status.')
      return true
    })
  } finally { fake.restore() }

  fake = stubFetch(502, { detail: 'Bookings service unavailable' })
  try {
    await assert.rejects(submitForSafetyCheck('E1'), (error) => {
      assert.match(submissionErrorMessage(error), /nothing was submitted\. Try again/)
      return true
    })
  } finally { fake.restore() }
})

// TC-FRONTEND-135
test('builds sign-off payloads', async () => {
  assert.deepEqual(signoffPayload({ decision: 'approved' }), { payload: { decision: 'approved' } })
  assert.deepEqual(
    signoffPayload({ decision: 'approved', overrideComment: ' Borrowing 2 projectors from Library ' }),
    { payload: { decision: 'approved', override_comment: 'Borrowing 2 projectors from Library' } },
  )
  assert.deepEqual(
    signoffPayload({ decision: 'declined', reason: 'Only one sound desk exists' }),
    { payload: { decision: 'declined', reason: 'Only one sound desk exists' } },
  )
  assert.deepEqual(signoffPayload({ decision: 'declined', reason: '   ' }), { error: 'Enter a reason for declining' })

  const short = [{ equipment_item_id: 'p1', name: 'Projector', required: 4, available: 2 }]
  const fake = stubFetch(409, { detail: 'Some equipment is short for this event', short })
  try {
    await assert.rejects(signOffEquipment('E1', { decision: 'approved' }), (error) => {
      assert.deepEqual(error.short, short)
      return true
    })
    assert.equal(fake.calls[0].url, '/api/equipment-requirements/E1/sign-off')
    assert.equal(fake.calls[0].options.body, JSON.stringify({ decision: 'approved' }))
  } finally { fake.restore() }
})

// TC-FRONTEND-136
test('describes the sign-off', () => {
  assert.deepEqual(describeSignoff({}), { label: 'Awaiting Technical Support', note: null })
  assert.deepEqual(
    describeSignoff({ technical_signoff_decision: 'approved' }),
    { label: 'Approved by Technical Support', note: null },
  )
  assert.deepEqual(
    describeSignoff({
      technical_signoff_decision: 'approved',
      technical_signoff_override_comment: 'Borrowing 2 projectors from Library',
    }),
    { label: 'Approved by Technical Support', note: 'Borrowing 2 projectors from Library' },
  )
  assert.deepEqual(
    describeSignoff({ technical_signoff_decision: 'declined', technical_signoff_reason: 'Only one sound desk exists' }),
    { label: 'Declined by Technical Support', note: 'Only one sound desk exists' },
  )
})

// Supports TC-VENUEBOOKINGS-099 and TC-SAFETYCHECKS-026: a rejected booking
// offers a replacement (never "Mark resolved"); a rejected replacement
// request offers nothing, since its original is what still needs one.
test('offers a replacement for a rejected booking', async () => {
  const { replacementState } = await import('../../../frontend/src/lib/venueBookings.js')
  const B2 = { id: 'b2', status: 'rejected', venue_name: 'Studio 2' }
  assert.deepEqual(replacementState(B2, [B2]), { actions: ['replace'], label: null })

  const waiting = { id: 'b3', status: 'pending', venue_name: 'Studio 3', replaces_booking_id: 'b2' }
  assert.deepEqual(replacementState(B2, [B2, waiting]), {
    actions: [], label: 'Replacement requested: Studio 3, waiting for Venue Staff',
  })

  const declined = { ...waiting, status: 'rejected' }
  assert.deepEqual(replacementState(B2, [B2, declined]), {
    actions: ['replace'], label: 'Studio 3 declined the replacement request',
  })
  assert.deepEqual(replacementState(declined, [B2, declined]), {
    actions: [], label: 'Replacement for Studio 2',
  })
})
