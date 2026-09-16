const API_BASE = import.meta.env?.VITE_API_URL ?? '/api'

export class ApiError extends Error {
  constructor(message, status, fieldErrors = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
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
    )
  }

  return data
}
