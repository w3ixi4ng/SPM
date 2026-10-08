export const PERMISSIONS = Object.freeze({
  VIEW_DASHBOARD: 'dashboard:view',
  CREATE_EVENT: 'events:create',
  SAVE_EVENT_DRAFT: 'events:save_draft',
  VIEW_OWN_EVENTS: 'events:view_own',
  UPDATE_OWN_EVENT_DRAFT: 'events:update_own_draft',
  SUBMIT_OWN_EVENT: 'events:submit_own',
  CREATE_VENUE: 'venues:create',
  UPDATE_VENUE: 'venues:update',
  VIEW_VENUES: 'venues:view',
  VIEW_ASSIGNED_EVENTS: 'events:view_assigned',
  DECIDE_EVENT: 'events:decide',
  ASSIGN_TECHNICAL_SUPPORT: 'events:assign_technical_support',
  VIEW_UNASSIGNED_EVENTS: 'events:view_unassigned',
  ASSIGN_EVENT_COORDINATOR: 'events:assign_coordinator',
  REQUEST_VENUE_BOOKING: 'venue_bookings:create',
  VIEW_PENDING_VENUE_BOOKINGS: 'venue_bookings:view_pending',
  DECIDE_VENUE_BOOKING: 'venue_bookings:decide',
  MANAGE_VENUE_HOLDS: 'venue_bookings:manage_holds',
  VIEW_VENUE_AVAILABILITY: 'venue_bookings:view_availability',
  MANAGE_VENUE_BLOCKS: 'venue_bookings:manage_blocks',
  CREATE_EQUIPMENT: 'equipment:create',
  UPDATE_EQUIPMENT: 'equipment:update',
  RETIRE_EQUIPMENT: 'equipment:retire',
  VIEW_EQUIPMENT_CATALOGUE: 'equipment:view_catalogue',
  EDIT_EQUIPMENT_REQUIREMENTS: 'equipment_requirements:edit',
  VIEW_EQUIPMENT_REQUIREMENTS: 'equipment_requirements:view',
  CHECK_EQUIPMENT_AVAILABILITY: 'equipment:check_availability',
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
      PERMISSIONS.ASSIGN_TECHNICAL_SUPPORT,
      PERMISSIONS.VIEW_VENUES,
      PERMISSIONS.VIEW_VENUE_AVAILABILITY,
      PERMISSIONS.REQUEST_VENUE_BOOKING,
      PERMISSIONS.EDIT_EQUIPMENT_REQUIREMENTS,
      PERMISSIONS.VIEW_EQUIPMENT_REQUIREMENTS,
    ]),
  }),
  event_coordinator_lead: Object.freeze({
    label: 'Event Coordinator Lead',
    dashboardPath: '/dashboard/event-coordinator-lead',
    description: 'Review unassigned event requests and assign an Event Coordinator.',
    permissions: Object.freeze([
      ...DASHBOARD_PERMISSION,
      PERMISSIONS.VIEW_UNASSIGNED_EVENTS,
      PERMISSIONS.ASSIGN_EVENT_COORDINATOR,
    ]),
  }),
  venue_staff: Object.freeze({
    label: 'Venue Staff',
    dashboardPath: '/dashboard/venue-staff',
    description: 'Add the venues you manage so they can receive booking requests.',
    permissions: Object.freeze([
      ...DASHBOARD_PERMISSION,
      PERMISSIONS.CREATE_VENUE,
      PERMISSIONS.UPDATE_VENUE,
      PERMISSIONS.VIEW_VENUES,
      PERMISSIONS.VIEW_PENDING_VENUE_BOOKINGS,
      PERMISSIONS.DECIDE_VENUE_BOOKING,
      PERMISSIONS.MANAGE_VENUE_HOLDS,
      PERMISSIONS.VIEW_VENUE_AVAILABILITY,
      PERMISSIONS.MANAGE_VENUE_BLOCKS,
    ]),
  }),
  technical_support: Object.freeze({
    label: 'Technical Support',
    dashboardPath: '/dashboard/technical-support',
    description: 'Your technical workspace is ready for assigned workflows.',
    permissions: Object.freeze([
      ...DASHBOARD_PERMISSION,
      PERMISSIONS.CREATE_EQUIPMENT,
      PERMISSIONS.UPDATE_EQUIPMENT,
      PERMISSIONS.RETIRE_EQUIPMENT,
      PERMISSIONS.VIEW_EQUIPMENT_CATALOGUE,
      PERMISSIONS.VIEW_EQUIPMENT_REQUIREMENTS,
      PERMISSIONS.CHECK_EQUIPMENT_AVAILABILITY,
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
