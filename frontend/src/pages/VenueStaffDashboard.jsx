import { CalendarDays, ListChecks, LogOut, Plus } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import useVenueList from '../components/useVenueList.js'
import VenueList from '../components/VenueList.jsx'
import { getRoleAccess, hasPermission, PERMISSIONS } from '../lib/access.js'
import {
  bookingDateLabel,
  listPendingVenueBookings,
  pendingListErrorMessage,
  shortTime,
} from '../lib/venueBookings.js'
import { optionLabel } from '../lib/venues.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F0EDE5',
  line: '#E3DFD3',
  teal: '#0E7C74',
  sky: '#3C6E96',
  amber: '#B5842B',
  rose: '#B25547',
  green: '#3F8F5F',
}

const UPCOMING_AREAS = [
  {
    icon: CalendarDays,
    title: 'Venue availability',
    description: 'Mark a venue as available or booked for a given date.',
  },
  {
    icon: ListChecks,
    title: 'Setup & teardown checklists',
    description: 'Confirm a space is ready before an event and reset after.',
  },
]

function usePendingBookings(enabled) {
  const [state, setState] = useState({ bookings: [], loading: enabled, error: null })

  const load = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: null }))
    return listPendingVenueBookings().then(
      (bookings) => ({ bookings, loading: false, error: null }),
      (error) => ({ bookings: [], loading: false, error: pendingListErrorMessage(error) }),
    )
  }, [])

  useEffect(() => {
    if (!enabled) return undefined
    let active = true
    load().then((next) => { if (active) setState(next) })
    return () => { active = false }
  }, [enabled, load])

  const reload = useCallback(() => { load().then(setState) }, [load])
  return { ...state, reload }
}

function Detail({ label, value }) {
  if (!value) return null
  return (
    <p className="font-ui text-sm" style={{ color: C.ink }}>
      <span style={{ color: C.inkFaint }}>{label}: </span>
      {value}
    </p>
  )
}

function listLabel(codes) {
  return codes.length > 0 ? codes.map(optionLabel).join(', ') : null
}

function PendingBooking({ booking }) {
  return (
    <li className="py-5 first:pt-0 last:pb-0" style={{ borderColor: C.line }}>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-2">
        <h3 className="font-ui text-base font-medium" style={{ color: C.ink }}>
          {booking.event_name}
          <span style={{ color: C.inkFaint }}> at </span>
          {booking.venue_name}
        </h3>
        <span className="inline-flex items-center gap-1.5 font-ui text-xs shrink-0 mt-1" style={{ color: C.amber }}>
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.amber }} aria-hidden="true" />
          Pending
        </span>
      </div>
      <p className="font-ui text-sm mb-2" style={{ color: C.ink }}>
        {bookingDateLabel(booking.booking_date)} · {shortTime(booking.start_time)}–{shortTime(booking.end_time)}
        {' · '}
        {booking.expected_attendance} expected
        {booking.room_layout && ` · ${optionLabel(booking.room_layout)}`}
      </p>
      <div className="space-y-0.5">
        <Detail label="Purpose" value={booking.event_purpose} />
        <Detail label="Facilities" value={listLabel(booking.required_facilities)} />
        <Detail label="Accessibility" value={listLabel(booking.required_accessibility)} />
        <Detail label="Organiser's accessibility notes" value={booking.accessibility_requirements} />
        <Detail label="Notes" value={booking.notes} />
      </div>
      <p className="font-ui text-xs mt-2" style={{ color: C.inkFaint }}>
        Requested by {booking.coordinator_name} ({booking.coordinator_email})
      </p>
    </li>
  )
}

function PendingBookings({ bookings, loading, error, onRetry }) {
  if (loading) {
    return <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading booking requests…</p>
  }
  if (error) {
    return (
      <div className="font-ui text-sm" style={{ color: C.rose }}>
        <p role="alert">{error}</p>
        <button type="button" onClick={onRetry} className="underline mt-1" style={{ color: C.teal }}>
          Try again
        </button>
      </div>
    )
  }
  if (bookings.length === 0) {
    return (
      <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
        No pending booking requests. Requests from Event Coordinators appear here.
      </p>
    )
  }
  return (
    <ul className="divide-y" aria-label="Pending booking requests">
      {bookings.map((booking) => <PendingBooking key={booking.id} booking={booking} />)}
    </ul>
  )
}

