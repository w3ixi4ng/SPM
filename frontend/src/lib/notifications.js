import { requestJSON } from './api.js'

export function listNotifications() {
  return requestJSON('/notifications')
}

export function notificationErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status >= 500) return 'Notifications are temporarily unavailable.'
  return error.message || "We couldn't load notifications."
}
