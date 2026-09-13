import { useRef, useState } from 'react'
import { CalendarCheck2, CircleAlert, Loader2 } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import { signUp } from '../lib/auth.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
  rose: '#B25547',
}

// Mirrors backend/services/atomic/users/schemas.py::SignUpRequest exactly, so
// a bad value is caught here instead of round-tripping to the server first.
// First/last name are a frontend-only split -- the backend takes one `name`.
const NAME_MAX = 100
const PASSWORD_MIN = 8
const PASSWORD_MAX = 72

const FRIENDLY_FIELD_ERRORS = {
  name: `Please check your name (up to ${NAME_MAX} characters).`,
  email: 'Please enter a valid email address.',
  password: `Password must be ${PASSWORD_MIN}-${PASSWORD_MAX} characters.`,
}

function withAlpha(hex, alpha) {
  const n = Number.parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function validate({ firstName, lastName, email, password, confirmPassword }) {
  const errors = {}

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

function FieldError({ id, message }) {
  return (
    <div className="min-h-5 mt-1">
      {message && (
        <p id={id} role="alert" className="font-ui text-xs" style={{ color: C.rose }}>
          {message}
        </p>
      )}
    </div>
  )
}

export default function SignUp() {
  const navigate = useNavigate()

  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [status, setStatus] = useState('idle')

  const firstNameRef = useRef(null)
  const lastNameRef = useRef(null)
  const emailRef = useRef(null)
  const passwordRef = useRef(null)
  const confirmPasswordRef = useRef(null)
  const fieldRefs = {
    firstName: firstNameRef,
    lastName: lastNameRef,
    email: emailRef,
    password: passwordRef,
    confirmPassword: confirmPasswordRef,
  }

  const isSubmitting = status === 'loading' || status === 'success'

  function clearFieldError(field) {
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: undefined }))
    if (formError) setFormError(null)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (isSubmitting) return

    const validationErrors = validate({ firstName, lastName, email, password, confirmPassword })
    setErrors(validationErrors)
    setFormError(null)

    const firstInvalid = Object.keys(validationErrors)[0]
    if (firstInvalid) {
      fieldRefs[firstInvalid]?.current?.focus()
      return
    }

    const name = `${firstName.trim()} ${lastName.trim()}`.trim()

    setStatus('loading')
    try {
      await signUp({ name, email: email.trim(), password })
      setStatus('success')
      setTimeout(() => navigate('/dashboard'), 700)
    } catch (err) {
      setStatus('idle')
      if (err.status === 409) {
        setFormError('This email is already registered. Log in instead, or use a different email.')
      } else if (err.status === 422 && err.fieldErrors) {
        const mapped = {}
        let nameIssue = null
        for (const field of Object.keys(err.fieldErrors)) {
          if (field === 'name') nameIssue = FRIENDLY_FIELD_ERRORS.name
          else mapped[field] = FRIENDLY_FIELD_ERRORS[field] || err.fieldErrors[field]
        }
        setErrors(mapped)
        if (nameIssue) setFormError(nameIssue)
      } else if (err.status === 429) {
        setFormError("You've tried too many times. Wait a moment and try again.")
      } else {
        setFormError(err.message || 'Something went wrong. Please try again.')
      }
    }
  }

  return (
    <div className="min-h-screen flex" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
        }
      `}</style>

      <div className="flex-1 flex items-center justify-center px-6 py-12 sm:py-16">
        <div className="rise-in w-full max-w-md flex flex-col gap-8">
          <div>
            <Logo className="mb-8" />
            <h1 className="font-display text-3xl mb-2" style={{ color: C.ink }}>
              Create your account
            </h1>
            <p className="font-ui text-sm leading-relaxed" style={{ color: C.inkFaint }}>
              to start planning with ConnectSphere
            </p>
          </div>

          {formError && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-sm px-4 py-3 font-ui text-sm"
              style={{ backgroundColor: withAlpha(C.rose, 0.1), color: C.rose }}
            >
              <CircleAlert size={18} className="shrink-0 mt-0.5" aria-hidden="true" />
              <span>{formError}</span>
            </div>
          )}

          <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="signup-first-name" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                  First name
                </label>
                <input
                  ref={firstNameRef}
                  id="signup-first-name"
                  name="firstName"
                  type="text"
                  autoComplete="given-name"
                  maxLength={NAME_MAX}
                  placeholder="Ada"
                  value={firstName}
                  onChange={(e) => {
                    setFirstName(e.target.value)
                    clearFieldError('firstName')
                  }}
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.firstName)}
                  aria-describedby={errors.firstName ? 'signup-first-name-error' : undefined}
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                />
                <FieldError id="signup-first-name-error" message={errors.firstName} />
              </div>

              <div>
                <label htmlFor="signup-last-name" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                  Last name
                </label>
                <input
                  ref={lastNameRef}
                  id="signup-last-name"
                  name="lastName"
                  type="text"
                  autoComplete="family-name"
                  maxLength={NAME_MAX}
                  placeholder="Lovelace"
                  value={lastName}
                  onChange={(e) => {
                    setLastName(e.target.value)
                    clearFieldError('lastName')
                  }}
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.lastName)}
                  aria-describedby={errors.lastName ? 'signup-last-name-error' : undefined}
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                />
                <FieldError id="signup-last-name-error" message={errors.lastName} />
              </div>
            </div>

            <div>
              <label htmlFor="signup-email" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                Email
              </label>
              <input
                ref={emailRef}
                id="signup-email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="ada@example.com"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  clearFieldError('email')
                }}
                disabled={isSubmitting}
                aria-invalid={Boolean(errors.email)}
                aria-describedby={errors.email ? 'signup-email-error' : undefined}
                className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
              />
              <FieldError id="signup-email-error" message={errors.email} />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="signup-password" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                  Password
                </label>
                <input
                  ref={passwordRef}
                  id="signup-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  maxLength={PASSWORD_MAX}
                  placeholder={`${PASSWORD_MIN}+ characters`}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    clearFieldError('password')
                  }}
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={errors.password ? 'signup-password-error' : undefined}
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                />
                <FieldError id="signup-password-error" message={errors.password} />
              </div>

              <div>
                <label htmlFor="signup-confirm-password" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                  Confirm Password
                </label>
                <input
                  ref={confirmPasswordRef}
                  id="signup-confirm-password"
                  name="confirmPassword"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  maxLength={PASSWORD_MAX}
                  placeholder="Re-enter password"
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value)
                    clearFieldError('confirmPassword')
                  }}
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.confirmPassword)}
                  aria-describedby={errors.confirmPassword ? 'signup-confirm-password-error' : undefined}
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                />
                <FieldError id="signup-confirm-password-error" message={errors.confirmPassword} />
              </div>
            </div>

            <label className="flex items-center gap-2 font-ui text-sm select-none -mt-2" style={{ color: C.ink }}>
              <input
                type="checkbox"
                checked={showPassword}
                onChange={() => setShowPassword((v) => !v)}
                disabled={isSubmitting}
                className="w-4 h-4 rounded-sm"
                style={{ accentColor: C.teal }}
              />
              Show password
            </label>

            <div className="flex items-center justify-between pt-2">
              <Link
                to="/login"
                className="font-ui text-sm font-medium transition-colors duration-200 hover:underline"
                style={{ color: C.teal }}
              >
                Log in instead
              </Link>
              <button
                type="submit"
                disabled={isSubmitting}
                className={`flex items-center justify-center gap-2 px-6 py-3 rounded-sm font-medium font-ui transition-transform duration-200 disabled:opacity-70 ${
                  isSubmitting ? '' : 'hover:-translate-y-0.5'
                }`}
                style={{ backgroundColor: C.teal, color: C.paper }}
              >
                {status === 'loading' && (
                  <>
                    <Loader2 size={18} className="animate-spin" aria-hidden="true" />
                    Creating account...
                  </>
                )}
                {status === 'success' && 'Account created'}
                {status === 'idle' && 'Sign Up'}
              </button>
            </div>
          </form>
        </div>
      </div>

      <div
        className="hidden md:flex md:w-2/5 items-center px-12 border-l"
        style={{ borderColor: C.line }}
      >
        <div className="max-w-xs">
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center mb-6"
            style={{ backgroundColor: withAlpha(C.teal, 0.1) }}
          >
            <CalendarCheck2 size={26} aria-hidden="true" style={{ color: C.teal }} />
          </div>
          <p className="font-display text-2xl leading-snug" style={{ color: C.ink }}>
            One account. Every event, organised.
          </p>
        </div>
      </div>
    </div>
  )
}
