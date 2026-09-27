export const PERMISSIONS = Object.freeze({
  VIEW_DASHBOARD: 'dashboard:view',
  CREATE_EVENT: 'events:create',
  SAVE_EVENT_DRAFT: 'events:save_draft',
  VIEW_OWN_EVENTS: 'events:view_own',
  UPDATE_OWN_EVENT_DRAFT: 'events:update_own_draft',
  SUBMIT_OWN_EVENT: 'events:submit_own',
  CREATE_VENUE: 'venues:create',
  VIEW_VENUES: 'venues:view',
  VIEW_ASSIGNED_EVENTS: 'events:view_assigned',
  DECIDE_EVENT: 'events:decide',
  REQUEST_VENUE_BOOKING: 'venue_bookings:create',
  VIEW_PENDING_VENUE_BOOKINGS: 'venue_bookings:view_pending',
  CREATE_EQUIPMENT: 'equipment:create',
  VIEW_EQUIPMENT_CATALOGUE: 'equipment:view_catalogue',
})

const DASHBOARD_PERMISSION = [PERMISSIONS.VIEW_DASHBOARD]

// This mirrors the backend policy for presentation only. Backend dependencies
// remain authoritative: events permissions come from the events service's
// authorization.py, venues permissions from the venues service's, venue
// booking permissions from the venue_bookings composite's role checks. Event
// Coordinator can view and decide on its assigned requests; the remaining
// non-organiser workflows are not yet defined by the project requirements,
// so those roles receive a dashboard and no controls.
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
    description: 'Review the event requests routed to you.',
    permissions: Object.freeze([
      ...DASHBOARD_PERMISSION,
      PERMISSIONS.VIEW_ASSIGNED_EVENTS,
      PERMISSIONS.DECIDE_EVENT,
      PERMISSIONS.VIEW_VENUES,
      PERMISSIONS.REQUEST_VENUE_BOOKING,
    ]),
  }),
  venue_staff: Object.freeze({
    label: 'Venue Staff',
    dashboardPath: '/dashboard/venue-staff',
    description: 'Add the venues you manage so they can receive booking requests.',
    permissions: Object.freeze([
      ...DASHBOARD_PERMISSION,
      PERMISSIONS.CREATE_VENUE,
      PERMISSIONS.VIEW_VENUES,
      PERMISSIONS.VIEW_PENDING_VENUE_BOOKINGS,
    ]),
  }),
  technical_support: Object.freeze({
    label: 'Technical Support',
    dashboardPath: '/dashboard/technical-support',
    description: 'Your technical workspace is ready for assigned workflows.',
    permissions: Object.freeze([
      ...DASHBOARD_PERMISSION,
      PERMISSIONS.CREATE_EQUIPMENT,
      PERMISSIONS.VIEW_EQUIPMENT_CATALOGUE,
    ]),
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
