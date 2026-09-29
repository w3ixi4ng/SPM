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

// --- TC-FRONTEND-009 -------------------------------------------------------
test('only venue staff create venues and only venue staff and coordinators view them', () => {
  const expected = {
    venue_staff: [true, true],
    event_coordinator: [false, true],
    event_organiser: [false, false],
    technical_support: [false, false],
    attendee: [false, false],
  }

  assert.deepEqual(Object.keys(expected).sort(), Object.keys(ROLE_ACCESS).sort())
  for (const [role, [create, view]] of Object.entries(expected)) {
    assert.equal(hasPermission(role, PERMISSIONS.CREATE_VENUE), create, role)
    assert.equal(hasPermission(role, PERMISSIONS.VIEW_VENUES), view, role)
  }
})

// --- TC-FRONTEND-028 -------------------------------------------------------
test('only coordinators request venues and only venue staff see pending requests', () => {
  const expected = {
    event_coordinator: [true, false],
    venue_staff: [false, true],
    event_organiser: [false, false],
    technical_support: [false, false],
    attendee: [false, false],
  }

  assert.deepEqual(Object.keys(expected).sort(), Object.keys(ROLE_ACCESS).sort())
  for (const [role, [request, viewPending]] of Object.entries(expected)) {
    assert.equal(hasPermission(role, PERMISSIONS.REQUEST_VENUE_BOOKING), request, role)
    assert.equal(hasPermission(role, PERMISSIONS.VIEW_PENDING_VENUE_BOOKINGS), viewPending, role)
  }
})

// --- TC-FRONTEND-042 -------------------------------------------------------
test('coordinators edit requirements and technical support can only view them', () => {
  const expected = {
    event_coordinator: [true, true],
    technical_support: [false, true],
    event_organiser: [false, false],
    venue_staff: [false, false],
    attendee: [false, false],
  }

  for (const [role, [edit, view]] of Object.entries(expected)) {
    assert.equal(hasPermission(role, PERMISSIONS.EDIT_EQUIPMENT_REQUIREMENTS), edit, role)
    assert.equal(hasPermission(role, PERMISSIONS.VIEW_EQUIPMENT_REQUIREMENTS), view, role)
  }
})

// --- TC-FRONTEND-045 -------------------------------------------------------
test('only technical support receives the equipment update permission', () => {
  for (const role of Object.keys(ROLE_ACCESS)) {
    assert.equal(
      hasPermission(role, PERMISSIONS.UPDATE_EQUIPMENT),
      role === 'technical_support',
      role,
    )
  }
})

// --- TC-FRONTEND-049 -------------------------------------------------------
test('only technical support can retire equipment', () => {
  for (const role of Object.keys(ROLE_ACCESS)) {
    assert.equal(
      hasPermission(role, PERMISSIONS.RETIRE_EQUIPMENT),
      role === 'technical_support',
      role,
    )
  }
})

// --- TC-FRONTEND-052 -----------------------------------------------------
test('only coordinators can request technical support assignment', () => {
  for (const role of Object.keys(ROLE_ACCESS)) {
    assert.equal(
      hasPermission(role, PERMISSIONS.ASSIGN_TECHNICAL_SUPPORT),
      role === 'event_coordinator',
      role,
    )
  }
})
