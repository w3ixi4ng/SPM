import { requestJSON } from './api.js'

export function listNotifications() {
  return requestJSON('/notifications')
}

export function notificationErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status >= 500) return 'Notifications are temporarily unavailable.'
  return error.message || "We couldn't load notifications."
}

// S-55: an invitation to take a held place links to the event page, where it
// is accepted. Every other notification is read in place.
export function notificationLink(row) {
  if (row?.kind !== 'waiting_list_offer' || !row.event_id) return null
  return { href: `/public/events/${row.event_id}`, label: 'View event' }
}
