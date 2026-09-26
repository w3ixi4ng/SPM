import { useEffect, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import { eventErrorMessage, getAssignedEventRequest } from '../lib/eventRequests.js'
import {
  canRequestVenue,
  emptyVenueBookingForm,
  shortTime,
  submitVenueBooking,
  venueBookingErrorMessages,
} from '../lib/venueBookings.js'
import { getVenueOptions, listVenues, optionLabel } from '../lib/venues.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
  rose: '#B25547',
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

function OptionChecklist({ legend, options, offered, selected, onToggle }) {
  return (
    <fieldset className="mb-6">
      <legend className="font-ui text-sm font-medium mb-2" style={{ color: C.ink }}>
        {legend}
      </legend>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
        {options.map((code) => {
          const missing = offered && !offered.includes(code)
          return (
            <label key={code} className="flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
              <input type="checkbox" checked={selected.includes(code)} onChange={() => onToggle(code)} />
              <span>
                {optionLabel(code)}
                {missing && (
                  <span className="text-xs" style={{ color: C.inkFaint }}> · not at this venue</span>
                )}
              </span>
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}

// The venue_bookings service makes every suitability call; this page only
// collects the request and shows what came back, so a Coordinator sees every
// problem at once.
function RequestForm({ event, onSent }) {
  const [form, setForm] = useState(() => ({
    ...emptyVenueBookingForm(event.id),
    bookingDate: event.start_date ?? '',
    startTime: shortTime(event.start_time),
    endTime: shortTime(event.end_time),
  }))
  const [catalogue, setCatalogue] = useState({ status: 'loading', venues: [], options: null })
  const [sendState, setSendState] = useState({ status: 'idle', errors: [] })

  useEffect(() => {
    let active = true
    Promise.all([listVenues(), getVenueOptions()])
      .then(([venues, options]) => {
        if (active) setCatalogue({ status: 'ready', venues, options })
      })
      .catch(() => {
        if (active) setCatalogue({ status: 'error', venues: [], options: null })
      })
    return () => {
      active = false
    }
  }, [])

  const venue = catalogue.venues.find((item) => item.id === form.venueId) ?? null

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  function toggle(field, code) {
    setForm((current) => ({
      ...current,
      [field]: current[field].includes(code)
        ? current[field].filter((item) => item !== code)
        : [...current[field], code],
    }))
  }

  function chooseVenue(venueId) {
    // A layout belongs to a venue; keep it only if the new venue offers it.
    const next = catalogue.venues.find((item) => item.id === venueId)
    setForm((current) => ({
      ...current,
      venueId,
      roomLayout: next?.room_layouts.includes(current.roomLayout) ? current.roomLayout : '',
    }))
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
      {catalogue.status === 'loading' && (
        <p className="font-ui text-sm mb-6" style={{ color: C.inkFaint }}>Loading venues…</p>
      )}
      {catalogue.status === 'error' && (
        <p role="alert" className="font-ui text-sm mb-6" style={{ color: C.rose }}>
          We couldn&apos;t load the venue list. Reload the page to try again.
        </p>
      )}

      <div className="mb-6">
        <Label htmlFor="venue-request-venue">Venue</Label>
        <select
          id="venue-request-venue"
          value={form.venueId}
          onChange={(e) => chooseVenue(e.target.value)}
          className={INPUT_CLASS}
          style={INPUT_STYLE}
          disabled={catalogue.status !== 'ready'}
        >
          <option value="">Choose a venue</option>
          {catalogue.venues.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} — holds {item.capacity}
            </option>
          ))}
        </select>
      </div>

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

      <div className="mb-6">
        <Label htmlFor="venue-request-layout">Room layout</Label>
        <select
          id="venue-request-layout"
          value={form.roomLayout}
          onChange={(e) => update('roomLayout', e.target.value)}
          className={INPUT_CLASS}
          style={INPUT_STYLE}
          disabled={!venue}
        >
          <option value="">No preference</option>
          {(venue?.room_layouts ?? []).map((code) => (
            <option key={code} value={code}>{optionLabel(code)}</option>
          ))}
        </select>
      </div>

      {catalogue.options && (
        <>
          <OptionChecklist
            legend="Facilities needed"
            options={catalogue.options.facilities}
            offered={venue?.facilities}
            selected={form.requiredFacilities}
            onToggle={(code) => toggle('requiredFacilities', code)}
          />
          {event.accessibility_requirements && (
            <p className="font-ui text-sm mb-2" style={{ color: C.inkFaint }}>
              The organiser asked for: {event.accessibility_requirements}
            </p>
          )}
          <OptionChecklist
            legend="Accessibility needed"
            options={catalogue.options.accessibility}
            offered={venue?.accessibility}
            selected={form.requiredAccessibility}
            onToggle={(code) => toggle('requiredAccessibility', code)}
          />
        </>
      )}

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
        .csp-primary-btn:focus-visible {
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
            <p className="font-ui text-sm leading-relaxed max-w-md mb-8" style={{ color: C.inkFaint }}>
              For {event.name}: {event.expected_attendance} expected, {event.start_date}{' '}
              {shortTime(event.start_time)} to {event.end_date} {shortTime(event.end_time)}. The booking has
              to fit inside that window and the venue&apos;s opening hours.
            </p>
            <RequestForm event={event} onSent={handleSent} />
          </section>
        )}
      </div>
    </div>
  )
}
