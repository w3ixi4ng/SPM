import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getRoleAccess,
  hasPermission,
  PERMISSIONS,
  ROLE_ACCESS,
} from '../../../frontend/src/lib/access.js'

const EXPECTED_DASHBOARDS = {
  event_organiser: '/dashboard/event-organiser',
  event_coordinator: '/dashboard/event-coordinator',
  venue_staff: '/dashboard/venue-staff',
  technical_support: '/dashboard/technical-support',
  attendee: '/dashboard/attendee',
}

test('every supported role has its own dashboard', () => {
  assert.deepEqual(
    Object.fromEntries(
      Object.entries(ROLE_ACCESS).map(([role, access]) => [role, access.dashboardPath]),
    ),
    EXPECTED_DASHBOARDS,
  )
})

test('only event organisers receive organiser-only event permissions', () => {
  const organiserEventPermissions = ROLE_ACCESS.event_organiser.permissions.filter(
    (permission) => permission.startsWith('events:'),
  )

  for (const permission of organiserEventPermissions) {
    assert.equal(hasPermission('event_organiser', permission), true)
    for (const role of Object.keys(ROLE_ACCESS).filter((name) => name !== 'event_organiser')) {
      assert.equal(hasPermission(role, permission), false)
    }
  }
})

test('only event coordinators receive coordinator-only event permissions', () => {
  const coordinatorEventPermissions = ROLE_ACCESS.event_coordinator.permissions.filter(
    (permission) => permission.startsWith('events:'),
  )

  for (const permission of coordinatorEventPermissions) {
    assert.equal(hasPermission('event_coordinator', permission), true)
    for (const role of Object.keys(ROLE_ACCESS).filter((name) => name !== 'event_coordinator')) {
      assert.equal(hasPermission(role, permission), false)
    }
  }
})

test('missing and unknown roles fail closed', () => {
  assert.equal(getRoleAccess(), null)
  assert.equal(getRoleAccess('not_a_role'), null)
  assert.equal(hasPermission(undefined, PERMISSIONS.VIEW_DASHBOARD), false)
  assert.equal(hasPermission('not_a_role', PERMISSIONS.CREATE_EVENT), false)
})
