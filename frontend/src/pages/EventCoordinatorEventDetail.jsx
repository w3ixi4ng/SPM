import { useEffect, useState } from 'react'
import { ArrowLeft, Building2, Check, RotateCcw, X } from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import { hasPermission, PERMISSIONS } from '../lib/access.js'
import { optionLabel } from '../lib/venues.js'
import {
  decideEventRequest,
  eventErrorMessage,
  eventResponseToForm,
  eventStatusMeta,
  getAssignedEventRequest,
} from '../lib/eventRequests.js'
import {
  bookingDateLabel,
  bookingStatusMeta,
  canRequestVenue,
  listVenueBookingsForEvent,
  shortTime,
} from '../lib/venueBookings.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F0EDE5',
  line: '#E3DFD3',
  teal: '#0E7C74',
  amber: '#B5842B',
  rose: '#B25547',
  green: '#3F8F5F',
}

const DECISIONS = [
  { value: 'approved', label: 'Approve', icon: Check, color: C.green },
  { value: 'returned', label: 'Return for amendment', icon: RotateCcw, color: C.amber },
  { value: 'rejected', label: 'Reject', icon: X, color: C.rose },
]

function Field({ label, value }) {
  return (
    <div>
      <p className="font-ui text-xs uppercase tracking-wide" style={{ color: C.inkFaint }}>
        {label}
      </p>
      <p className="font-ui text-base mt-1" style={{ color: C.ink }}>
        {value || '—'}
      </p>
    </div>
  )
}

function equipmentSummary(equipmentRequests) {
  const entries = Object.entries(equipmentRequests ?? {})
  if (entries.length === 0) return null
  return entries.map(([name, quantity]) => `${quantity}× ${name}`).join(', ')
}

function DecisionRecord({ event }) {
  const { label, color } = eventStatusMeta(event.status)
  return (
    <div className="border rounded-sm p-5 mb-8" style={{ borderColor: color, backgroundColor: `${color}0D` }}>
      <p className="font-ui text-sm font-medium mb-2" style={{ color }}>
        {label}
      </p>
      {event.decision_reason && (
        <p className="font-ui text-sm mb-1" style={{ color: C.ink }}>
          <span style={{ color: C.inkFaint }}>Reason: </span>
          {event.decision_reason}
        </p>
      )}
      {event.decision_comment && (
        <p className="font-ui text-sm mb-1" style={{ color: C.ink }}>
          <span style={{ color: C.inkFaint }}>Note for the organiser: </span>
          {event.decision_comment}
        </p>
      )}
      {event.decided_at && (
        <p className="font-ui text-xs mt-2" style={{ color: C.inkFaint }}>
          Decided {new Date(event.decided_at).toLocaleString()}
        </p>
      )}
    </div>
  )
}

