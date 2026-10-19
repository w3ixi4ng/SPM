const API_BASE = import.meta.env?.VITE_API_URL ?? '/api'

export class ApiError extends Error {
  constructor(message, status, fieldErrors = null, body = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
    // The whole error body, for the few responses that carry more than a
    // detail -- S-17's outstanding arrangements and equipment shortages.
    this.body = body
  }
}

export async function requestJSON(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      credentials: 'include',
    })
  } catch {
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }

  const data = response.status === 204
    ? null
    : await response.json().catch(() => null)

  if (!response.ok) {
    throw new ApiError(
      data?.detail || 'Something went wrong. Please try again.',
      response.status,
      data?.errors ?? null,
      data,
    )
  }

  return data
}
