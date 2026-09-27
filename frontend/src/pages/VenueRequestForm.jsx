import { useEffect, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import { eventErrorMessage, getAssignedEventRequest } from '../lib/eventRequests.js'
import {
  canRequestVenue,
  venueWarning,
  emptyVenueBookingForm,
  shortTime,
  submitVenueBooking,
  venueBookingErrorMessages,
  venueFit,
} from '../lib/venueBookings.js'
import { DAY_LABELS, listVenues, optionLabel, WEEK } from '../lib/venues.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  teal: '#0E7C74',
  amber: '#B5842B',
  rose: '#B25547',
  green: '#3F8F5F',
}

const INPUT_CLASS = 'csp-input w-full rounded-sm border px-3 py-2 font-ui text-sm'
const INPUT_STYLE = { borderColor: C.line, color: C.ink, backgroundColor: C.paper }

function Label({ htmlFor, children }) {
  return (
    <label htmlFor={htmlFor} className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
      {children}
    </label>
  )
}

function labels(codes) {
  return codes?.length ? codes.map(optionLabel).join(', ') : null
}

// The event's venue requirements, as the organiser gave them. Read-only: the
// Coordinator books against them rather than restating them.
function Requirements({ event }) {
  const rows = [
    ['Expected attendance', event.expected_attendance],
    ['Room layout', event.room_layout && optionLabel(event.room_layout)],
    ['Facilities', labels(event.required_facilities)],
    ['Accessibility', labels(event.required_accessibility)],
    ['Other requirements', event.special_requirements],
    ['Venue preference', event.venue],
  ]
  return (
    <section className="rounded-sm px-5 py-4 mb-8" style={{ backgroundColor: C.paperDim }} aria-labelledby="requirements-heading">
      <h2 id="requirements-heading" className="font-ui text-sm font-medium mb-2" style={{ color: C.ink }}>
        What the event needs
      </h2>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
        {rows.map(([term, value]) => (
          <div key={term} className="font-ui text-sm">
            <dt className="inline" style={{ color: C.inkFaint }}>{term}: </dt>
            <dd className="inline" style={{ color: C.ink }}>{value || 'None'}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function hoursSummary(operatingHours) {
  const byDay = Object.fromEntries(operatingHours.map((entry) => [entry.day, entry]))
  return WEEK.filter((day) => byDay[day])
    .map((day) => `${DAY_LABELS[day].slice(0, 3)} ${shortTime(byDay[day].open)}–${shortTime(byDay[day].close)}`)
    .join(', ')
}

function VenueOption({ venue, event, selected, onSelect }) {
  const problems = venueFit(event, venue)
  const fits = problems.length === 0
  return (
    <li style={{ borderColor: C.line }}>
      <label
        className="flex items-start gap-3 py-4 px-3 rounded-sm cursor-pointer"
        style={selected ? { backgroundColor: 'rgba(14,124,116,0.08)' } : undefined}
      >
        <input
          type="radio"
          name="venue"
          value={venue.id}
          checked={selected}
          onChange={() => onSelect(venue.id)}
          className="mt-1"
          aria-describedby={`venue-${venue.id}-fit`}
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-ui text-base font-medium" style={{ color: C.ink }}>{venue.name}</span>
            <span
              id={`venue-${venue.id}-fit`}
              className="inline-flex items-center gap-1.5 font-ui text-xs"
              style={{ color: fits ? C.green : C.amber }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: fits ? C.green : C.amber }}
                aria-hidden="true"
              />
              {fits ? 'Fits' : problems.join(' · ')}
            </span>
          </span>
          <span className="block font-ui text-sm mt-0.5" style={{ color: C.inkFaint }}>
            {venue.location} · Holds {venue.capacity} · {labels(venue.room_layouts)}
          </span>
          <span className="block font-ui text-xs mt-1" style={{ color: C.inkFaint }}>
            {labels(venue.facilities) || 'No listed facilities'}
            {venue.accessibility.length > 0 && ` · ${labels(venue.accessibility)}`}
          </span>
          <span className="block font-ui text-xs mt-0.5" style={{ color: C.inkFaint }}>
            Open {hoursSummary(venue.operating_hours)}
          </span>
        </span>
      </label>
    </li>
  )
}

// The venue_bookings service makes every suitability call; this page shows
// each venue against the event and sends the Coordinator's choice.
function RequestForm({ event, onSent }) {
  const [form, setForm] = useState(() => ({
    ...emptyVenueBookingForm(event.id),
    bookingDate: event.start_date ?? '',
    startTime: shortTime(event.start_time),
    endTime: shortTime(event.end_time),
  }))
  const [venues, setVenues] = useState({ status: 'loading', list: [] })
  const [sendState, setSendState] = useState({ status: 'idle', errors: [] })

  useEffect(() => {
    let active = true
    listVenues()
      .then((list) => { if (active) setVenues({ status: 'ready', list }) })
      .catch(() => { if (active) setVenues({ status: 'error', list: [] }) })
    return () => { active = false }
  }, [])

  const selectedVenue = venues.list.find((venue) => venue.id === form.venueId) ?? null
  const warning = venueWarning(event, selectedVenue)

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const missing = [
      !form.venueId && 'Choose a venue.',
      !form.bookingDate && 'Choose a date.',
      (!form.startTime || !form.endTime) && 'Enter a start and end time.',
    ].filter(Boolean)
    if (missing.length > 0) {
      setSendState({ status: 'idle', errors: missing })
      return
    }
    setSendState({ status: 'sending', errors: [] })
    try {
      await submitVenueBooking(form)
      onSent()
    } catch (error) {
      setSendState({ status: 'idle', errors: venueBookingErrorMessages(error) })
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <fieldset className="border-0 p-0 m-0 mb-8">
        <legend className="font-display text-xl mb-3" style={{ color: C.ink }}>Choose a venue</legend>
        {venues.status === 'loading' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading venues…</p>
        )}
        {venues.status === 'error' && (
          <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>
            We couldn&apos;t load the venue list. Reload the page to try again.
          </p>
        )}
        {venues.status === 'ready' && venues.list.length === 0 && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
            No venues have been added yet. Venue Staff add them from their dashboard.
          </p>
        )}
        {venues.status === 'ready' && venues.list.length > 0 && (
          <ul className="divide-y" aria-label="Venues">
            {venues.list.map((venue) => (
              <VenueOption
                key={venue.id}
                venue={venue}
                event={event}
                selected={form.venueId === venue.id}
                onSelect={(venueId) => update('venueId', venueId)}
              />
            ))}
          </ul>
        )}
      </fieldset>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div>
          <Label htmlFor="venue-request-date">Date</Label>
          <input
            id="venue-request-date"
            type="date"
            value={form.bookingDate}
            min={event.start_date}
            max={event.end_date}
            onChange={(e) => update('bookingDate', e.target.value)}
            className={INPUT_CLASS}
            style={INPUT_STYLE}
          />
        </div>
        <div>
          <Label htmlFor="venue-request-start">From</Label>
          <input
            id="venue-request-start"
            type="time"
            value={form.startTime}
            onChange={(e) => update('startTime', e.target.value)}
            className={INPUT_CLASS}
            style={INPUT_STYLE}
          />
        </div>
        <div>
          <Label htmlFor="venue-request-end">To</Label>
          <input
            id="venue-request-end"
            type="time"
            value={form.endTime}
            onChange={(e) => update('endTime', e.target.value)}
            className={INPUT_CLASS}
            style={INPUT_STYLE}
          />
        </div>
      </div>

      <div className="mb-8">
        <Label htmlFor="venue-request-notes">Notes for Venue Staff (optional)</Label>
        <textarea
          id="venue-request-notes"
          rows={3}
          value={form.notes}
          onChange={(e) => update('notes', e.target.value)}
          className={INPUT_CLASS}
          style={INPUT_STYLE}
          placeholder="Setup times, access, anything else they should know"
        />
      </div>

      {warning && (
        <p id="venue-warning" role="alert" className="font-ui text-sm mb-4" style={{ color: C.amber }}>
          ⚠ {warning}
        </p>
      )}

      {sendState.errors.length > 0 && (
        <div role="alert" className="font-ui text-sm mb-6" style={{ color: C.rose }}>
          <p className="font-medium mb-1">This request wasn&apos;t sent:</p>
          <ul className="list-disc pl-5 space-y-0.5">
            {sendState.errors.map((message) => <li key={message}>{message}</li>)}
          </ul>
        </div>
      )}

      <button
        type="submit"
        disabled={sendState.status === 'sending' || Boolean(warning)}
        aria-describedby={warning ? 'venue-warning' : undefined}
        className="csp-primary-btn px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
        style={{ backgroundColor: C.teal, color: C.paper }}
      >
        {sendState.status === 'sending' ? 'Sending…' : 'Send request'}
      </button>
    </form>
  )
}

export default function VenueRequestForm() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [state, setState] = useState({ status: 'loading', event: null, error: null })
  const eventPath = `/coordinator/events/${id}`

  useEffect(() => {
    let active = true
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

  function handleSent() {
    navigate(eventPath, { state: { notice: 'Venue request sent to Venue Staff.' } })
  }

  const { event } = state

  return (
    <div className="font-ui min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        .csp-input:focus-visible,
        .csp-primary-btn:focus-visible,
        input[type="radio"]:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
        @media (prefers-reduced-motion: reduce) {
          .csp-primary-btn:hover { transform: none; }
        }
      `}</style>
      <div className="w-full max-w-3xl mx-auto">
        <header className="flex items-center justify-between gap-6 mb-10">
          <Logo />
          <Link to={eventPath} className="inline-flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
            <ArrowLeft size={15} aria-hidden="true" />
            Back to the event
          </Link>
        </header>

        {state.status === 'loading' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading the event…</p>
        )}

        {state.status === 'error' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>{state.error}</p>
        )}

        {state.status === 'ready' && !canRequestVenue(event.status) && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
            A venue can only be requested for an event in planning.{' '}
            <Link to={eventPath} style={{ color: C.teal }}>Back to the event</Link>
          </p>
        )}

        {state.status === 'ready' && canRequestVenue(event.status) && (
          <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
            <h1 className="font-display text-3xl mb-2" style={{ color: C.ink }}>
              Request a venue
            </h1>
            <p className="font-ui text-sm leading-relaxed max-w-md mb-6" style={{ color: C.inkFaint }}>
              For {event.name}, {event.start_date} {shortTime(event.start_time)} to {event.end_date}{' '}
              {shortTime(event.end_time)}. The booking has to fit inside that window and the venue&apos;s
              opening hours.
            </p>
            <Requirements event={event} />
            <RequestForm event={event} onSent={handleSent} />
          </section>
        )}
      </div>
    </div>
  )
}
