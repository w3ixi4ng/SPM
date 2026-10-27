import { AlertTriangle, ChevronRight, ListChecks, LogOut, Plus } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import useVenueList from '../components/useVenueList.js'
import VenueList from '../components/VenueList.jsx'
import { getRoleAccess, hasPermission, PERMISSIONS } from '../lib/access.js'
import {
  clashPairLabel,
  clashReviewHeading,
  getClashesToReview,
  listPendingVenueBookings,
  listVenuePreparationBookings,
  pendingListErrorMessage,
  pendingRequestPath,
  pendingRequestSummary,
  updateVenuePreparation,
  VENUE_PREPARATION_OPTIONS,
  venuePreparationErrorMessage,
} from '../lib/venueBookings.js'

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

// S-30 built venue availability: each venue's Availability link above.
const UPCOMING_AREAS = [
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

function usePreparationBookings(enabled) {
  const [state, setState] = useState({ bookings: [], loading: enabled, error: null })
  const load = useCallback(() => listVenuePreparationBookings().then(
    (bookings) => ({ bookings, loading: false, error: null }),
    (error) => ({ bookings: [], loading: false, error: pendingListErrorMessage(error) }),
  ), [])
  useEffect(() => {
    if (!enabled) return undefined
    let active = true
    load().then((next) => { if (active) setState(next) })
    return () => { active = false }
  }, [enabled, load])
  const reload = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: null }))
    load().then(setState)
  }, [load])
  return { ...state, reload, setState }
}

function PreparationBookings({ state }) {
  const [saving, setSaving] = useState(null)
  async function change(booking, nextStatus) {
    setSaving(booking.id)
    try {
      const updated = await updateVenuePreparation(
        booking.id, nextStatus, booking.venue_preparation_version ?? 0,
      )
      state.setState((current) => ({
        ...current,
        error: null,
        bookings: current.bookings.map((item) => item.id === updated.id ? updated : item),
      }))
    } catch (error) {
      state.setState((current) => ({ ...current, error: venuePreparationErrorMessage(error) }))
    } finally {
      setSaving(null)
    }
  }
  return (
    <section className="max-w-3xl mb-12" aria-labelledby="preparation-heading">
      <h2 id="preparation-heading" className="font-display text-3xl mb-2" style={{ color: C.ink }}>
        Venue preparation
      </h2>
      <p className="font-ui text-sm mb-5" style={{ color: C.inkFaint }}>
        Update each confirmed venue after its event reaches Preparation.
      </p>
      {state.loading && <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading venue preparationâ€¦</p>}
      {state.error && <p role="alert" className="font-ui text-sm mb-3" style={{ color: C.rose }}>{state.error}</p>}
      {!state.loading && state.bookings.length === 0 && (
        <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No venues currently need preparation.</p>
      )}
      <ul className="divide-y" aria-label="Venue preparation bookings">
        {state.bookings.map((booking) => (
          <li key={booking.id} className="py-4 flex flex-wrap items-center justify-between gap-4" style={{ borderColor: C.line }}>
            <span>
              <strong className="block font-ui text-sm" style={{ color: C.ink }}>{booking.venue_name}</strong>
              <span className="block font-ui text-xs" style={{ color: C.inkFaint }}>{booking.event_name} {' / '} {booking.booking_date}</span>
            </span>
            <label className="font-ui text-xs" style={{ color: C.inkFaint }}>
              <span className="sr-only">Preparation status for {booking.venue_name}, {booking.event_name}</span>
              <select
                value={booking.venue_preparation_status ?? 'not_started'}
                disabled={saving === booking.id}
                onChange={(event) => change(booking, event.target.value)}
                className="border rounded-sm px-3 py-2 bg-white"
                style={{ borderColor: C.line, color: C.ink }}
              >
                {VENUE_PREPARATION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </li>
        ))}
      </ul>
    </section>
  )
}

// S-75: one row per request. The details, hold and decision are on the
// request's own page, so the list stays short.
function PendingBooking({ booking }) {
  const summary = pendingRequestSummary(booking)
  return (
    <li style={{ borderColor: C.line }}>
      <Link
        to={pendingRequestPath(booking)}
        className="csp-request-row flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-4 px-3 -mx-3 rounded-sm"
        aria-label={`Review ${summary.title}, ${summary.line}, ${summary.status.label}${summary.clash ? ', clashes with another booking' : ''}`}
      >
        <span className="min-w-0">
          <span className="block font-ui text-base font-medium" style={{ color: C.ink }}>{summary.title}</span>
          <span className="block font-ui text-sm" style={{ color: C.inkFaint }}>{summary.line}</span>
        </span>
        <span className="flex items-center gap-4 font-ui text-xs shrink-0">
          {summary.clash && (
            <span className="inline-flex items-center gap-1" style={{ color: C.rose }}>
              <AlertTriangle size={13} aria-hidden="true" />
              {summary.clash}
            </span>
          )}
          <span className="inline-flex items-center gap-1.5" style={{ color: summary.status.color }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: summary.status.color }} aria-hidden="true" />
            {summary.status.label}
          </span>
          <ChevronRight size={16} aria-hidden="true" style={{ color: C.inkFaint }} />
        </span>
      </Link>
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

// S-76: every venue's clashing bookings, worked out on each load, so a clash
// stays here until Staff resolve it. Read-only: nothing is changed.
function useClashesToReview(enabled) {
  const [state, setState] = useState({ venues: [], loading: enabled, error: null })

  const load = useCallback(() => getClashesToReview().then(
    ({ venues }) => ({ venues, loading: false, error: null }),
    (error) => ({ venues: [], loading: false, error: pendingListErrorMessage(error) }),
  ), [])

  useEffect(() => {
    if (!enabled) return undefined
    let active = true
    load().then((next) => { if (active) setState(next) })
    return () => { active = false }
  }, [enabled, load])

  const reload = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: null }))
    load().then(setState)
  }, [load])
  return { ...state, reload }
}