function DecisionForm({ eventId, onDecided }) {
  const [choice, setChoice] = useState(null)
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const [fieldError, setFieldError] = useState(null)
  const [submitState, setSubmitState] = useState({ status: 'idle', error: null })

  const needsReason = choice === 'rejected' || choice === 'returned'
  const allowsComment = choice === 'returned'

  function selectChoice(value) {
    setChoice(value)
    setFieldError(null)
    if (value !== 'returned') setComment('')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!choice) {
      setFieldError('Choose a decision first.')
      return
    }
    if (needsReason && !reason.trim()) {
      setFieldError('A reason is required to reject or return a request.')
      return
    }
    setFieldError(null)
    setSubmitState({ status: 'saving', error: null })
    try {
      const updated = await decideEventRequest(eventId, {
        decision: choice,
        reason: needsReason ? reason.trim() : undefined,
        comment: allowsComment ? comment.trim() : undefined,
      })
      onDecided(updated)
    } catch (error) {
      setSubmitState({ status: 'idle', error: eventErrorMessage(error) })
    }
  }

  return (
    <form onSubmit={handleSubmit} className="border rounded-sm p-6 mb-8" style={{ borderColor: C.line }}>
      <h2 className="font-display text-xl mb-4" style={{ color: C.ink }}>
        Record your decision
      </h2>

      <div className="flex flex-wrap gap-3 mb-5" role="radiogroup" aria-label="Decision">
        {DECISIONS.map(({ value, label, icon: Icon, color }) => {
          const selected = choice === value
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => selectChoice(value)}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-sm font-ui text-sm font-medium border transition-colors duration-200"
              style={{
                borderColor: color,
                color: selected ? C.paper : color,
                backgroundColor: selected ? color : 'transparent',
              }}
            >
              <Icon size={15} aria-hidden="true" />
              {label}
            </button>
          )
        })}
      </div>

      {needsReason && (
        <div className="mb-5">
          <label htmlFor="decision-reason" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
            Reason <span style={{ color: C.rose }}>*</span>
          </label>
          <textarea
            id="decision-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            className="w-full rounded-sm border px-3 py-2 font-ui text-sm"
            style={{ borderColor: C.line, color: C.ink }}
            placeholder={
              choice === 'rejected'
                ? 'Why this request is being rejected'
                : 'What needs to change before this can be approved'
            }
          />
        </div>
      )}

      {allowsComment && (
        <div className="mb-5">
          <label htmlFor="decision-comment" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
            Note for the organiser (optional)
          </label>
          <textarea
            id="decision-comment"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            rows={2}
            className="w-full rounded-sm border px-3 py-2 font-ui text-sm"
            style={{ borderColor: C.line, color: C.ink }}
            placeholder="Any clarification or amendment guidance"
          />
        </div>
      )}

      {(fieldError || submitState.error) && (
        <p role="alert" className="font-ui text-sm mb-4" style={{ color: C.rose }}>
          {fieldError || submitState.error}
        </p>
      )}

      <button
        type="submit"
        disabled={submitState.status === 'saving'}
        className="px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
        style={{ backgroundColor: C.teal, color: C.paper }}
      >
        {submitState.status === 'saving' ? 'Saving…' : 'Record decision'}
      </button>
    </form>
  )
}

