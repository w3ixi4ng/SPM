export const PERMISSIONS = Object.freeze({
  VIEW_DASHBOARD: 'dashboard:view',
  CREATE_EVENT: 'events:create',
  SAVE_EVENT_DRAFT: 'events:save_draft',
  VIEW_OWN_EVENTS: 'events:view_own',
  UPDATE_OWN_EVENT_DRAFT: 'events:update_own_draft',
  SUBMIT_OWN_EVENT: 'events:submit_own',
  CREATE_VENUE: 'venues:create',
  VIEW_VENUES: 'venues:view',
})

const DASHBOARD_PERMISSION = [PERMISSIONS.VIEW_DASHBOARD]

// This mirrors the backend policy for presentation only. Backend dependencies
// remain authoritative: events permissions come from the events service's
// authorization.py, venues permissions from the venues service's.
export const ROLE_ACCESS = Object.freeze({
  event_organiser: Object.freeze({
    label: 'Event Organiser',
    dashboardPath: '/dashboard/event-organiser',
    description: 'Create and manage your own event requests.',
    permissions: Object.freeze([
      ...DASHBOARD_PERMISSION,
      PERMISSIONS.CREATE_EVENT,
      PERMISSIONS.SAVE_EVENT_DRAFT,
      PERMISSIONS.VIEW_OWN_EVENTS,
      PERMISSIONS.UPDATE_OWN_EVENT_DRAFT,
      PERMISSIONS.SUBMIT_OWN_EVENT,
    ]),
  }),
  event_coordinator: Object.freeze({
    label: 'Event Coordinator',
    dashboardPath: '/dashboard/event-coordinator',
    description: 'Your coordinator workspace is ready for assigned workflows.',
    permissions: Object.freeze([...DASHBOARD_PERMISSION, PERMISSIONS.VIEW_VENUES]),
  }),
  venue_staff: Object.freeze({
    label: 'Venue Staff',
    dashboardPath: '/dashboard/venue-staff',
    description: 'Add the venues you manage so they can receive booking requests.',
    permissions: Object.freeze([
      ...DASHBOARD_PERMISSION,
      PERMISSIONS.CREATE_VENUE,
      PERMISSIONS.VIEW_VENUES,
    ]),
  }),
  technical_support: Object.freeze({
    label: 'Technical Support',
    dashboardPath: '/dashboard/technical-support',
    description: 'Your technical workspace is ready for assigned workflows.',
    permissions: Object.freeze([...DASHBOARD_PERMISSION]),
  }),
  attendee: Object.freeze({
    label: 'Attendee',
    dashboardPath: '/dashboard/attendee',
    description: 'Your attendee workspace is ready for assigned workflows.',
    permissions: Object.freeze([...DASHBOARD_PERMISSION]),
  }),
})

export function getRoleAccess(role) {
  return ROLE_ACCESS[role] ?? null
}

export function hasPermission(role, permission) {
  return getRoleAccess(role)?.permissions.includes(permission) ?? false
}