export default function VenueStaffDashboard({ role }) {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const access = getRoleAccess(role)
  const canAdd = hasPermission(role, PERMISSIONS.CREATE_VENUE)
  const canSeePending = hasPermission(role, PERMISSIONS.VIEW_PENDING_VENUE_BOOKINGS)
  const pending = usePendingBookings(canSeePending)
  const { venues, loading, error, reload } = useVenueList()
  const location = useLocation()
  // Set by the venue form after a save. Read once, then cleared from history
  // so a reload or Back does not announce the same save again.
  const [notice, setNotice] = useState(location.state?.notice ?? null)

  useEffect(() => {
    if (location.state?.notice) {
      navigate(location.pathname, { replace: true, state: null })
    }
  }, [location, navigate])

  useEffect(() => {
    if (!notice) return undefined
    const timer = setTimeout(() => setNotice(null), 4000)
    return () => clearTimeout(timer)
  }, [notice])

  async function handleSignOut() {
    await signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
          .csp-primary-btn:hover { transform: none; }
        }

        .csp-signout-btn {
          border-color: ${C.ink};
          color: ${C.ink};
          transition: background-color 0.2s, color 0.2s;
        }
        .csp-signout-btn:hover { background-color: ${C.ink}; color: ${C.paper}; }
        .csp-signout-btn:focus-visible,
        .csp-primary-btn:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
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
            Venue workspace
          </h1>
          <p className="font-ui text-base leading-relaxed" style={{ color: C.inkFaint }}>
            {access.description}
          </p>
          <p className="font-ui text-xs mt-3" style={{ color: C.inkFaint }}>
            {user.name} · {user.email}
          </p>
        </div>

        {canSeePending && (
          <section className="max-w-3xl mb-12" aria-labelledby="pending-heading">
            <h2 id="pending-heading" className="font-display text-3xl mb-6" style={{ color: C.ink }}>
              Pending booking requests
            </h2>
            <PendingBookings
              bookings={pending.bookings}
              loading={pending.loading}
              error={pending.error}
              onRetry={pending.reload}
            />
          </section>
        )}

        <section className="max-w-3xl mb-12" aria-labelledby="venues-heading">
          <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
            <h2 id="venues-heading" className="font-display text-3xl" style={{ color: C.ink }}>
              Your venues
            </h2>
            {canAdd && (
              <Link
                to="/venues/new"
                className="csp-primary-btn inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium transition-transform duration-200 hover:-translate-y-0.5"
                style={{ backgroundColor: C.teal, color: C.paper }}
              >
                <Plus size={16} aria-hidden="true" />
                Add venue
              </Link>
            )}
          </div>
          <div role="status" className="font-ui text-sm mb-4" style={{ color: C.green }}>
            {notice}
          </div>
          <VenueList
            canEdit={hasPermission(role, PERMISSIONS.UPDATE_VENUE)}
            venues={venues}
            loading={loading}
            error={error}
            onRetry={reload}
            emptyMessage="No venues yet. Add your first venue to start receiving booking requests."
          />
        </section>

        <section className="rounded-sm p-7 sm:p-8 max-w-3xl" style={{ backgroundColor: C.paperDim }}>
          <h2 className="font-display text-2xl mb-6" style={{ color: C.ink }}>
            More venue tools, on the way
          </h2>
          <ul className="divide-y">
            {UPCOMING_AREAS.map(({ icon: Icon, title, description }) => (
              <li
                key={title}
                className="py-4 first:pt-0 last:pb-0 flex items-start gap-4"
                style={{ borderColor: C.line }}
              >
                <Icon size={20} aria-hidden="true" className="mt-0.5 shrink-0" style={{ color: C.sky }} />
                <div className="min-w-0 flex-1">
                  <h3 className="font-ui text-base font-medium" style={{ color: C.ink }}>{title}</h3>
                  <p className="font-ui text-sm mt-0.5" style={{ color: C.inkFaint }}>{description}</p>
                </div>
                <span
                  className="inline-flex items-center gap-1.5 font-ui text-xs shrink-0 mt-1"
                  style={{ color: C.inkFaint }}
                >
                  <span
                    className="w-1.5 h-1.5 rounded-full border"
                    style={{ borderColor: C.inkFaint }}
                    aria-hidden="true"
                  />
                  Not started
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>

    </div>
  )
}
