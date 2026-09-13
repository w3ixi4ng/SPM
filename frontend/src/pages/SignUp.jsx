import { useRef, useState } from 'react'
import { CircleAlert, Loader2 } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
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
const NAME_MAX = 100
const PASSWORD_MIN = 8
const PASSWORD_MAX = 72

const FRIENDLY_FIELD_ERRORS = {
  name: `Please enter a name (up to ${NAME_MAX} characters).`,
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

function validate({ name, email, password }) {
  const errors = {}

  const trimmedName = name.trim()
  if (!trimmedName) errors.name = 'Please enter your name.'
  else if (trimmedName.length > NAME_MAX) errors.name = `Name must be ${NAME_MAX} characters or fewer.`

  const trimmedEmail = email.trim()
  if (!trimmedEmail) errors.email = 'Please enter your email address.'
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
    errors.email = 'Please enter a valid email address.'
  }

  if (!password) errors.password = 'Please create a password.'
  else if (password.length < PASSWORD_MIN) errors.password = `Password must be at least ${PASSWORD_MIN} characters.`
  else if (password.length > PASSWORD_MAX) errors.password = `Password must be ${PASSWORD_MAX} characters or fewer.`

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

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [status, setStatus] = useState('idle')

  const nameRef = useRef(null)
  const emailRef = useRef(null)
  const passwordRef = useRef(null)
  const fieldRefs = { name: nameRef, email: emailRef, password: passwordRef }

  const isSubmitting = status === 'loading' || status === 'success'

  function clearFieldError(field) {
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: undefined }))
    if (formError) setFormError(null)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (isSubmitting) return

    const validationErrors = validate({ name, email, password })
    setErrors(validationErrors)
    setFormError(null)

    const firstInvalid = Object.keys(validationErrors)[0]
    if (firstInvalid) {
      fieldRefs[firstInvalid]?.current?.focus()
      return
    }

    setStatus('loading')
    try {
      await signUp({ name: name.trim(), email: email.trim(), password })
      setStatus('success')
      setTimeout(() => navigate('/dashboard'), 700)
    } catch (err) {
      setStatus('idle')
      if (err.status === 409) {
        setFormError('This email is already registered. Log in instead, or use a different email.')
      } else if (err.status === 422 && err.fieldErrors) {
        const mapped = {}
        for (const field of Object.keys(err.fieldErrors)) {
          mapped[field] = FRIENDLY_FIELD_ERRORS[field] || err.fieldErrors[field]
        }
        setErrors(mapped)
      } else if (err.status === 429) {
        setFormError("You've tried too many times. Wait a moment and try again.")
      } else {
        setFormError(err.message || 'Something went wrong. Please try again.')
      }
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center px-6 py-16"
      style={{ backgroundColor: C.paper }}
    >
      <style>{`
        @keyframes riseIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: none; }
        }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }

        .csp-input {
          border: 1px solid ${C.line};
          background: ${C.paper};
          color: ${C.ink};
          transition: border-color 0.2s, box-shadow 0.2s;
        }
        .csp-input::placeholder { color: ${C.inkFaint}; opacity: 0.65; }
        .csp-input:focus-visible {
          outline: none;
          border-color: ${C.teal};
          box-shadow: 0 0 0 3px ${withAlpha(C.teal, 0.15)};
        }
        .csp-input[aria-invalid="true"] { border-color: ${C.rose}; }
        .csp-input[aria-invalid="true"]:focus-visible {
          box-shadow: 0 0 0 3px ${withAlpha(C.rose, 0.15)};
        }
        .csp-input:disabled { opacity: 0.65; cursor: not-allowed; }

        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none !important; }
        }
      `}</style>

      <div
        className="rise-in w-full max-w-sm border rounded-sm px-8 py-10"
        style={{ borderColor: C.line }}
      >
        <h1 className="font-display text-3xl mb-2" style={{ color: C.ink }}>
          Sign Up
        </h1>
        <p className="font-ui text-sm leading-relaxed mb-8" style={{ color: C.inkFaint }}>
          Create your ConnectSphere account to start planning and managing
          events.
        </p>

        {formError && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-sm px-4 py-3 mb-5 font-ui text-sm"
            style={{ backgroundColor: withAlpha(C.rose, 0.1), color: C.rose }}
          >
            <CircleAlert size={18} className="shrink-0 mt-0.5" aria-hidden="true" />
            <span>{formError}</span>
          </div>
        )}

        <form noValidate onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="signup-name" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
              Name
            </label>
            <input
              ref={nameRef}
              id="signup-name"
              name="name"
              type="text"
              autoComplete="name"
              maxLength={NAME_MAX}
              placeholder="Ada Lovelace"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                clearFieldError('name')
              }}
              disabled={isSubmitting}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? 'signup-name-error' : undefined}
              className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
            />
            <FieldError id="signup-name-error" message={errors.name} />
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

          <div>
            <label htmlFor="signup-password" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
              Password
            </label>
            <input
              ref={passwordRef}
              id="signup-password"
              name="password"
              type="password"
              autoComplete="new-password"
              maxLength={PASSWORD_MAX}
              placeholder={`${PASSWORD_MIN}-${PASSWORD_MAX} characters`}
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

          <button
            type="submit"
            disabled={isSubmitting}
            className={`w-full flex items-center justify-center gap-2 px-5 py-3 rounded-sm font-medium font-ui transition-transform duration-200 disabled:opacity-70 ${
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
        </form>

        <div className="mt-6">
          <Link
            to="/login"
            className="inline-block w-full text-center px-5 py-3 rounded-sm font-medium font-ui border transition-colors duration-200"
            style={{ borderColor: C.ink, color: C.ink }}
          >
            Back to log in
          </Link>
        </div>
      </div>
    </div>
  )
}
