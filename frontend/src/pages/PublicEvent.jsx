import { useEffect, useRef, useState } from 'react'
import { CalendarDays, ChevronLeft, Loader2, MapPin, Ticket } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import {
  acceptOffer,
  canWithdraw,
  declineOffer,
  declinePrompt,
  describeRegistration,
  formatEventWhen,
  getMyRegistration,
  getPublicEvent,
  joinWaitingList,
  registerForEvent,
  registrationCountdown,
  waitingListPlace,
  withdrawPrompt,
  withdrawRegistration,
} from '../lib/registration.js'

const C = {
  ink: '#10192B',
  inkSoft: '#1C2A42',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  lineOnInk: '#2A3A54',
  teal: '#0E7C74',
  tealBright: '#149E92',
  amber: '#B5842B',
  rose: '#B25547',
  green: '#3F8F5F',
}

// The countdown only needs minute precision.
const TICK_MS = 30 * 1000

function useNow() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), TICK_MS)
    return () => clearInterval(timer)
  }, [])
  return now
}

function Header({ signedIn }) {
  return (
    <header className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-between gap-6">
      <Logo />
      {signedIn ? (
        <Link
          to="/dashboard"
          className="csp-ghost px-5 py-3 rounded-sm font-ui text-sm font-medium border"
          style={{ borderColor: C.ink, color: C.ink }}
        >
          Your dashboard
        </Link>
      ) : (
        <Link
          to="/login"
          className="csp-ghost px-5 py-3 rounded-sm font-ui text-sm font-medium border"
          style={{ borderColor: C.ink, color: C.ink }}
        >
          Sign in
        </Link>
      )}
    </header>
  )
}

function Fact({ icon: Icon, label, children }) {
  return (
    <div className="flex gap-4 py-4">
      <Icon size={20} aria-hidden="true" style={{ color: C.inkFaint, flexShrink: 0, marginTop: 2 }} />
      <div>
        <p className="font-ui text-xs" style={{ color: C.inkFaint }}>{label}</p>
        <p className="font-ui text-base font-medium" style={{ color: C.ink }}>{children}</p>
      </div>
    </div>
  )
}

