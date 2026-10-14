import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  decideSafetyCheck,
  getSafetyCheck,
  listSafetyChecks,
  safetyCheckErrorMessage,
} from '../../../frontend/src/lib/safetyChecks.js'


test('safety-check helpers use credentialled composite routes', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return new Response(JSON.stringify(url.endsWith('/decision')
      ? { status: 'preparation', safety_decision: 'approved' }
      : []), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }

  try {
    await listSafetyChecks()
    await getSafetyCheck('event-1')
    await decideSafetyCheck('event-1', { decision: 'approved', reason: null })
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(calls[0].url, '/api/safety-checks')
  assert.equal(calls[1].url, '/api/safety-checks/event-1')
  assert.equal(calls[2].url, '/api/safety-checks/event-1/decision')
  assert.equal(calls[2].options.method, 'POST')
  assert.equal(calls[2].options.credentials, 'include')
  assert.deepEqual(JSON.parse(calls[2].options.body), { decision: 'approved', reason: null })
})


test('safety officer access and routes are registered', () => {
  const access = readFileSync(new URL('../../../frontend/src/lib/access.js', import.meta.url), 'utf8')
  const app = readFileSync(new URL('../../../frontend/src/App.jsx', import.meta.url), 'utf8')

  assert.match(access, /safety_officer/)
  assert.match(access, /VIEW_SAFETY_CHECKS/)
  assert.match(access, /DECIDE_SAFETY_CHECK/)
  assert.match(app, /SafetyOfficerDashboard/)
  assert.match(app, /SafetyCheckDetail/)
})


test('dashboard and detail expose all confirmed UI states and safety evidence', () => {
  const dashboard = readFileSync(
    new URL('../../../frontend/src/pages/SafetyOfficerDashboard.jsx', import.meta.url), 'utf8',
  )
  const detail = readFileSync(
    new URL('../../../frontend/src/pages/SafetyCheckDetail.jsx', import.meta.url), 'utf8',
  )

  for (const copy of ['Loading safety reviews', 'No events are awaiting an operational safety check', 'Try again']) {
    assert.match(dashboard, new RegExp(copy))
  }
  for (const contract of [
    'expected_attendance', 'confirmed_venues', 'capacity', 'layout', 'accessibility',
    'restrictions', 'technical_support', 'technical_support_notes',
    'equipment_requirements', 'special_requirements', 'Record safety decision',
    'Operational safety decision recorded',
  ]) {
    assert.match(detail, new RegExp(contract))
  }
})


test('error copy covers authorization, stale decisions and upstream failures', () => {
  assert.match(safetyCheckErrorMessage({ status: 401 }), /sign in again/i)
  assert.match(safetyCheckErrorMessage({ status: 403 }), /Safety Officers/i)
  assert.match(safetyCheckErrorMessage({ status: 404 }), /not found/i)
  assert.match(safetyCheckErrorMessage({ status: 409 }), /already/i)
  assert.match(safetyCheckErrorMessage({ status: 502 }), /temporarily unavailable/i)
})

