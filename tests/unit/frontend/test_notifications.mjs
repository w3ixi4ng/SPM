import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  listNotifications,
  notificationErrorMessage,
  notificationLink,
} from '../../../frontend/src/lib/notifications.js'

// --- TC-FRONTEND-094 -----------------------------------------------------
test('notifications load through Kong using the authenticated session', async () => {
  const originalFetch = globalThis.fetch
  let recorded
  const expected = [{ id: 1, message: 'You have been assigned.' }]
  globalThis.fetch = async (url, options = {}) => {
    recorded = { url, options }
    return new Response(JSON.stringify(expected), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  try {
    assert.deepEqual(await listNotifications(), expected)
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(recorded.url, '/api/notifications')
  assert.equal(recorded.options.method, undefined)
  assert.equal(recorded.options.credentials, 'include')
})

test('notification failures map to safe messages', () => {
  assert.match(notificationErrorMessage({ status: 401 }), /sign in again/i)
  assert.match(notificationErrorMessage({ status: 500 }), /temporarily unavailable/i)
  assert.equal(
    notificationErrorMessage({ status: 400, message: 'Bad notification request' }),
    'Bad notification request',
  )
})

// --- TC-FRONTEND-095 -----------------------------------------------------
test('organiser and coordinator dashboards render the persistent inbox states', () => {
  const panel = readFileSync(
    new URL('../../../frontend/src/components/NotificationPanel.jsx', import.meta.url),
    'utf8',
  )
  const organiser = readFileSync(
    new URL('../../../frontend/src/pages/Dashboard.jsx', import.meta.url),
    'utf8',
  )
  const coordinator = readFileSync(
    new URL('../../../frontend/src/pages/EventCoordinatorDashboard.jsx', import.meta.url),
    'utf8',
  )

  assert.match(organiser, /<NotificationPanel \/>/)
  assert.match(coordinator, /<NotificationPanel \/>/)
  assert.match(panel, /listNotifications\(\)/)
  assert.match(panel, /row\.message/)
  assert.match(panel, /row\.created_at/)
  assert.match(panel, /No notifications yet\./)
  assert.match(panel, /role="alert"/)
  assert.doesNotMatch(panel, /email|sms|push/i)
})

// --- TC-FRONTEND-279 -----------------------------------------------------
test('the invitation links to its event', () => {
  const event = '11111111-1111-4111-8111-111111111111'
  assert.deepEqual(notificationLink({ kind: 'waiting_list_offer', event_id: event }), {
    href: `/public/events/${event}`, label: 'View event',
  })
  assert.equal(notificationLink({ kind: 'registration_confirmation', event_id: event }), null)
  assert.equal(notificationLink({ kind: 'event_assignment', event_id: event }), null)
})