// What this Coordinator has already asked for, so a reload never leaves them
// guessing whether a request went out.
function VenueRequests({ eventId }) {
  const [state, setState] = useState({ status: 'loading', bookings: [] })

  useEffect(() => {
    let active = true
    listVenueBookingsForEvent(eventId)
      .then((bookings) => {
        if (active) setState({ status: 'ready', bookings })
      })
      .catch(() => {
        if (active) setState({ status: 'error', bookings: [] })
      })
    return () => {
      active = false
    }
  }, [eventId])

  return (
    <section className="mb-8" aria-labelledby="venue-requests-heading">
      <h2 id="venue-requests-heading" className="font-display text-xl mb-4" style={{ color: C.ink }}>
        Venue requests
      </h2>
      {state.status === 'loading' && (
        <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading venue requests…</p>
      )}
      {state.status === 'error' && (
        <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>
          We couldn&apos;t load the venue requests for this event. Reload the page to try again.
        </p>
      )}
      {state.status === 'ready' && state.bookings.length === 0 && (
        <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No venue requests sent yet.</p>
      )}
      {state.status === 'ready' && state.bookings.length > 0 && (
        <ul className="divide-y" aria-label="Venue requests sent">
          {state.bookings.map((booking) => {
            const { label, color } = bookingStatusMeta(booking.status)
            return (
              <li
                key={booking.id}
                className="py-3 first:pt-0 last:pb-0 flex flex-wrap items-center justify-between gap-3"
                style={{ borderColor: C.line }}
              >
                <div className="min-w-0">
                  <p className="font-ui text-base font-medium" style={{ color: C.ink }}>{booking.venue_name}</p>
                  <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                    {bookingDateLabel(booking.booking_date)} · {shortTime(booking.start_time)}–{shortTime(booking.end_time)}
                  </p>
                </div>
                <span className="inline-flex items-center gap-1.5 font-ui text-xs shrink-0" style={{ color }}>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} aria-hidden="true" />
                  {label}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

export default function EventCoordinatorEventDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const [state, setState] = useState({ status: 'loading', event: null, error: null })
  const location = useLocation()
  const navigate = useNavigate()
  // Set by the venue request screen after a send. Read once, then cleared
  // from history so a reload or Back does not announce the same send again.
  const [notice] = useState(location.state?.notice ?? null)

  useEffect(() => {
    if (location.state?.notice) {
      navigate(location.pathname, { replace: true, state: null })
    }
  }, [location, navigate])

  useEffect(() => {
    let active = true
    setState({ status: 'loading', event: null, error: null })

    getAssignedEventRequest(id)
      .then((event) => {
        if (active) setState({ status: 'ready', event, error: null })
      })
      .catch((error) => {
        if (active) setState({ status: 'error', event: null, error: eventErrorMessage(error) })
      })

    return () => {
      active = false
    }
  }, [id])

  const form = state.event ? eventResponseToForm(state.event) : null
  const isCoordinator = hasPermission(user?.role, PERMISSIONS.REQUEST_VENUE_BOOKING)
  const showVenueRequest = state.event && isCoordinator && canRequestVenue(state.event.status)

  return (
    <div className="min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <div className="w-full max-w-3xl mx-auto">
        <header className="flex items-center justify-between gap-6 mb-10">
          <Logo />
          <Link
            to="/dashboard/event-coordinator"
            className="inline-flex items-center gap-2 font-ui text-sm"
            style={{ color: C.ink }}
          >
            <ArrowLeft size={15} aria-hidden="true" />
            Back to workspace
          </Link>
        </header>

        {state.status === 'loading' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
            Loading the event request…
          </p>
        )}

        {state.status === 'error' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
            {state.error}
          </p>
        )}

        {state.status === 'ready' && (
          <>
            {state.event.status === 'submitted' ? (
              <DecisionForm
                eventId={state.event.id}
                onDecided={(updated) => setState({ status: 'ready', event: updated, error: null })}
              />
            ) : (
              <DecisionRecord event={state.event} />
            )}

            {showVenueRequest && (
              <div className="flex flex-wrap items-center gap-4 mb-8">
                <Link
                  to={`/coordinator/events/${state.event.id}/request-venue`}
                  className="inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5"
                  style={{ backgroundColor: C.teal, color: C.paper }}
                >
                  <Building2 size={16} aria-hidden="true" />
                  Request venue
                </Link>
                <p role="status" className="font-ui text-sm" style={{ color: C.green }}>
                  {notice}
                </p>
              </div>
            )}

            {isCoordinator && <VenueRequests eventId={state.event.id} />}

            <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
              <h1 className="font-display text-3xl mb-8" style={{ color: C.ink }}>
                {form.name || 'Untitled event request'}
              </h1>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <Field label="Purpose" value={form.purpose} />
                <Field label="Venue preference" value={form.venue} />
                <Field label="Room layout" value={form.roomLayout && optionLabel(form.roomLayout)} />
                <Field label="Facilities needed" value={form.requiredFacilities.map(optionLabel).join(', ')} />
                <Field label="Accessibility needed" value={form.requiredAccessibility.map(optionLabel).join(', ')} />
                <Field
                  label="Starts"
                  value={form.startDate && `${form.startDate} at ${form.startTime}`}
                />
                <Field
                  label="Ends"
                  value={form.endDate && `${form.endDate} at ${form.endTime}`}
                />
                <Field label="Expected attendance" value={form.attendance} />
                <Field label="Equipment requested" value={equipmentSummary(form.equipmentRequests)} />
                <Field label="Other accessibility notes" value={form.accessibility} />
                <Field label="Other requirements" value={form.specialRequirements} />
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