function ClashesToReview({ venues, error, onRetry }) {
  return (
    <section className="max-w-3xl mb-12" aria-labelledby="clashes-heading">
      <h2 id="clashes-heading" className="font-display text-3xl mb-2" style={{ color: C.ink }}>
        Clashes to review
      </h2>
      {error ? (
        <div className="font-ui text-sm" style={{ color: C.rose }}>
          <p role="alert">{error}</p>
          <button type="button" onClick={onRetry} className="underline mt-1" style={{ color: C.teal }}>
            Try again
          </button>
        </div>
      ) : (
        <>
          <p className="font-ui text-sm leading-relaxed max-w-md mb-6" style={{ color: C.inkFaint }}>
            These bookings overlap once each venue&apos;s setup and turnaround times are counted.
            Nothing has been changed or cancelled. Rearrange them with their Coordinators.
          </p>
          <ul className="divide-y" aria-label="Clashes to review">
            {venues.map((venue) => (
              <li key={venue.venue_id} className="py-4 first:pt-0" style={{ borderColor: C.line }}>
                <h3 className="flex items-center gap-2 font-ui text-base font-medium" style={{ color: C.ink }}>
                  <AlertTriangle size={16} aria-hidden="true" style={{ color: C.rose }} />
                  {clashReviewHeading(venue)}
                </h3>
                <ul className="list-disc pl-6 mt-1 space-y-0.5 font-ui text-sm" style={{ color: C.inkFaint }}>
                  {venue.pairs.map((pair) => (
                    <li key={`${pair.first.id}-${pair.second.id}`}>{clashPairLabel(pair)}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

// S-75: right after Staff change a venue's setup/turnaround, the bookings
// those times now make clash. Nothing has been changed or removed.
function ClashList({ clashes, onDismiss }) {
  const { venue, pairs } = clashes
  return (
    <div className="rounded-sm px-4 py-3 mb-6 font-ui text-sm" style={{ backgroundColor: C.paperDim, color: C.ink }}>
      {pairs.length === 0 ? (
        <p>No bookings at {venue || 'this venue'} clash under the new setup and turnaround times.</p>
      ) : (
        <>
          <p className="flex items-center gap-2 font-medium mb-1" style={{ color: C.rose }}>
            <AlertTriangle size={16} aria-hidden="true" />
            {pairs.length === 1 ? '1 pair of bookings' : `${pairs.length} pairs of bookings`} at {venue || 'this venue'} now clash
          </p>
          <ul className="list-disc pl-5 space-y-0.5" aria-label="Clashing bookings">
            {pairs.map((pair) => <li key={`${pair.first.id}-${pair.second.id}`}>{clashPairLabel(pair)}</li>)}
          </ul>
          <p className="mt-1" style={{ color: C.inkFaint }}>
            Nothing has been changed or cancelled. Their Coordinators see a warning on their events.
          </p>
        </>
      )}
      <button type="button" onClick={onDismiss} className="underline mt-2 font-ui text-xs" style={{ color: C.teal }}>
        Dismiss
      </button>
    </div>
  )
}

export default function VenueStaffDashboard({ role }) {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const access = getRoleAccess(role)
  const canAdd = hasPermission(role, PERMISSIONS.CREATE_VENUE)
  const canSeePending = hasPermission(role, PERMISSIONS.VIEW_PENDING_VENUE_BOOKINGS)
  const canPrepare = hasPermission(role, PERMISSIONS.UPDATE_VENUE_PREPARATION)
  const pending = usePendingBookings(canSeePending)
  const preparation = usePreparationBookings(canPrepare)
  const review = useClashesToReview(canSeePending)
  const { venues, loading, error, reload } = useVenueList()
  const location = useLocation()
  // Set by the venue form after a save. Read once, then cleared from history
  // so a reload or Back does not announce the same save again.
  const [notice, setNotice] = useState(location.state?.notice ?? null)
  // S-75: bookings the venue form's new setup/turnaround times make clash.
  // Kept until dismissed: Staff need them to rearrange the bookings.
  const [clashes, setClashes] = useState(
    location.state?.clashes ? { venue: location.state.clashVenue, pairs: location.state.clashes } : null,
  )

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
        .csp-request-row { transition: background-color 0.2s; }
        .csp-request-row:hover { background-color: ${C.paperDim}; }
        .csp-request-row:focus-visible,
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

        {canPrepare && <PreparationBookings state={preparation} />}

        {canSeePending && !review.loading && (review.error || review.venues.length > 0) && (
          <ClashesToReview venues={review.venues} error={review.error} onRetry={review.reload} />
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
          {clashes && <ClashList clashes={clashes} onDismiss={() => setClashes(null)} />}
          <VenueList
            canEdit={hasPermission(role, PERMISSIONS.UPDATE_VENUE)}
            canViewAvailability={hasPermission(role, PERMISSIONS.VIEW_VENUE_AVAILABILITY)}
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
