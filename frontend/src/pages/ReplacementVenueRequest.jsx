import { useEffect, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import { eventErrorMessage, getAssignedEventRequest } from '../lib/eventRequests.js'
import {
  bookingDateLabel,
  replacementErrorMessages,
  replacementSearchSummary,
  requestReplacementVenue,
  searchReplacementVenues,
  shortTime,
} from '../lib/venueBookings.js'
import { DAY_LABELS, optionLabel, WEEK } from '../lib/venues.js'

// S-78: a replacement for a booking an unavailable period affects. Its own
// screen, like S-36's request: the Coordinator compares venues to choose one.
// The date, times and requirements are the booking's and the event's, shown
// read-only -- the service offers only venues that are suitable and free
// then, and copies the event's details onto the request.

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  teal: '#0E7C74',
  rose: '#B25547',
  green: '#3F8F5F',
}

const INPUT_CLASS = 'csp-input w-full rounded-sm border px-3 py-2 font-ui text-sm'
const INPUT_STYLE = { borderColor: C.line, color: C.ink, backgroundColor: C.paper }

function labels(codes) {
  return codes?.length ? codes.map(optionLabel).join(', ') : null
}

function hoursSummary(operatingHours) {
  const byDay = Object.fromEntries(operatingHours.map((entry) => [entry.day, entry]))
  return WEEK.filter((day) => byDay[day])
    .map((day) => `${DAY_LABELS[day].slice(0, 3)} ${shortTime(byDay[day].open)}–${shortTime(byDay[day].close)}`)
    .join(', ')
}

function Requirements({ event, booking }) {
  const rows = [
    ['When', `${bookingDateLabel(booking.booking_date)} · ${shortTime(booking.start_time)}–${shortTime(booking.end_time)}`],
    ['Expected attendance', event.expected_attendance],
    ['Room layout', event.room_layout && optionLabel(event.room_layout)],
    ['Facilities', labels(event.required_facilities)],
    ['Accessibility', labels(event.required_accessibility)],
    ['Other requirements', event.special_requirements],
  ]
  return (
    <section className="rounded-sm px-5 py-4 mb-8" style={{ backgroundColor: C.paperDim }} aria-labelledby="requirements-heading">
      <h2 id="requirements-heading" className="font-ui text-sm font-medium mb-2" style={{ color: C.ink }}>
        What the replacement has to provide
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

function VenueOption({ venue, selected, onSelect }) {
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
        />
        <span className="min-w-0 flex-1">
          <span className="block font-ui text-base font-medium" style={{ color: C.ink }}>{venue.name}</span>
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

function ReplacementForm({ bookingId, search, onSent }) {
  const [venueId, setVenueId] = useState('')
  const [notes, setNotes] = useState('')
  const [sendState, setSendState] = useState({ status: 'idle', errors: [] })

  async function handleSubmit(e) {
    e.preventDefault()
    if (!venueId) {
      setSendState({ status: 'idle', errors: ['Choose a venue.'] })
      return
    }
    setSendState({ status: 'sending', errors: [] })
    try {
      await requestReplacementVenue(bookingId, { venueId, notes })
      onSent(search.venues.find((venue) => venue.id === venueId))
    } catch (error) {
      setSendState({ status: 'idle', errors: replacementErrorMessages(error) })
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <fieldset className="border-0 p-0 m-0 mb-8">
        <legend className="font-display text-xl mb-1" style={{ color: C.ink }}>Choose a venue</legend>
        <p className="rise-in font-ui text-sm mb-3 max-w-md" style={{ color: C.inkFaint }}>
          {replacementSearchSummary(search)}
        </p>
        {search.venues.length > 0 && (
          <ul className="divide-y" aria-label="Available venues">
            {search.venues.map((venue) => (
              <VenueOption key={venue.id} venue={venue} selected={venueId === venue.id} onSelect={setVenueId} />
            ))}
          </ul>
        )}
      </fieldset>

      {search.venues.length > 0 && (
        <>
          <div className="mb-8">
            <label htmlFor="replacement-notes" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
              Notes for Venue Staff (optional)
            </label>
            <textarea
              id="replacement-notes"
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className={INPUT_CLASS}
              style={INPUT_STYLE}
              placeholder="Setup times, access, anything else they should know"
            />
          </div>

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
            disabled={sendState.status === 'sending'}
            className="csp-primary-btn px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            {sendState.status === 'sending' ? 'Sending…' : 'Send replacement request'}
          </button>
        </>
      )}
    </form>
  )
}

export default function ReplacementVenueRequest() {
  const { id, bookingId } = useParams()
  const navigate = useNavigate()
  const [state, setState] = useState({ status: 'loading', event: null, search: null, errors: [] })
  const eventPath = `/coordinator/events/${id}`

  useEffect(() => {
    let active = true
    Promise.all([getAssignedEventRequest(id), searchReplacementVenues(bookingId)])
      .then(([event, search]) => {
        if (active) setState({ status: 'ready', event, search, errors: [] })
      })
      .catch((error) => {
        if (!active) return
        // The event lookup fails with its own words; the search with S-78's.
        const errors = error.status === 404 && error.message === 'Event not found'
          ? [eventErrorMessage(error)]
          : replacementErrorMessages(error)
        setState({ status: 'error', event: null, search: null, errors })
      })
    return () => {
      active = false
    }
  }, [id, bookingId])

  function handleSent(venue) {
    navigate(eventPath, { state: { notice: `Replacement request sent to ${venue?.name ?? 'Venue Staff'}.` } })
  }

  const { event, search } = state

  return (
    <div className="font-ui min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        .csp-input:focus-visible,
        .csp-primary-btn:focus-visible,
        input[type="radio"]:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
        @keyframes riseIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
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
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Finding venues that can take this event…</p>
        )}

        {state.status === 'error' && (
          <div role="alert" className="font-ui text-sm space-y-1" style={{ color: C.inkFaint }}>
            {state.errors.map((message) => <p key={message}>{message}</p>)}
            <Link to={eventPath} style={{ color: C.teal }}>Back to the event</Link>
          </div>
        )}

        {state.status === 'ready' && (
          <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
            <h1 className="font-display text-3xl mb-2" style={{ color: C.ink }}>
              Find a replacement venue
            </h1>
            <p className="font-ui text-sm leading-relaxed max-w-md mb-6" style={{ color: C.inkFaint }}>
              For {event.name}, instead of {search.booking.venue_name}. Every venue below is free then and meets
              the event&apos;s requirements. Your current booking stays in place until Venue Staff approve the
              replacement.
            </p>
            <Requirements event={event} booking={search.booking} />
            <ReplacementForm bookingId={bookingId} search={search} onSent={handleSent} />
          </section>
        )}
      </div>
    </div>
  )
}