// The page's one bold moment: where registration stands right now, with a
// live countdown to the next change, and the action that goes with it.
// S-53: giving up a place can't be undone -- registering again may mean the
// back of the waiting list -- so it asks first, inline. S-55: declining a held
// place asks the same way.
function ConfirmControl({ label, prompt, confirm, busyLabel, keepLabel, onConfirm, busy, className = '' }) {
  const [confirming, setConfirming] = useState(false)
  const trigger = useRef(null)
  const keep = useRef(null)
  const opened = useRef(false)

  useEffect(() => {
    if (confirming) keep.current?.focus()
    else if (opened.current) trigger.current?.focus()
    opened.current = confirming
  }, [confirming])

  if (!confirming) {
    return (
      <button
        ref={trigger}
        type="button"
        onClick={() => setConfirming(true)}
        className={`csp-ghost px-5 py-3 rounded-sm font-ui text-sm font-medium border ${className}`}
        style={{ borderColor: C.paper, color: C.paper }}
      >
        {label}
      </button>
    )
  }
  return (
    <div
      className="mt-5 pt-5 border-t"
      style={{ borderColor: C.lineOnInk }}
      onKeyDown={(e) => { if (e.key === 'Escape' && !busy) setConfirming(false) }}
    >
      <p className="font-ui text-sm leading-relaxed max-w-sm mb-4" style={{ color: C.paper }}>
        {prompt}
      </p>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className="csp-primary inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium transition-transform duration-200 disabled:opacity-70"
          style={{ backgroundColor: C.teal, color: C.paper }}
        >
          {busy && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
          {busy ? busyLabel : confirm}
        </button>
        <button
          ref={keep}
          type="button"
          onClick={() => setConfirming(false)}
          disabled={busy}
          className="csp-ghost px-5 py-3 rounded-sm font-ui font-medium border disabled:opacity-70"
          style={{ borderColor: C.paper, color: C.paper }}
        >
          {keepLabel}
        </button>
      </div>
    </div>
  )
}

function RegistrationPanel({
  event, now, auth, registration, onRegister, onJoinWaitingList, registering, error,
  withdrawn, onWithdraw, withdrawing, declined, onAccept, onDecline, answering,
}) {
  const navigate = useNavigate()
  const { state, status } = describeRegistration(event, now)
  const countdown = registrationCountdown(event, now)
  const isAttendee = auth.status === 'authenticated' && auth.user?.role === 'attendee'
  const signedOut = auth.status === 'unauthenticated'

  let action = null
  if (registration?.registered) {
    action = (
      <>
        <p className="flex items-center gap-2 font-ui text-base" style={{ color: C.paper }}>
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: C.green }} aria-hidden="true" />
          You&apos;re registered for this event.
        </p>
        {canWithdraw(event, now) && (
          <ConfirmControl
            label="Withdraw registration"
            prompt={withdrawPrompt(event)}
            confirm="Withdraw"
            busyLabel="Withdrawing…"
            keepLabel="Keep my place"
            onConfirm={onWithdraw}
            busy={withdrawing}
            className="mt-5"
          />
        )}
      </>
    )
  } else if (registration?.offered) {
    // S-55: the place is held, not given -- only Accept place registers.
    action = (
      <>
        <p className="flex items-center gap-2 font-ui text-base leading-relaxed max-w-sm" style={{ color: C.paper }}>
          <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: C.amber }} aria-hidden="true" />
          A place is being held for you. Accept it to register, or decline to pass it to the next person.
        </p>
        <div className="mt-5 flex flex-wrap items-start gap-3">
          <button
            type="button"
            onClick={onAccept}
            disabled={answering}
            className="csp-primary inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium transition-transform duration-200 disabled:opacity-70"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            {answering && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
            {answering ? 'Accepting…' : 'Accept place'}
          </button>
          <ConfirmControl
            label="Decline"
            prompt={declinePrompt()}
            confirm="Decline"
            busyLabel="Declining…"
            keepLabel="Keep my offer"
            onConfirm={onDecline}
            busy={answering}
          />
        </div>
      </>
    )
  } else if (registration?.waitlisted) {
    // S-50
    action = (
      <p className="flex items-center gap-2 font-ui text-base" style={{ color: C.paper }}>
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: C.amber }} aria-hidden="true" />
        You&apos;re on the waiting list. {waitingListPlace(registration.position)}
      </p>
    )
  } else if (state === 'full' && (signedOut || isAttendee)) {
    action = (
      <button
        type="button"
        onClick={signedOut ? () => navigate('/login') : onJoinWaitingList}
        disabled={registering}
        className="csp-primary inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium transition-transform duration-200 disabled:opacity-70"
        style={{ backgroundColor: C.teal, color: C.paper }}
      >
        {registering && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
        {registering ? 'Joining…' : 'Join the waiting list'}
      </button>
    )
  } else if (state === 'open' && (signedOut || isAttendee)) {
    action = (
      <button
        type="button"
        onClick={signedOut ? () => navigate('/login') : onRegister}
        disabled={registering}
        className="csp-primary inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium transition-transform duration-200 disabled:opacity-70"
        style={{ backgroundColor: C.teal, color: C.paper }}
      >
        {registering && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
        {registering ? 'Registering…' : 'Register'}
      </button>
    )
  } else if ((state === 'open' || state === 'full') && auth.status === 'authenticated') {
    action = (
      <p className="font-ui text-sm" style={{ color: C.paper }}>
        Only attendee accounts can register for events.
      </p>
    )
  }

  return (
    <section
      aria-label="Registration"
      className="rise-in rounded-sm p-7 sm:p-8"
      style={{ backgroundColor: C.ink, animationDelay: '120ms' }}
    >
      {/* "Full -- join the waiting list" would mislead someone a place is held for. */}
      {!registration?.offered && (
        <p className="font-ui text-sm mb-2" style={{ color: C.paperDim }}>{status}</p>
      )}
      {countdown && (
        <p className="mb-6" aria-live="polite">
          <span className="block font-ui text-xs" style={{ color: C.paperDim }}>{countdown.label}</span>
          <span className="block text-4xl font-display" style={{ color: C.paper }}>
            {countdown.remaining}
          </span>
        </p>
      )}
      {withdrawn && (
        <p role="status" className="flex items-center gap-2 font-ui text-base mb-5" style={{ color: C.paper }}>
          <span className="w-2 h-2 rounded-full border" style={{ borderColor: C.paperDim }} aria-hidden="true" />
          You&apos;ve withdrawn from this event.
        </p>
      )}
      {declined && (
        <p role="status" className="flex items-center gap-2 font-ui text-base mb-5" style={{ color: C.paper }}>
          <span className="w-2 h-2 rounded-full border" style={{ borderColor: C.paperDim }} aria-hidden="true" />
          You&apos;ve declined the place and left the waiting list.
        </p>
      )}
      {action}
      {error && (
        <p role="alert" className="font-ui text-sm mt-4" style={{ color: C.paper }}>
          {error}
        </p>
      )}
    </section>
  )
}

export default function PublicEvent() {
  const { id } = useParams()
  const auth = useAuth()
  const now = useNow()
  const [load, setLoad] = useState({ status: 'loading', event: null, error: null })
  const [registration, setRegistration] = useState(null)
  const [registering, setRegistering] = useState(false)
  const [registerError, setRegisterError] = useState(null)
  // S-53: shown once, after withdrawing; a reload starts without it.
  const [withdrawn, setWithdrawn] = useState(false)
  const [withdrawing, setWithdrawing] = useState(false)
  // S-55: answering a held place; the decline message is shown once.
  const [answering, setAnswering] = useState(false)
  const [declined, setDeclined] = useState(false)
  // Bumped by Register / Join the waiting list, so a status lookup that
  // started before the click can't overwrite what the click returned.
  const actions = useRef(0)
  const isAttendee = auth.status === 'authenticated' && auth.user?.role === 'attendee'

  useEffect(() => {
    let active = true
    getPublicEvent(id)
      .then((event) => { if (active) setLoad({ status: 'ready', event, error: null }) })
      .catch((error) => {
        if (!active) return
        setLoad({
          status: 'error',
          event: null,
          error: error.status === 404
            ? "This event isn't open to the public. It may not be confirmed yet."
            : error.message,
        })
      })
    return () => { active = false }
  }, [id])

  useEffect(() => {
    let active = true
    if (!isAttendee || load.event?.registration_required !== true) return undefined
    const startedAt = actions.current
    getMyRegistration(id)
      .then((found) => { if (active && actions.current === startedAt) setRegistration(found) })
      .catch(() => {})
    return () => { active = false }
  }, [id, isAttendee, load.event])

  async function handleRegister() {
    actions.current += 1
    setRegistering(true)
    setRegisterError(null)
    setWithdrawn(false)
    setDeclined(false)
    try {
      setRegistration(await registerForEvent(id))
    } catch (error) {
      setRegisterError(error.message)
      // S-50: the last place went while the page was open; show the
      // waiting list instead of a stale Register button.
      if (error.status === 409) refreshEvent()
    } finally {
      setRegistering(false)
    }
  }

  async function handleJoinWaitingList() {
    actions.current += 1
    setRegistering(true)
    setRegisterError(null)
    setWithdrawn(false)
    setDeclined(false)
    try {
      const joined = await joinWaitingList(id)
      setRegistration({
        registered: false, waitlisted: true, joined_at: joined.joined_at, position: joined.position,
      })
    } catch (error) {
      setRegisterError(error.message)
      if (error.status === 409) refreshEvent()
    } finally {
      setRegistering(false)
    }
  }

  async function handleWithdraw() {
    actions.current += 1
    setWithdrawing(true)
    setRegisterError(null)
    try {
      setRegistration(await withdrawRegistration(id))
      setWithdrawn(true)
    } catch (error) {
      setRegisterError(error.message)
    } finally {
      setWithdrawing(false)
      // The freed place may now be held for the next person waiting, so the
      // event can be full again.
      refreshEvent()
    }
  }

  async function handleAccept() {
    actions.current += 1
    setAnswering(true)
    setRegisterError(null)
    try {
      setRegistration(await acceptOffer(id))
    } catch (error) {
      setRegisterError(error.message)
    } finally {
      setAnswering(false)
    }
  }

  async function handleDecline() {
    actions.current += 1
    setAnswering(true)
    setRegisterError(null)
    try {
      setRegistration(await declineOffer(id))
      setDeclined(true)
    } catch (error) {
      setRegisterError(error.message)
    } finally {
      setAnswering(false)
      // The place is now held for the next in line.
      refreshEvent()
    }
  }

  function refreshEvent() {
    getPublicEvent(id)
      .then((event) => setLoad({ status: 'ready', event, error: null }))
      .catch(() => {})
  }

  const event = load.event
  const { period } = event ? describeRegistration(event, now) : { period: null }

  return (
    <div className="font-ui min-h-screen" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        .csp-primary:hover:not(:disabled) { transform: translateY(-2px); }
        .csp-primary:focus-visible, .csp-ghost:focus-visible, .csp-back:focus-visible {
          outline: 2px solid ${C.tealBright};
          outline-offset: 2px;
        }
        .csp-back { transition: color 0.2s; }
        .csp-back:hover { color: ${C.teal}; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
          .csp-primary:hover:not(:disabled) { transform: none; }
        }
      `}</style>

      <Header signedIn={auth.status === 'authenticated'} />

      <main className="max-w-6xl mx-auto px-6 pb-20">
        <Link
          to="/public/events"
          className="csp-back inline-flex items-center gap-1 font-ui text-sm mb-8"
          style={{ color: C.inkFaint }}
        >
          <ChevronLeft size={16} aria-hidden="true" />
          Back to events
        </Link>

        {load.status === 'loading' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading the event…</p>
        )}

        {load.status === 'error' && (
          <p role="alert" className="font-ui text-base max-w-md" style={{ color: C.rose }}>
            {load.error}
          </p>
        )}

        {event && (
          <div className="grid md:grid-cols-[1.4fr_1fr] gap-10 items-start">
            <div>
              <h1 className="text-4xl sm:text-5xl font-display leading-tight mb-4" style={{ color: C.ink }}>
                {event.name}
              </h1>
              <p className="font-ui text-base leading-relaxed max-w-md mb-8" style={{ color: C.inkFaint }}>
                {event.purpose}
              </p>
              <div className="border-t border-b divide-y" style={{ borderColor: C.line }}>
                <Fact icon={CalendarDays} label="When">{formatEventWhen(event)}</Fact>
                <Fact icon={MapPin} label="Venue">
                  {event.venues.length ? event.venues.join(', ') : 'Venue to be confirmed'}
                </Fact>
                <Fact icon={Ticket} label="Registration">
                  {period ?? "This event doesn't need registration."}
                </Fact>
              </div>
            </div>

            <RegistrationPanel
              event={event}
              now={now}
              auth={auth}
              registration={registration}
              onRegister={handleRegister}
              onJoinWaitingList={handleJoinWaitingList}
              registering={registering}
              error={registerError}
              withdrawn={withdrawn}
              onWithdraw={handleWithdraw}
              withdrawing={withdrawing}
              declined={declined}
              onAccept={handleAccept}
              onDecline={handleDecline}
              answering={answering}
            />
          </div>
        )}
      </main>
    </div>
  )
}
