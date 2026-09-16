import { useEffect, useId, useRef, useState } from 'react'
import { Check, CircleAlert, Eye, EyeOff, Loader2 } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import { login } from '../lib/auth.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  teal: '#0E7C74',
  tealBright: '#149E92',
  rose: '#B25547',
  green: '#3F8F5F',
}

const STAT_TARGET = 12400

function withAlpha(hex, alpha) {
  const n = Number.parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function BrandPanel() {
  const [count, setCount] = useState(0)

  useEffect(() => {
    const reduceMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches
    if (reduceMotion) {
      setCount(STAT_TARGET)
      return
    }

    const duration = 1100
    const start = performance.now()
    let raf

    function tick(now) {
      const progress = Math.min((now - start) / duration, 1)
      const eased = 1 - (1 - progress) ** 3
      setCount(Math.round(eased * STAT_TARGET))
      if (progress < 1) raf = requestAnimationFrame(tick)
    }

    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <div
      className="hidden md:flex md:w-2/5 flex-col justify-between p-10 lg:p-14"
      style={{ backgroundColor: C.ink }}
    >
      <div className="rise-in">
        <Logo onDark />
        <p
          className="font-display text-3xl leading-snug mt-10 mb-4"
          style={{ color: C.paper }}
        >
          Plan events people actually show up for.
        </p>
        <p
          className="font-ui text-sm leading-relaxed max-w-sm"
          style={{ color: 'rgba(248,246,241,0.7)' }}
        >
          Venues, vendors, guests, and schedules — one workspace for the
          whole team.
        </p>
      </div>
      <div className="rise-in" style={{ animationDelay: '140ms' }}>
        <p className="font-display text-4xl" style={{ color: C.paper }}>
          {count.toLocaleString()}
          <span style={{ color: C.tealBright }}>+</span>
        </p>
        <p
          className="font-ui text-xs mt-1"
          style={{ color: 'rgba(248,246,241,0.6)' }}
        >
          events planned on ConnectSphere
        </p>
      </div>
    </div>
  )
}

export default function Login() {
  const navigate = useNavigate()
  const { refresh } = useAuth()
  const emailId = useId()
  const passwordId = useId()
  const emailErrorId = useId()
  const passwordErrorId = useId()

  const emailRef = useRef(null)
  const passwordRef = useRef(null)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState({})
  const [authError, setAuthError] = useState(null)
  const [status, setStatus] = useState('idle')

  const isSubmitting = status === 'loading' || status === 'success'

  function handleEmailChange(e) {
    setEmail(e.target.value)
    if (errors.email) {
      setErrors((prev) => ({ ...prev, email: undefined }))
    }
    if (authError) setAuthError(null)
  }

  function handlePasswordChange(e) {
    setPassword(e.target.value)
    if (errors.password) {
      setErrors((prev) => ({ ...prev, password: undefined }))
    }
    if (authError) setAuthError(null)
  }

  function validate() {
    const next = {}
    if (!email.trim()) next.email = 'Please enter your email.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      next.email = 'Please enter a valid email address.'
    }
    if (!password) next.password = 'Please enter your password.'
    return next
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (isSubmitting) return

    const next = validate()
    setErrors(next)
    setAuthError(null)

    if (next.email) {
      emailRef.current?.focus()
      return
    }
    if (next.password) {
      passwordRef.current?.focus()
      return
    }

    setStatus('loading')
    login({ email: email.trim(), password })
      .then(() => refresh())
      .then(() => {
        setStatus('success')
        setTimeout(() => navigate('/dashboard'), 700)
      })
      .catch((err) => {
        setStatus('idle')
        if (err.status === 401) {
          setAuthError('Incorrect email or password. Please try again.')
        } else if (err.status === 429) {
          setAuthError("You've tried too many times. Wait a moment and try again.")
        } else {
          setAuthError(err.message || 'Something went wrong. Please try again.')
        }
      })
  }

  return (
    <div
      className="min-h-screen flex flex-col md:flex-row"
      style={{ backgroundColor: C.paperDim }}
    >
      <style>{`
        @keyframes riseIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: none; }
        }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }

        @keyframes fieldErrorIn {
          from { opacity: 0; transform: translateY(-2px); }
          to { opacity: 1; transform: none; }
        }
        .csp-error { animation: fieldErrorIn 0.18s ease-out both; }

        .csp-input {
          border: 1px solid ${C.line};
          background: #FFFFFF;
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

        .csp-toggle:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }

        .csp-btn-primary { transition: transform 0.2s, background-color 0.2s; }
        .csp-btn-primary:disabled { cursor: not-allowed; }

        @media (prefers-reduced-motion: reduce) {
          .rise-in, .csp-error {
            animation: none !important;
          }
          .csp-btn-primary {
            transition: background-color 0.2s !important;
          }
        }
      `}</style>

      <div
        className="flex md:hidden items-center px-6 py-5 border-b"
        style={{ borderColor: C.line }}
      >
        <Logo />
      </div>

      <BrandPanel />

      <div className="flex-1 flex items-center justify-center px-6 py-10 md:py-16">
        <div
          className="rise-in w-full max-w-md"
          style={{ animationDelay: '130ms' }}
        >
          <div className="rounded-sm px-6 py-8 sm:px-10 sm:py-10">
            <h1
              className="font-display text-3xl mb-2"
              style={{ color: C.ink }}
            >
              Welcome back
            </h1>
            <p
              className="font-ui text-sm leading-relaxed mb-6 max-w-sm"
              style={{ color: C.inkFaint }}
            >
              Log in to continue managing your events with ConnectSphere.
            </p>

            {authError && (
              <div
                role="alert"
                className="csp-error flex items-start gap-2 rounded-sm px-4 py-3 mb-5 font-ui text-sm"
                style={{ backgroundColor: withAlpha(C.rose, 0.1), color: C.rose }}
              >
                <CircleAlert
                  size={18}
                  className="shrink-0 mt-0.5"
                  aria-hidden="true"
                />
                <span>{authError}</span>
              </div>
            )}

            <form noValidate onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label
                  htmlFor={emailId}
                  className="block font-ui text-sm font-medium mb-1.5"
                  htmlFor={emailId}
                  className="block font-display text-sm font-medium mb-1.5"
                  style={{ color: C.ink }}
                >
                  Email
                </label>
                <input
                  ref={emailRef}
                  id={emailId}
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={handleEmailChange}
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={
                    errors.email ? emailErrorId : undefined
                  }
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm disabled:opacity-60"
                />
                <div className="min-h-5 mt-1">
                  {errors.email && (
                    <p
                      id={emailErrorId}
                      role="alert"
                      className="csp-error font-ui text-xs"
                      style={{ color: C.rose }}
                    >
                      {errors.email}
                    </p>
                  )}
                </div>
              </div>

              <div>
                <label
                  htmlFor={passwordId}
                  className="block font-display text-sm font-medium mb-1.5"
                  style={{ color: C.ink }}
                >
                  Password
                </label>
                <div className="relative">
                  <input
                    ref={passwordRef}
                    id={passwordId}
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    placeholder="Enter your password"
                    value={password}
                    onChange={handlePasswordChange}
                    disabled={isSubmitting}
                    aria-invalid={Boolean(errors.password)}
                    aria-describedby={
                      errors.password ? passwordErrorId : undefined
                    }
                    className="csp-input w-full rounded-sm px-4 py-3 pr-11 font-ui text-sm disabled:opacity-60"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    disabled={isSubmitting}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    aria-pressed={showPassword}
                    className="csp-toggle absolute right-2 top-1/2 -translate-y-1/2 grid place-items-center w-8 h-8 rounded-sm disabled:opacity-60"
                    style={{ color: C.inkFaint }}
                  >
                    <Eye
                      size={18}
                      aria-hidden="true"
                      className="transition-opacity duration-150"
                      style={{ opacity: showPassword ? 0 : 1, gridArea: '1 / 1' }}
                    />
                    <EyeOff
                      size={18}
                      aria-hidden="true"
                      className="transition-opacity duration-150"
                      style={{ opacity: showPassword ? 1 : 0, gridArea: '1 / 1' }}
                    />
                  </button>
                </div>
                <div className="min-h-5 mt-1">
                  {errors.password && (
                    <p
                      id={passwordErrorId}
                      role="alert"
                      className="csp-error font-ui text-xs"
                      style={{ color: C.rose }}
                    >
                      {errors.password}
                    </p>
                  )}
                </div>
                <div className="text-right mt-1">
                  <Link
                    to="/forgot-password"
                    className="font-ui text-xs font-medium transition-colors duration-200 hover:underline"
                    style={{ color: C.teal }}
                  >
                    Forgot password?
                  </Link>
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                aria-label={
                  status === 'loading'
                    ? 'Logging in, please wait'
                    : status === 'success'
                      ? 'Login successful'
                      : 'Log in'
                }
                className={`csp-btn-primary w-full flex items-center justify-center gap-2 px-5 py-3 rounded-sm font-medium font-ui ${
                  isSubmitting ? '' : 'hover:-translate-y-0.5'
                }`}
                style={{
                  backgroundColor: status === 'success' ? C.green : C.teal,
                  color: C.paper,
                }}
              >
                {status === 'loading' && (
                  <>
                    <Loader2 size={18} className="animate-spin" aria-hidden="true" />
                    Logging in...
                  </>
                )}
                {status === 'success' && (
                  <>
                    <Check size={18} aria-hidden="true" />
                    Success
                  </>
                )}
                {status === 'idle' && 'Log in'}
              </button>

              <p aria-live="polite" className="sr-only">
                {status === 'loading' && 'Logging in, please wait.'}
                {status === 'success' && 'Login successful. Redirecting.'}
              </p>
            </form>

            <p
              className="font-ui text-sm text-center mt-6"
              style={{ color: C.inkFaint }}
            >
              Don't have an account?{' '}
              <Link
                to="/signup"
                className="font-medium transition-colors duration-200 hover:underline"
                style={{ color: C.teal }}
              >
                Sign up
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
