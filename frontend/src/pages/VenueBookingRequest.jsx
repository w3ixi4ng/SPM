import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, ArrowLeft } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import BookingDecisionForm from '../components/BookingDecisionForm.jsx'
import Logo from '../components/Logo.jsx'
import { hasPermission, PERMISSIONS, ROLE_ACCESS } from '../lib/access.js'
import {
  bookingDateLabel,
  bookingStatusMeta,
  decisionNotice,
  getVenueBooking,
  holdActionErrorMessage,
  holdExpiryLabel,
  holdExpiryToIso,
  pendingListErrorMessage,
  placeVenueHold,
  releaseVenueHold,
  replacementOriginLabel,
  shortTime,
} from '../lib/venueBookings.js'
import { optionLabel } from '../lib/venues.js'

// S-75: one booking request on its own page, so Venue Staff's list on the
// dashboard stays one row per request. The details, any setup/turnaround
// clash, the hold and the decision all live here.

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  teal: '#0E7C74',
  amber: '#B5842B',
  rose: '#B25547',
}

const DASHBOARD = ROLE_ACCESS.venue_staff.dashboardPath
const ACTIONABLE = ['pending', 'held']

function Detail({ label, value }) {
  if (!value) return null
  return (
    <div className="font-ui text-sm">
      <dt className="inline" style={{ color: C.inkFaint }}>{label}: </dt>
      <dd className="inline" style={{ color: C.ink }}>{value}</dd>
    </div>
  )
}

function listLabel(codes) {
  return codes?.length > 0 ? codes.map(optionLabel).join(', ') : null
}

function Clashes({ booking }) {
  const clashes = booking.clashes ?? []
  if (clashes.length === 0) return null
  return (
    <div role="alert" className="rounded-sm px-4 py-3 mb-6 font-ui text-sm" style={{ backgroundColor: C.paperDim, color: C.ink }}>
      <p className="flex items-center gap-2 font-medium mb-1" style={{ color: C.rose }}>
        <AlertTriangle size={16} aria-hidden="true" />
        Clashes under {booking.venue_name}&apos;s setup and turnaround times
      </p>
      <ul className="list-disc pl-5 space-y-0.5">
        {clashes.map((clash) => (
          <li key={`${clash.booking_date}-${clash.start_time}`}>
            Another {bookingStatusMeta(clash.status).label.toLowerCase()} booking,{' '}
            {shortTime(clash.start_time)}–{shortTime(clash.end_time)} (venue in use {clash.occupied_start}–{clash.occupied_end})
          </li>
        ))}
      </ul>
      <p className="mt-1" style={{ color: C.inkFaint }}>
        With setup {booking.setup_minutes} min and turnaround {booking.turnaround_minutes} min. Nothing has been changed:
        arrange the times with the Coordinators involved.
      </p>
    </div>
  )
}

function HoldAction({ booking, onChanged }) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [expiry, setExpiry] = useState('')

  async function change() {
    setSaving(true)
    setError(null)
    try {
      if (booking.status === 'held') await releaseVenueHold(booking.id)
      else {
        const parsed = holdExpiryToIso(expiry)
        if (parsed.error) {
          setError(parsed.error)
          setSaving(false)
          return
        }
        await placeVenueHold(booking.id, parsed.expiresAt)
      }
      await onChanged()
    } catch (failure) {
      setError(holdActionErrorMessage(failure))
    }
    setSaving(false)
  }

  return (
    <div className="mb-8">
      {booking.status === 'held' ? (
        <p className="font-ui text-sm mb-3" style={{ color: C.inkFaint }}>
          Expires {holdExpiryLabel(booking.hold_expires_at)} Singapore time
        </p>
      ) : (
        <label className="block font-ui text-sm mb-3" style={{ color: C.ink }}>
          Hold expiry (Singapore time)
          <input
            type="datetime-local"
            required
            value={expiry}
            onChange={(event) => setExpiry(event.target.value)}
            className="block mt-1 px-3 py-2 rounded-sm border"
            style={{ borderColor: C.line }}
          />
        </label>
      )}
      <button
        type="button"
        disabled={saving}
        onClick={change}
        className="csp-hold-btn px-4 py-2 rounded-sm border font-ui text-sm disabled:opacity-60"
        style={{ borderColor: C.amber, color: C.amber }}
      >
        {saving ? 'Saving…' : booking.status === 'held' ? 'Release hold' : 'Place hold'}
      </button>
      {error && <p role="alert" className="font-ui text-sm mt-2" style={{ color: C.rose }}>{error}</p>}
    </div>
  )
}

