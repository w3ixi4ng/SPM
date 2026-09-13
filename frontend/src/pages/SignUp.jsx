import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
  rose: '#B25547',
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
  if (!name.trim()) errors.name = 'Please enter your name.'
  if (!email.trim()) errors.email = 'Please enter your email address.'
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
    errors.email = 'Please enter a valid email address.'
  }
  if (!password) errors.password = 'Please create a password.'
  else if (password.length < 8) errors.password = 'Password must be at least 8 characters.'
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
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState({})

  const nameRef = useRef(null)
  const emailRef = useRef(null)
  const passwordRef = useRef(null)
  const fieldRefs = { name: nameRef, email: emailRef, password: passwordRef }

  function clearFieldError(field) {
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: undefined }))
  }

  function handleSubmit(e) {
    e.preventDefault()

    const validationErrors = validate({ name, email, password })
    setErrors(validationErrors)

    const firstInvalid = Object.keys(validationErrors)[0]
    if (firstInvalid) {
      fieldRefs[firstInvalid]?.current?.focus()
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
              placeholder="Ada Lovelace"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                clearFieldError('name')
              }}
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
              placeholder="At least 8 characters"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value)
                clearFieldError('password')
              }}
              aria-invalid={Boolean(errors.password)}
              aria-describedby={errors.password ? 'signup-password-error' : undefined}
              className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
            />
            <FieldError id="signup-password-error" message={errors.password} />
          </div>

          <button
            type="submit"
            className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-sm font-medium font-ui transition-transform duration-200 hover:-translate-y-0.5"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            Sign Up
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
