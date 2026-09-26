import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, Building2, Check, RotateCcw, X } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import { hasPermission, PERMISSIONS } from '../lib/access.js'
import {
  decideEventRequest,
  eventErrorMessage,
  eventResponseToForm,
  eventStatusMeta,
  getAssignedEventRequest,
} from '../lib/eventRequests.js'
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

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function OptionChecklist({ legend, options, offered, selected, onToggle }) {
  return (
    <fieldset className="mb-5">
      <legend className="font-ui text-sm font-medium mb-2" style={{ color: C.ink }}>
        {legend}
      </legend>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
        {options.map((code) => {
          const missing = offered && !offered.includes(code)
          return (
            <label key={code} className="flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
              <input
                type="checkbox"
                checked={selected.includes(code)}
                onChange={() => onToggle(code)}
              />
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

// The house slide-over (see AGENTS.md): right-anchored, traps focus, closes
// on Escape, the backdrop or X. The venue_bookings service makes every
// suitability call; this panel only collects the request and shows what
// came back, so a Coordinator sees every problem at once.
function VenueRequestPanel({ event, onClose, onSent }) {
  const panelRef = useRef(null)
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

  useEffect(() => {
    const timer = setTimeout(() => {
      panelRef.current?.querySelector(FOCUSABLE)?.focus()
    }, 0)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panelRef.current) return
      const items = Array.from(panelRef.current.querySelectorAll(FOCUSABLE))
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

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

  const inputClass = 'w-full rounded-sm border px-3 py-2 font-ui text-sm'
  const inputStyle = { borderColor: C.line, color: C.ink, backgroundColor: C.paper }

  return (
    <>
      <div
        className="fixed inset-0 z-40"
        style={{ backgroundColor: 'rgba(16,25,43,0.5)' }}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="venue-request-title"
        className="csp-slide-in fixed top-0 right-0 bottom-0 z-50 w-full max-w-md flex flex-col border-l"
        style={{ backgroundColor: C.paper, borderColor: C.line }}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b shrink-0" style={{ borderColor: C.line }}>
          <h2 id="venue-request-title" className="font-display text-xl" style={{ color: C.ink }}>
            Request a venue
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close venue request panel"
            className="rounded-sm p-2"
            style={{ color: C.inkFaint }}
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-6" noValidate>
          <p className="font-ui text-sm leading-relaxed mb-6" style={{ color: C.inkFaint }}>
            {event.expected_attendance} expected, {event.start_date} {shortTime(event.start_time)} to{' '}
            {event.end_date} {shortTime(event.end_time)}. The booking has to fit inside that window and
            the venue&apos;s opening hours.
          </p>

          {catalogue.status === 'loading' && (
            <p className="font-ui text-sm mb-5" style={{ color: C.inkFaint }}>Loading venues…</p>
          )}
          {catalogue.status === 'error' && (
            <p role="alert" className="font-ui text-sm mb-5" style={{ color: C.rose }}>
              We couldn&apos;t load the venue list. Close this panel and try again.
            </p>
          )}

          <div className="mb-5">
            <label htmlFor="venue-request-venue" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
              Venue
            </label>
            <select
              id="venue-request-venue"
              value={form.venueId}
              onChange={(e) => chooseVenue(e.target.value)}
              className={inputClass}
              style={inputStyle}
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

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
            <div>
              <label htmlFor="venue-request-date" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
                Date
              </label>
              <input
                id="venue-request-date"
                type="date"
                value={form.bookingDate}
                min={event.start_date}
                max={event.end_date}
                onChange={(e) => update('bookingDate', e.target.value)}
                className={inputClass}
                style={inputStyle}
              />
            </div>
            <div>
              <label htmlFor="venue-request-start" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
                From
              </label>
              <input
                id="venue-request-start"
                type="time"
                value={form.startTime}
                onChange={(e) => update('startTime', e.target.value)}
                className={inputClass}
                style={inputStyle}
              />
            </div>
            <div>
              <label htmlFor="venue-request-end" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
                To
              </label>
              <input
                id="venue-request-end"
                type="time"
                value={form.endTime}
                onChange={(e) => update('endTime', e.target.value)}
                className={inputClass}
                style={inputStyle}
              />
            </div>
          </div>

          <div className="mb-5">
            <label htmlFor="venue-request-layout" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
              Room layout
            </label>
            <select
              id="venue-request-layout"
              value={form.roomLayout}
              onChange={(e) => update('roomLayout', e.target.value)}
              className={inputClass}
              style={inputStyle}
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

          <div className="mb-6">
            <label htmlFor="venue-request-notes" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
              Notes for Venue Staff (optional)
            </label>
            <textarea
              id="venue-request-notes"
              rows={3}
              value={form.notes}
              onChange={(e) => update('notes', e.target.value)}
              className={inputClass}
              style={inputStyle}
              placeholder="Setup times, access, anything else they should know"
            />
          </div>

          {sendState.errors.length > 0 && (
            <div role="alert" className="font-ui text-sm mb-5" style={{ color: C.rose }}>
              <p className="font-medium mb-1">This request wasn&apos;t sent:</p>
              <ul className="list-disc pl-5 space-y-0.5">
                {sendState.errors.map((message) => <li key={message}>{message}</li>)}
              </ul>
            </div>
          )}

          <button
            type="submit"
            disabled={sendState.status === 'sending'}
            className="px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            {sendState.status === 'sending' ? 'Sending…' : 'Send request'}
          </button>
        </form>
      </div>
    </>
  )
}

export default function EventCoordinatorEventDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const [state, setState] = useState({ status: 'loading', event: null, error: null })
  const [panelOpen, setPanelOpen] = useState(false)
  const [notice, setNotice] = useState(null)
  const requestTriggerRef = useRef(null)

  const closePanel = useCallback(() => {
    setPanelOpen(false)
    requestTriggerRef.current?.focus()
  }, [])

  const handleSent = useCallback(() => {
    setNotice('Venue request sent to Venue Staff.')
    closePanel()
  }, [closePanel])

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
  const showVenueRequest = state.event
    && canRequestVenue(state.event.status)
    && hasPermission(user?.role, PERMISSIONS.REQUEST_VENUE_BOOKING)

  return (
    <div className="min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }
        .csp-slide-in { animation: slideIn 0.32s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .csp-slide-in { animation: none; }
        }
      `}</style>
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
                <button
                  ref={requestTriggerRef}
                  type="button"
                  onClick={() => {
                    setNotice(null)
                    setPanelOpen(true)
                  }}
                  className="inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5"
                  style={{ backgroundColor: C.teal, color: C.paper }}
                >
                  <Building2 size={16} aria-hidden="true" />
                  Request venue
                </button>
                <p role="status" className="font-ui text-sm" style={{ color: C.green }}>
                  {notice}
                </p>
              </div>
            )}

            <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
              <h1 className="font-display text-3xl mb-8" style={{ color: C.ink }}>
                {form.name || 'Untitled event request'}
              </h1>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <Field label="Purpose" value={form.purpose} />
                <Field label="Venue" value={form.venue} />
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
                <Field label="Accessibility requirements" value={form.accessibility} />
                <Field label="Other requirements" value={form.specialRequirements} />
              </div>
            </section>
          </>
        )}
      </div>

      {panelOpen && state.event && (
        <VenueRequestPanel event={state.event} onClose={closePanel} onSent={handleSent} />
      )}
    </div>
  )
}