export default function VenueBookingRequest() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [state, setState] = useState({ status: 'loading', booking: null, error: null })

  const load = useCallback(() => getVenueBooking(id).then(
    (booking) => setState({ status: 'ready', booking, error: null }),
    (error) => setState({
      status: 'error',
      booking: null,
      error: error.status === 404 ? 'This booking request could not be found.' : pendingListErrorMessage(error),
    }),
  ), [id])

  useEffect(() => { load() }, [load])

  function handleDecided(updated) {
    const decision = updated.status === 'confirmed' ? 'approved' : 'rejected'
    // Shown once on the dashboard, then cleared, so a reload doesn't repeat it.
    navigate(DASHBOARD, { state: { notice: decisionNotice(decision, { ...state.booking, ...updated }) } })
  }

  const { booking } = state
  const status = booking && bookingStatusMeta(booking.status)
  const actionable = booking && ACTIONABLE.includes(booking.status)

  return (
    <div className="font-ui min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        .csp-hold-btn:focus-visible { outline: 2px solid ${C.teal}; outline-offset: 2px; }
      `}</style>
      <div className="w-full max-w-3xl mx-auto">
        <header className="flex items-center justify-between gap-6 mb-10">
          <Logo />
          <Link to={DASHBOARD} className="inline-flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
            <ArrowLeft size={15} aria-hidden="true" />
            Back to dashboard
          </Link>
        </header>

        {state.status === 'loading' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading the booking request…</p>
        )}
        {state.status === 'error' && (
          <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>{state.error}</p>
        )}

        {booking && (
          <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }} aria-labelledby="request-heading">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-2">
              <h1 id="request-heading" className="font-display text-3xl" style={{ color: C.ink }}>
                {booking.event_name}
              </h1>
              <span className="inline-flex items-center gap-1.5 font-ui text-sm mt-2" style={{ color: status.color }}>
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: status.color }} aria-hidden="true" />
                {status.label}
              </span>
            </div>
            <p className="font-ui text-base mb-6" style={{ color: C.ink }}>
              {booking.venue_name} · {bookingDateLabel(booking.booking_date)},{' '}
              {shortTime(booking.start_time)}–{shortTime(booking.end_time)}
            </p>
            {replacementOriginLabel(booking) && (
              // S-78: the Coordinator is replacing a booking an unavailable
              // period affects. Approving this replaces that one.
              <p className="font-ui text-sm -mt-4 mb-6" style={{ color: C.inkFaint }}>
                {replacementOriginLabel(booking)} ({bookingDateLabel(booking.replaces.booking_date)},{' '}
                {shortTime(booking.replaces.start_time)}–{shortTime(booking.replaces.end_time)}). Approving this
                request releases that booking.
              </p>
            )}

            <Clashes booking={booking} />

            <dl className="grid gap-1 mb-4">
              <Detail label="Expected attendance" value={booking.expected_attendance} />
              <Detail label="Room layout" value={booking.room_layout && optionLabel(booking.room_layout)} />
              <Detail label="Purpose" value={booking.event_purpose} />
              <Detail label="Facilities" value={listLabel(booking.required_facilities)} />
              <Detail label="Accessibility" value={listLabel(booking.required_accessibility)} />
              <Detail label="Other requirements" value={booking.special_requirements} />
              <Detail label="Notes" value={booking.notes} />
            </dl>
            <p className="font-ui text-xs mb-8" style={{ color: C.inkFaint }}>
              Requested by {booking.coordinator_name} ({booking.coordinator_email})
            </p>

            {!actionable && (
              <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                This request has already been decided ({status.label.toLowerCase()}).
              </p>
            )}
            {actionable && hasPermission(user?.role, PERMISSIONS.MANAGE_VENUE_HOLDS) && (
              <HoldAction booking={booking} onChanged={load} />
            )}
            {actionable && hasPermission(user?.role, PERMISSIONS.DECIDE_VENUE_BOOKING) && (
              <BookingDecisionForm booking={booking} onDecided={handleDecided} />
            )}
          </section>
        )}
      </div>
    </div>
  )
}
