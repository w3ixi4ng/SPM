import { useEffect, useState } from 'react'
import { ArrowRight, Check, Loader2, LogOut } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import { getRoleAccess, hasPermission, PERMISSIONS } from '../lib/access.js'
import {
  eventErrorMessage,
  listEventRequests,
  organiserStatusMeta,
  sortEventsForOrganiser,
} from '../lib/eventRequests.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
  green: '#3F8F5F',
  paperDim: '#F0EDE5',
  amber: '#B5842B',
}

const ORGANISER_CAPABILITIES = [
  [PERMISSIONS.CREATE_EVENT, 'Create event requests'],
  [PERMISSIONS.SAVE_EVENT_DRAFT, 'Save incomplete requests as drafts'],
  [PERMISSIONS.VIEW_OWN_EVENTS, 'View your own requests'],
  [PERMISSIONS.UPDATE_OWN_EVENT_DRAFT, 'Update your own drafts'],
  [PERMISSIONS.SUBMIT_OWN_EVENT, 'Submit your own requests'],
]

function EventRequestList({ refreshAuth }) {
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [state, setState] = useState({
    status: 'loading',
    events: [],
    error: null,
  })

  useEffect(() => {
    let active = true
    listEventRequests()
      .then((events) => {
        if (active) setState({ status: 'ready', events: sortEventsForOrganiser(events), error: null })
      })
      .catch((error) => {
        if (!active) return
        setState({ status: 'error', events: [], error: eventErrorMessage(error) })
        if (error.status === 401) refreshAuth().catch(() => {})
      })
    return () => {
      active = false
    }
  }, [loadAttempt, refreshAuth])

  function retry() {
    setState({ status: 'loading', events: [], error: null })
    setLoadAttempt((attempt) => attempt + 1)
  }

  return (
    <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
      <div className="flex items-start justify-between gap-4 mb-5">
        <div>
          <p className="font-ui text-xs uppercase tracking-widest mb-2" style={{ color: C.teal }}>
            Event requests
          </p>
          <h2 className="font-display text-2xl" style={{ color: C.ink }}>Your requests</h2>
        </div>
        {state.status === 'ready' && state.events.length > 0 && (
          <span className="font-ui text-xs" style={{ color: C.inkFaint }}>
            {state.events.length} total
          </span>
        )}
      </div>

      {state.status === 'loading' && (
        <p className="font-ui text-sm flex items-center gap-2" style={{ color: C.inkFaint }}>
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
          Loading your event requests…
        </p>
      )}

      {state.status === 'error' && (
        <div role="alert" className="font-ui text-sm" style={{ color: C.inkFaint }}>
          <p>{state.error}</p>
          <button type="button" onClick={retry} className="font-medium underline mt-2" style={{ color: C.teal }}>
            Try again
          </button>
        </div>
      )}

      {state.status === 'ready' && state.events.length === 0 && (
        <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
          You have no saved event requests yet.
        </p>
      )}

      {state.status === 'ready' && state.events.length > 0 && (
        <ul className="divide-y" style={{ borderColor: C.line }}>
          {state.events.map((event) => {
            const { label: statusLabel, color: statusColor } = organiserStatusMeta(event.status)
            return (
              <li key={event.id} className="py-4 first:pt-0 last:pb-0">
                <Link
                  to={`/events/${event.id}`}
                  className="group flex items-center justify-between gap-5 rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4"
                  style={{ outlineColor: C.teal }}
                >
                  <div className="min-w-0">
                    <h3 className="font-ui text-sm font-medium truncate" style={{ color: C.ink }}>
                      {event.name || 'Untitled event'}
                    </h3>
                    <p className="font-ui text-xs mt-1" style={{ color: C.inkFaint }}>
                      {event.start_date || 'No date selected'}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span
                      className={`font-ui text-xs font-medium px-2.5 py-1 rounded-sm ${
                        event.status === 'returned' ? 'csp-pulse-badge' : ''
                      }`}
                      style={{ color: statusColor, backgroundColor: `${statusColor}1F` }}
                    >
                      {statusLabel}
                    </span>
                    <ArrowRight
                      size={16}
                      aria-hidden="true"
                      className="transition-transform group-hover:translate-x-1"
                      style={{ color: C.teal }}
                    />
                  </div>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

export default function Dashboard({ role }) {
  const navigate = useNavigate()
  const { user, signOut, refresh } = useAuth()
  const access = getRoleAccess(role)
  const capabilities = ORGANISER_CAPABILITIES.filter(([permission]) =>
    hasPermission(role, permission),
  )

  async function handleSignOut() {
    await signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div
      className="min-h-screen px-6 py-10 md:py-14"
      style={{ backgroundColor: C.paper }}
    >
      <style>{`
        @keyframes riseIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
        }

        .csp-signout-btn {
          border-color: ${C.ink};
          color: ${C.ink};
          transition: background-color 0.2s, color 0.2s;
        }
        .csp-signout-btn:hover { background-color: ${C.ink}; color: ${C.paper}; }
        .csp-signout-btn:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }

        /* Draws the eye to a request a coordinator sent back for amendment
           -- slow and subtle on purpose, not a hard flash. */
        @keyframes cspPulseBadge {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.62; transform: scale(1.04); }
        }
        .csp-pulse-badge { animation: cspPulseBadge 2.2s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .csp-pulse-badge { animation: none; }
        }
      `}</style>
      <div className="rise-in w-full max-w-5xl mx-auto">
        <header className="flex items-center justify-between gap-6 mb-14">
          <Logo />
          <button
            type="button"
            onClick={handleSignOut}
            className="csp-signout-btn inline-flex items-center gap-2 px-4 py-2 rounded-sm font-ui text-sm border"
          >
            <LogOut size={15} aria-hidden="true" />
            Sign out
          </button>
        </header>

        <div className="max-w-2xl mb-10">
          <div
            className="inline-flex items-center gap-2 text-xs font-ui px-3 py-1 rounded-sm mb-5"
            style={{ backgroundColor: 'rgba(63,143,95,0.12)', color: C.green }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.green }} />
            Signed in as {access.label}
          </div>
          <h1 className="font-display text-4xl sm:text-5xl mb-4" style={{ color: C.ink }}>
            {access.label} dashboard
          </h1>
          <p className="font-ui text-base leading-relaxed" style={{ color: C.inkFaint }}>
            {access.description}
          </p>
          <p className="font-ui text-xs mt-3" style={{ color: C.inkFaint }}>
            {user.name} · {user.email}
          </p>
        </div>

        {hasPermission(role, PERMISSIONS.CREATE_EVENT) ? (
          <div className="space-y-6">
            <div className="grid md:grid-cols-[1.2fr_1fr] gap-6 items-start">
              <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
                <p className="font-ui text-xs uppercase tracking-widest mb-3" style={{ color: C.teal }}>
                  Event requests
                </p>
                <h2 className="font-display text-2xl mb-3" style={{ color: C.ink }}>
                  Plan a new event
                </h2>
                <p className="font-ui text-sm leading-relaxed mb-6" style={{ color: C.inkFaint }}>
                  Add the event details you know now, then save a draft or submit it for review.
                </p>
                <Link
                  to="/events/new"
                  className="inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui text-sm font-medium text-white"
                  style={{ backgroundColor: C.teal }}
                >
                  Create event request
                  <ArrowRight size={16} aria-hidden="true" />
                </Link>
              </section>

              <section className="rounded-sm p-7 sm:p-8" style={{ backgroundColor: C.paperDim }}>
                <h2 className="font-display text-xl mb-5" style={{ color: C.ink }}>Your access</h2>
                <ul className="space-y-3">
                  {capabilities.map(([permission, label]) => (
                    <li key={permission} className="flex gap-3 font-ui text-sm" style={{ color: C.inkFaint }}>
                      <Check size={16} style={{ color: C.green }} aria-hidden="true" />
                      {label}
                    </li>
                  ))}
                </ul>
              </section>
            </div>

            <EventRequestList refreshAuth={refresh} />
          </div>
        ) : (
          <section className="border rounded-sm p-8 max-w-2xl" style={{ borderColor: C.line }}>
            <h2 className="font-display text-2xl mb-3" style={{ color: C.ink }}>
              No workflow actions yet
            </h2>
            <p className="font-ui text-sm leading-relaxed" style={{ color: C.inkFaint }}>
              No {access.label.toLowerCase()} features are defined for Sprint 1. This dashboard intentionally exposes no operational controls.
            </p>
          </section>
        )}
      </div>
    </div>
  )
}
