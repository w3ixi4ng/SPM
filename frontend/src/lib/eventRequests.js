const STORAGE_KEY = 'connectsphere.eventRequests'

function readAll() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function writeAll(records) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(records))
  } catch {
    // storage unavailable (private mode, quota) — the draft just won't survive a reload
  }
}

// Placeholder for the events service — swap the body for an HTTP call and
// keep this signature so callers don't change.
export function getEventRequest(id) {
  if (!id) return null
  return readAll()[id] ?? null
}

export function saveEventRequest(data, status) {
  const records = readAll()
  const id =
    data.id ||
    `evt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
  const record = { ...data, id, status, updatedAt: new Date().toISOString() }
  records[id] = record
  writeAll(records)
  return record
}
