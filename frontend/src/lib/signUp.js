// Sign-up form rules. Mirrors backend/services/atomic/users/schemas.py::SignUpRequest
// exactly, so a bad value is caught here instead of round-tripping to the
// server first. First/last name are a frontend-only split -- the backend takes
// one `name`.
export const NAME_MAX = 100
export const PASSWORD_MIN = 8
export const PASSWORD_MAX = 72

// S-01: the only roles anyone may give themselves. Every other role is
// assigned by an administrator, and the users service rejects it with a 422.
export const SIGN_UP_ROLES = Object.freeze([
  Object.freeze({ value: 'attendee', label: 'Attendee', description: 'Find events and register for them.' }),
  Object.freeze({ value: 'event_organiser', label: 'Event Organiser', description: 'Request and run your own events.' }),
])

export const ROLE_REQUIRED = "Choose whether you're signing up as an Attendee or an Event Organiser."

// Keys come out in form order, so the first one is the field to focus.
export function validateSignUp({ role, firstName, lastName, email, password, confirmPassword }) {
  const errors = {}

  if (!SIGN_UP_ROLES.some((option) => option.value === role)) errors.role = ROLE_REQUIRED

  const trimmedFirst = firstName.trim()
  if (!trimmedFirst) errors.firstName = 'Please enter your first name.'

  const trimmedLast = lastName.trim()
  if (!trimmedLast) errors.lastName = 'Please enter your last name.'

  if (trimmedFirst && trimmedLast && `${trimmedFirst} ${trimmedLast}`.length > NAME_MAX) {
    errors.lastName = `Your full name must be ${NAME_MAX} characters or fewer.`
  }

  const trimmedEmail = email.trim()
  if (!trimmedEmail) errors.email = 'Please enter your email address.'
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
    errors.email = 'Please enter a valid email address.'
  }

  if (!password) errors.password = 'Please create a password.'
  else if (password.length < PASSWORD_MIN) errors.password = `Password must be at least ${PASSWORD_MIN} characters.`
  else if (password.length > PASSWORD_MAX) errors.password = `Password must be ${PASSWORD_MAX} characters or fewer.`

  if (!confirmPassword) errors.confirmPassword = 'Please confirm your password.'
  else if (confirmPassword !== password) errors.confirmPassword = 'Passwords do not match.'

  return errors
}
