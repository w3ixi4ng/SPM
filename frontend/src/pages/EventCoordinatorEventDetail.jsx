import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, Building2, Check, Headphones, RotateCcw, X } from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import EquipmentRequirementsPanel from '../components/EquipmentRequirementsPanel.jsx'
import EventReadinessPanel from '../components/EventReadinessPanel.jsx'
import SafetySubmissionPanel from '../components/SafetySubmissionPanel.jsx'
import {
  buildSubmissionReadiness,
  describeSignoff,
} from '../lib/safetySubmission.js'
import { equipmentPreparationLabel } from '../lib/technicalSupportAssignments.js'
import Logo from '../components/Logo.jsx'
import ReassignmentRequestPanel from '../components/ReassignmentRequestPanel.jsx'
import { hasPermission, PERMISSIONS } from '../lib/access.js'
import { optionLabel } from '../lib/venues.js'
import {
  canDecideCancellation,
  cancellationApprovalSummary,
  cancellationApprovedNotice,
  cancellationDecisionErrorMessage,
  cancellationRequestedLabel,
  decideCancellation,
  decideEventRequest,
  eventErrorMessage,
  eventResponseToForm,
  eventStatusMeta,
  getAssignedEventRequest,
  validateDeclineReason,
  previewAssignedEventInformation,
  updateAssignedEventInformation,
} from '../lib/eventRequests.js'
import {
  alternativeArrangementsNotice,
  bookingClashMessage,
  bookingDateLabel,
  bookingStatusMeta,
  canRequestVenue,
  listVenueBookingsForEvent,
  replacementErrorMessages,
  replacementPath,
  replacementState,
  resolveAlternativeArrangements,
  RESOLUTION_NOTE_MAX,
  shortTime,
  validateResolutionNote,
  venueRequestLinkLabel,
  cancelVenueBooking,
  cancelVenueBookingPrompt,
  canChangeVenueBooking,
  VENUE_BOOKING_CANCELLED,
  venueBookingChangeErrorMessage,
} from '../lib/venueBookings.js'
import {
  canRequestTechnicalSupport,
  getTechnicalSupportAssignment,
  requestTechnicalSupportAssignment,
  technicalSupportAssignmentErrorMessage,
} from '../lib/technicalSupportAssignments.js'
import {
  getReturnedSafetyReview,
  resubmitSafetyReview,
  safetyReturnErrorMessage,
} from '../lib/safetyChecks.js'

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

const EDITABLE_STATUSES = new Set(['planning', 'confirmed', 'preparation'])
const REASSIGNABLE_STATUSES = new Set(['submitted', 'planning', 'pending_safety_check', 'confirmed', 'returned'])
const FIELD_LABELS = {
  start_date: 'start date', start_time: 'start time', end_date: 'end date', end_time: 'end time',
  expected_attendance: 'expected attendance', venue: 'venue preference',
  special_requirements: 'other requirements', room_layout: 'room layout',
  required_facilities: 'required facilities', required_accessibility: 'accessibility requirements',
}

function EventInformationEditor({ event, onSaved }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(() => eventResponseToForm(event))
  const [impact, setImpact] = useState(null)
  const [state, setState] = useState({ status: 'idle', error: null, notice: null })

  useEffect(() => {
    setForm(eventResponseToForm(event))
    setImpact(null)
    setEditing(false)
  }, [event.id, event.edit_version])

  const set = (field) => (e) => setForm((current) => ({ ...current, [field]: e.target.value }))
  const setList = (field) => (e) => setForm((current) => ({
    ...current,
    [field]: e.target.value.split(',').map((value) => value.trim()).filter(Boolean),
  }))

  async function save(acceptImpact = false) {
    setState({ status: 'saving', error: null, notice: null })
    try {
      const updated = await updateAssignedEventInformation(event.id, form, event, acceptImpact)
      setImpact(null)
      setState({ status: 'idle', error: null, notice: 'Event information saved.' })
      onSaved(updated)
    } catch (error) {
      setState({ status: 'idle', error: eventErrorMessage(error), notice: null })
    }
  }

  async function review(event_) {
    event_.preventDefault()
    setState({ status: 'checking', error: null, notice: null })
    try {
      const result = await previewAssignedEventInformation(event.id, form, event)
      if (result.changed_fields.length === 0) {
        setState({ status: 'idle', error: null, notice: 'There are no changes to save.' })
      } else if (result.requires_impact_acceptance) {
        setImpact(result)
        setState({ status: 'idle', error: null, notice: null })
      } else {
        await save(false)
      }
    } catch (error) {
      setState({ status: 'idle', error: eventErrorMessage(error), notice: null })
    }
  }

  if (!EDITABLE_STATUSES.has(event.status)) return null
  if (!editing) return (
    <div className="mt-6 flex flex-wrap items-center gap-3">
      <button type="button" onClick={() => setEditing(true)} className="px-4 py-2 border rounded-sm font-ui text-sm" style={{ borderColor: C.teal, color: C.teal }}>
        Edit event information
      </button>
      {state.notice && <p role="status" className="font-ui text-sm" style={{ color: C.green }}>{state.notice}</p>}
      {state.error && <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>{state.error}</p>}
    </div>
  )

  const inputClass = 'w-full border rounded-sm px-3 py-2 font-ui text-sm bg-white'
  return (
    <form onSubmit={review} className="mt-8 border-t pt-6" style={{ borderColor: C.line }}>
      <h2 className="font-display text-xl mb-1" style={{ color: C.ink }}>Edit event information</h2>
      <p className="font-ui text-sm mb-5" style={{ color: C.inkFaint }}>Material changes are reviewed before they are saved.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {[
          ['name', 'Event name', 'text'], ['purpose', 'Description', 'text'],
          ['contactName', 'Contact name', 'text'], ['contactEmail', 'Contact email', 'email'],
          ['contactPhone', 'Contact phone', 'tel'], ['attendance', 'Expected attendance', 'number'],
          ['startDate', 'Start date', 'date'], ['startTime', 'Start time', 'time'],
          ['endDate', 'End date', 'date'], ['endTime', 'End time', 'time'],
          ['venue', 'Venue preference', 'text'], ['roomLayout', 'Room layout code', 'text'],
        ].map(([field, label, type]) => (
          <label key={field} className="font-ui text-sm" style={{ color: C.ink }}>
            {label}
            <input className={inputClass} style={{ borderColor: C.line }} type={type} min={type === 'number' ? '1' : undefined} value={form[field]} onChange={set(field)} />
          </label>
        ))}
        <label className="font-ui text-sm sm:col-span-2" style={{ color: C.ink }}>
          Required facilities (comma-separated codes)
          <input className={inputClass} style={{ borderColor: C.line }} value={form.requiredFacilities.join(', ')} onChange={setList('requiredFacilities')} />
        </label>
        <label className="font-ui text-sm sm:col-span-2" style={{ color: C.ink }}>
          Accessibility requirements (comma-separated codes)
          <input className={inputClass} style={{ borderColor: C.line }} value={form.requiredAccessibility.join(', ')} onChange={setList('requiredAccessibility')} />
        </label>
        <label className="font-ui text-sm sm:col-span-2" style={{ color: C.ink }}>
          Other requirements
          <textarea className={inputClass} style={{ borderColor: C.line }} value={form.specialRequirements} onChange={set('specialRequirements')} />
        </label>
        <label className="font-ui text-sm sm:col-span-2" style={{ color: C.ink }}>
          Internal notes (Coordinator only)
          <textarea className={inputClass} style={{ borderColor: C.line }} value={form.internalNotes} onChange={set('internalNotes')} />
        </label>
      </div>
      {impact && (
        <div role="alertdialog" aria-labelledby="impact-heading" className="mt-6 border rounded-sm p-5" style={{ borderColor: C.amber, backgroundColor: `${C.amber}0D` }}>
          <h3 id="impact-heading" className="font-display text-lg" style={{ color: C.ink }}>Review significant changes</h3>
          <p className="font-ui text-sm mt-2" style={{ color: C.ink }}>These changes may affect existing arrangements: {impact.significant_fields.map((field) => FIELD_LABELS[field] || field).join(', ')}.</p>
          {['confirmed', 'preparation'].includes(event.status) && <p className="font-ui text-sm mt-2" style={{ color: C.ink }}>Accepting returns the event to Planning and requires a fresh Operational Safety Check. Existing venue and equipment sign-offs remain in place.</p>}
          <div className="flex gap-3 mt-4">
            <button type="button" onClick={() => setImpact(null)} className="px-4 py-2 border rounded-sm font-ui text-sm" style={{ borderColor: C.line }}>Go back</button>
            <button type="button" onClick={() => save(true)} className="px-4 py-2 rounded-sm font-ui text-sm text-white" style={{ backgroundColor: C.amber }}>Accept and save</button>
          </div>
        </div>
      )}
      {state.error && <p role="alert" className="font-ui text-sm mt-4" style={{ color: C.rose }}>{state.error}</p>}
      {state.notice && <p role="status" className="font-ui text-sm mt-4" style={{ color: C.green }}>{state.notice}</p>}
      <div className="flex gap-3 mt-6">
        <button type="button" onClick={() => { setEditing(false); setImpact(null); setForm(eventResponseToForm(event)) }} className="px-4 py-2 border rounded-sm font-ui text-sm" style={{ borderColor: C.line }}>Cancel</button>
        <button type="submit" disabled={state.status !== 'idle'} className="px-4 py-2 rounded-sm font-ui text-sm text-white" style={{ backgroundColor: C.teal }}>{state.status === 'idle' ? 'Review changes' : 'Checking…'}</button>
      </div>
    </form>
  )
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

// S-78: the Coordinator says what they arranged instead of a replacement
// venue. A slide-over: one field, and the event page stays behind it.
function ResolvePanel({ booking, onClose, onResolved }) {
  const [note, setNote] = useState('')
  const [state, setState] = useState({ saving: false, errors: [] })
  const panelRef = useRef(null)

  useEffect(() => {
    panelRef.current?.querySelector('textarea')?.focus()
  }, [])

  useEffect(() => {
    const panel = panelRef.current

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panel) return
      // Keep focus inside the panel while it is open.
      const focusable = [...panel.querySelectorAll('button, textarea')].filter((el) => !el.disabled)
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
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

  async function handleSubmit(e) {
    e.preventDefault()
    const problem = validateResolutionNote(note)
    if (problem) {
      setState({ saving: false, errors: [problem] })
      return
    }
    setState({ saving: true, errors: [] })
    try {
      await resolveAlternativeArrangements(booking.id, note)
      onResolved()
    } catch (error) {
      setState({ saving: false, errors: replacementErrorMessages(error) })
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ backgroundColor: 'rgba(16,25,43,0.5)' }} onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="resolve-panel-title"
        className="csp-panel-in fixed top-0 right-0 z-50 h-full w-full max-w-md overflow-y-auto border-l p-7"
        style={{ backgroundColor: C.paper, borderColor: C.line }}
      >
        <div className="flex items-start justify-between gap-4 mb-2">
          <h2 id="resolve-panel-title" className="font-display text-2xl" style={{ color: C.ink }}>
            Mark resolved
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="csp-focus rounded-sm p-1" style={{ color: C.inkFaint }}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <p className="font-ui text-sm leading-relaxed mb-6" style={{ color: C.inkFaint }}>
          {booking.venue_name}, {bookingDateLabel(booking.booking_date)} {shortTime(booking.start_time)}–{shortTime(booking.end_time)}.
          The booking stays as it is. It is flagged again only if the venue is marked unavailable again.
        </p>
        <form onSubmit={handleSubmit} noValidate>
          <label htmlFor="resolution-note" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
            What have you arranged instead?
          </label>
          <textarea
            id="resolution-note"
            rows={4}
            maxLength={RESOLUTION_NOTE_MAX}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="csp-focus w-full rounded-sm border px-3 py-2 font-ui text-sm mb-4"
            style={{ borderColor: C.line, color: C.ink, backgroundColor: C.paper }}
            placeholder="For example: moved online for this session"
          />
          {state.errors.length > 0 && (
            <div role="alert" className="font-ui text-sm mb-4" style={{ color: C.rose }}>
              {state.errors.map((message) => <p key={message}>{message}</p>)}
            </div>
          )}
          <button
            type="submit"
            disabled={state.saving}
            className="csp-focus px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            {state.saving ? 'Saving…' : 'Mark resolved'}
          </button>
        </form>
      </div>
    </>
  )
}

// What this Coordinator has already asked for, so a reload never leaves them
// guessing whether a request went out.
// S-80: confirm before one booking is cancelled. The house slide-over.
function CancelBookingPanel({ booking, onClose, onCancelled }) {
  const [error, setError] = useState(null)
  const [sending, setSending] = useState(false)
  const panelRef = useRef(null)

  useEffect(() => {
    const panel = panelRef.current
    panel?.querySelector('button:not([aria-label="Close"])')?.focus()
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panel) return
      // Keep focus inside the panel while it is open.
      const focusable = [...panel.querySelectorAll('button')].filter((el) => !el.disabled)
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
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

  async function cancel() {
    setSending(true)
    setError(null)
    try {
      await cancelVenueBooking(booking.id)
      onCancelled()
    } catch (failure) {
      setError(venueBookingChangeErrorMessage(failure))
      setSending(false)
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ backgroundColor: 'rgba(16,25,43,0.5)' }} onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cancel-booking-title"
        className="csp-panel-in fixed top-0 right-0 z-50 h-full w-full max-w-md overflow-y-auto border-l p-7 font-ui"
        style={{ backgroundColor: C.paper, borderColor: C.line }}
      >
        <div className="flex items-start justify-between gap-4 mb-2">
          <h2 id="cancel-booking-title" className="font-display text-2xl" style={{ color: C.ink }}>
            Cancel venue booking
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-sm p-1" style={{ color: C.inkFaint }}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <p className="text-sm leading-relaxed mb-6" style={{ color: C.inkFaint }}>
          {cancelVenueBookingPrompt(booking)}
        </p>
        {error && <p role="alert" className="text-sm mb-4" style={{ color: C.rose }}>{error}</p>}
        <div className="grid gap-3">
          <button
            type="button"
            onClick={cancel}
            disabled={sending}
            className="px-5 py-3 rounded-sm font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            {sending ? 'Cancelling…' : 'Cancel booking'}
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={sending}
            className="px-5 py-3 rounded-sm font-medium text-sm border transition-colors duration-200"
            style={{ borderColor: C.ink, color: C.ink }}
          >
            Keep booking
          </button>
        </div>
      </div>
    </>
  )
}

function VenueRequests({ eventId, eventStatus, canRequest, notice }) {
  const [state, setState] = useState({ status: 'loading', bookings: [] })
  const [resolving, setResolving] = useState(null)
  const [resolvedNotice, setResolvedNotice] = useState(null)
  const triggerRef = useRef(null)
  // S-80: the booking being cancelled, and what the last cancel did.
  const [cancelling, setCancelling] = useState(null)
  const [cancelNotice, setCancelNotice] = useState(null)
  const cancelTriggerRef = useRef(null)

  const load = useCallback(() => listVenueBookingsForEvent(eventId).then(
    (bookings) => setState({ status: 'ready', bookings }),
    () => setState({ status: 'error', bookings: [] }),
  ), [eventId])

  useEffect(() => {
    load()
  }, [load])

  function openResolve(booking, trigger) {
    triggerRef.current = trigger
    setResolving(booking)
  }

  function closeResolve() {
    setResolving(null)
    triggerRef.current?.focus()
  }

  async function handleResolved() {
    setResolvedNotice(`${resolving.venue_name} booking marked resolved.`)
    setCancelNotice(null)
    setResolving(null)
    await load()
  }

  return (
    <section aria-labelledby="venue-requests-heading">
      <div className="flex items-center gap-2 mb-2">
        <Building2 size={18} aria-hidden="true" style={{ color: C.teal }} />
        <h2 id="venue-requests-heading" className="font-display text-2xl" style={{ color: C.ink }}>
          Venue requests
        </h2>
      </div>
      <p className="font-ui text-sm mb-6" style={{ color: C.inkFaint }}>
        Ask Venue Staff to book each venue this event needs, and follow each request&apos;s decision here.
      </p>
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
            const unavailable = alternativeArrangementsNotice(booking)
            const replacing = replacementState(booking, state.bookings)
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
                <div className="flex items-center gap-4 shrink-0">
                  <span className="inline-flex items-center gap-1.5 font-ui text-xs" style={{ color }}>
                    <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} aria-hidden="true" />
                    {label}
                  </span>
                  {canChangeVenueBooking(booking, eventStatus) && (
                    // S-80: this booking only; the others are untouched.
                    <>
                      <Link
                        to={`/coordinator/events/${eventId}/venue-bookings/${booking.id}/change`}
                        aria-label={`Change ${booking.venue_name} booking`}
                        className="font-ui text-sm underline transition-colors duration-200"
                        style={{ color: C.teal }}
                      >
                        Change
                      </Link>
                      <button
                        type="button"
                        aria-label={`Cancel ${booking.venue_name} booking`}
                        onClick={(e) => {
                          cancelTriggerRef.current = e.currentTarget
                          setCancelling(booking)
                        }}
                        className="font-ui text-sm underline transition-colors duration-200"
                        style={{ color: C.ink }}
                      >
                        Cancel
                      </button>
                    </>
                  )}
                </div>
                {booking.status !== 'pending' && (
                  <div className="w-full font-ui text-sm space-y-1" style={{ color: C.ink }}>
                    {booking.decision_reason && <p className="whitespace-pre-wrap">Reason: {booking.decision_reason}</p>}
                    {booking.decision_alternative && <p className="whitespace-pre-wrap">Alternative: {booking.decision_alternative}</p>}
                    {booking.decided_at && <p>Decided {new Date(booking.decided_at).toLocaleString()}</p>}
                  </div>
                )}
                {bookingClashMessage(booking) && (
                  // S-75: flagged for the assigned Coordinator; the booking itself is unchanged.
                  <p role="alert" className="w-full font-ui text-sm" style={{ color: C.rose }}>
                    {bookingClashMessage(booking)}
                  </p>
                )}
                {unavailable && (
                  // S-77: the venue is unavailable during this booking. The
                  // booking and the event are unchanged until people act.
                  <div role="alert" className="w-full font-ui text-sm">
                    <p className="inline-flex items-center gap-1.5 font-medium" style={{ color: unavailable.color }}>
                      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: unavailable.color }} aria-hidden="true" />
                      {unavailable.label}
                    </p>
                    <p className="mt-0.5" style={{ color: C.ink }}>{unavailable.detail}</p>
                  </div>
                )}
                {(replacing.label || replacing.actions.length > 0) && (
                  // S-78: replace the venue or resolve the flag, and where that stands.
                  <div className="w-full font-ui text-sm">
                    {replacing.label && <p style={{ color: C.inkFaint }}>{replacing.label}</p>}
                    {replacing.actions.length > 0 && (
                      <div className="flex flex-wrap items-center gap-3 mt-2">
                        {replacing.actions.includes('replace') && (
                          <Link
                            to={replacementPath(eventId, booking.id)}
                            className="csp-focus px-4 py-2 rounded-sm border font-medium transition-colors duration-200"
                            style={{ borderColor: C.ink, color: C.ink }}
                          >
                            Find a replacement venue
                          </Link>
                        )}
                        {replacing.actions.includes('resolve') && (
                          <button
                            type="button"
                            onClick={(e) => openResolve(booking, e.currentTarget)}
                            className="csp-focus px-4 py-2 rounded-sm border font-medium transition-colors duration-200"
                            style={{ borderColor: C.line, color: C.ink }}
                          >
                            Mark resolved
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-4 mt-6">
        {canRequest && (
          <Link
            to={`/coordinator/events/${eventId}/request-venue`}
            className="inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            <Building2 size={16} aria-hidden="true" />
            {venueRequestLinkLabel(state.bookings)}
          </Link>
        )}
        <p role="status" className="font-ui text-sm" style={{ color: C.green }}>
          {cancelNotice ?? resolvedNotice ?? notice}
        </p>
      </div>
      {resolving && <ResolvePanel booking={resolving} onClose={closeResolve} onResolved={handleResolved} />}
      {cancelling && (
        <CancelBookingPanel
          booking={cancelling}
          onClose={() => {
            setCancelling(null)
            cancelTriggerRef.current?.focus()
          }}
          onCancelled={async () => {
            setCancelling(null)
            setCancelNotice(VENUE_BOOKING_CANCELLED)
            setResolvedNotice(null)
            await load()
          }}
        />
      )}
    </section>
  )
}

// S-61: the Organiser's cancellation request and the assigned Coordinator's
// decision. Approving or declining happens in the house slide-over, and
// nothing is sent until its confirm step.
function CancellationReview({ event, notice, onDecide }) {
  if (!event.cancellation_requested_at) return null
  const pending = canDecideCancellation(event)

  return (
    <section aria-labelledby="cancellation-heading" className="border rounded-sm p-7 sm:p-8 mb-8" style={{ borderColor: C.line }}>
      <h2 id="cancellation-heading" className="font-display text-2xl mb-2" style={{ color: C.ink }}>
        Cancellation request
      </h2>
      {notice && (
        <p role="status" className="font-ui text-sm mb-4" style={{ color: C.green }}>{notice}</p>
      )}
      <p className="font-ui text-sm flex items-center gap-2" style={{ color: C.ink }}>
        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: pending ? C.amber : C.inkFaint }} aria-hidden="true" />
        {cancellationRequestedLabel(event)}
      </p>
      <p className="font-ui text-sm mt-2 whitespace-pre-wrap max-w-md" style={{ color: C.ink }}>
        <span style={{ color: C.inkFaint }}>Organiser&apos;s reason: </span>
        {event.cancellation_reason}
      </p>
      {event.cancellation_decision === 'approved' && (
        <p className="font-ui text-sm mt-3" style={{ color: C.inkFaint }}>
          You approved this request on {new Date(event.cancellation_decided_at).toLocaleString()}. The event is cancelled.
        </p>
      )}
      {event.cancellation_decision === 'declined' && (
        <p className="font-ui text-sm mt-3 whitespace-pre-wrap" style={{ color: C.inkFaint }}>
          You declined this request on {new Date(event.cancellation_decided_at).toLocaleString()}: {event.cancellation_decision_reason}
        </p>
      )}
      {pending && (
        <div className="flex flex-wrap gap-3 mt-6">
          <button
            type="button"
            onClick={(e) => onDecide('approved', e.currentTarget)}
            className="px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            Approve cancellation
          </button>
          <button
            type="button"
            onClick={(e) => onDecide('declined', e.currentTarget)}
            className="px-5 py-3 rounded-sm font-ui font-medium text-sm border transition-colors duration-200"
            style={{ borderColor: C.ink, color: C.ink }}
          >
            Decline
          </button>
        </div>
      )}
    </section>
  )
}

function CancellationDecisionPanel({ eventId, decision, onClose, onDecided }) {
  const [bookingCount, setBookingCount] = useState(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState(null)
  const [sending, setSending] = useState(false)
  const panelRef = useRef(null)
  const approving = decision === 'approved'

  useEffect(() => {
    if (!approving) return undefined
    let active = true
    // What approving will release, so the Coordinator confirms knowingly.
    listVenueBookingsForEvent(eventId)
      .then((bookings) => { if (active) setBookingCount(bookings.length) })
      .catch(() => { if (active) setBookingCount(-1) })
    return () => { active = false }
  }, [approving, eventId])

  useEffect(() => {
    const panel = panelRef.current
    panel?.querySelector('textarea, button:not([aria-label="Close"])')?.focus()
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panel) return
      // Keep focus inside the panel while it is open.
      const focusable = [...panel.querySelectorAll('button, textarea')].filter((el) => !el.disabled)
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
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

  async function send(e) {
    e.preventDefault()
    if (!approving) {
      const problem = validateDeclineReason(reason)
      if (problem) {
        setError(problem)
        return
      }
    }
    setSending(true)
    setError(null)
    try {
      onDecided(await decideCancellation(eventId, { decision, reason }))
    } catch (failure) {
      setError(cancellationDecisionErrorMessage(failure))
      setSending(false)
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ backgroundColor: 'rgba(16,25,43,0.5)' }} onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cancellation-decision-title"
        className="csp-panel-in fixed top-0 right-0 z-50 h-full w-full max-w-md overflow-y-auto border-l p-7 font-ui"
        style={{ backgroundColor: C.paper, borderColor: C.line }}
      >
        <div className="flex items-start justify-between gap-4 mb-2">
          <h2 id="cancellation-decision-title" className="font-display text-2xl" style={{ color: C.ink }}>
            {approving ? 'Cancel this event?' : 'Decline cancellation'}
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-sm p-1" style={{ color: C.inkFaint }}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <form onSubmit={send} noValidate className="grid gap-4">
          {approving ? (
            <p className="text-sm leading-relaxed" style={{ color: C.inkFaint }}>
              {bookingCount === null && 'Checking the venue bookings…'}
              {bookingCount === -1 && "We couldn't check the venue bookings. Every booking for this event will be removed. Equipment reserved for this event is freed."}
              {bookingCount !== null && bookingCount >= 0 && cancellationApprovalSummary(bookingCount)}
              {' '}This can&apos;t be undone.
            </p>
          ) : (
            <>
              <p className="text-sm leading-relaxed" style={{ color: C.inkFaint }}>
                The event stays as it is, and the Organiser sees your reason.
              </p>
              <div>
                <label htmlFor="decline-reason" className="block text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                  Why can&apos;t this event be cancelled?
                </label>
                <textarea
                  id="decline-reason"
                  rows={5}
                  maxLength={1000}
                  value={reason}
                  onChange={(e) => { setReason(e.target.value); setError(null) }}
                  aria-invalid={Boolean(error)}
                  className="w-full rounded-sm border px-4 py-3 text-sm"
                  style={{ borderColor: C.line, color: C.ink, backgroundColor: C.paper }}
                />
              </div>
            </>
          )}
          {error && <p role="alert" className="text-sm" style={{ color: C.rose }}>{error}</p>}
          <button
            type="submit"
            disabled={sending || (approving && bookingCount === null)}
            className="px-5 py-3 rounded-sm font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            {sending ? 'Saving…' : approving ? 'Cancel event' : 'Decline request'}
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={sending}
            className="px-5 py-3 rounded-sm font-medium text-sm border transition-colors duration-200"
            style={{ borderColor: C.ink, color: C.ink }}
          >
            {approving ? 'Keep event' : 'Back'}
          </button>
        </form>
      </div>
    </>
  )
}

function TechnicalSupportAssignment({ eventId, eventStatus }) {
  const [state, setState] = useState({ status: 'loading', assignment: null, error: null })
  const [details, setDetails] = useState('')

  useEffect(() => {
    let active = true
    getTechnicalSupportAssignment(eventId)
      .then((assignment) => {
        if (!active) return
        setDetails(assignment.support_details ?? '')
        setState({ status: 'ready', assignment, error: null })
      })
      .catch((error) => {
        if (active) setState({ status: 'error', assignment: null, error: technicalSupportAssignmentErrorMessage(error) })
      })
    return () => {
      active = false
    }
  }, [eventId])

  async function handleSubmit(event) {
    event.preventDefault()
    setState((current) => ({ ...current, status: 'saving', error: null }))
    try {
      const assignment = await requestTechnicalSupportAssignment(eventId, details)
      setDetails(assignment.support_details ?? '')
      setState({ status: 'ready', assignment, error: null })
    } catch (error) {
      setState((current) => ({
        ...current,
        status: 'ready',
        error: technicalSupportAssignmentErrorMessage(error),
      }))
    }
  }

  const assignment = state.assignment
  const editable = canRequestTechnicalSupport(eventStatus)

  return (
    <section className="border-t pt-8 mt-8" style={{ borderColor: C.line }} aria-labelledby="technical-support-heading">
      <div className="flex items-center gap-2 mb-2">
        <Headphones size={18} aria-hidden="true" style={{ color: C.teal }} />
        <h2 id="technical-support-heading" className="font-display text-2xl" style={{ color: C.ink }}>
          Technical support
        </h2>
      </div>
      {state.status === 'loading' && <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading Technical Support assignment…</p>}
      {state.status === 'error' && <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>{state.error}</p>}
      {assignment && (
        <>
          {assignment.assignment_state === 'assigned' && (
            <div className="mb-5">
              <p role="status" className="font-ui text-sm font-medium" style={{ color: C.green }}>Technical Support assigned</p>
              <p className="font-ui text-sm mt-1" style={{ color: C.ink }}>
                {assignment.assigned_staff?.name || assignment.assigned_technical_support_id}
                {assignment.assigned_staff?.email && ` · ${assignment.assigned_staff.email}`}
              </p>
            </div>
          )}
          {assignment.assignment_state === 'unassigned' && (
            <p role="status" className="font-ui text-sm mb-5" style={{ color: C.amber }}>{assignment.message}</p>
          )}
          {assignment.assignment_state === 'not_required' && (
            <p className="font-ui text-sm mb-5" style={{ color: C.inkFaint }}>Technical Support has not been requested for this event.</p>
          )}
          {editable && (
            <form onSubmit={handleSubmit}>
              <label htmlFor="technical-support-details" className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
                Support details (optional)
              </label>
              <textarea
                id="technical-support-details"
                value={details}
                onChange={(event) => setDetails(event.target.value)}
                rows={3}
                className="w-full rounded-sm border px-3 py-2 font-ui text-sm mb-4"
                style={{ borderColor: C.line, color: C.ink }}
                placeholder="Describe the on-site support needed"
              />
              {state.error && <p role="alert" className="font-ui text-sm mb-4" style={{ color: C.rose }}>{state.error}</p>}
              <button
                type="submit"
                disabled={state.status === 'saving'}
                className="px-5 py-3 rounded-sm font-ui font-medium text-sm disabled:opacity-60"
                style={{ backgroundColor: C.teal, color: C.paper }}
              >
                {state.status === 'saving'
                  ? 'Saving…'
                  : assignment.assignment_state === 'not_required'
                    ? 'Request technical support'
                    : 'Update support notes'}
              </button>
            </form>
          )}
        </>
      )}
    </section>
  )
}

function SafetyReturnPanel({ event, onResubmitted }) {
  const [state, setState] = useState({ status: 'loading', detail: null, error: null })
  const [submit, setSubmit] = useState({ status: 'idle', error: null, outstanding: [] })

  useEffect(() => {
    let active = true
    getReturnedSafetyReview(event.id).then(
      (detail) => { if (active) setState({ status: 'ready', detail, error: null }) },
      (error) => { if (active) setState({ status: 'error', detail: null, error: safetyReturnErrorMessage(error) }) },
    )
    return () => { active = false }
  }, [event.id])

  async function resubmit() {
    setSubmit({ status: 'saving', error: null, outstanding: [] })
    try {
      const updated = await resubmitSafetyReview(event.id)
      setSubmit({ status: 'success', error: null, outstanding: [] })
      onResubmitted(updated)
    } catch (error) {
      // S-17: a resubmission gets the same arrangement check as a first one.
      const outstanding = error.body?.outstanding
      setSubmit({
        status: 'idle',
        error: outstanding
          ? 'This event still has outstanding arrangements. Complete each item below, then resubmit.'
          : safetyReturnErrorMessage(error),
        outstanding: outstanding ? buildSubmissionReadiness({ outstanding }).items : [],
      })
    }
  }

  const feedback = state.detail?.current_return
  return (
    <section
      className="border rounded-sm p-6 sm:p-7 mt-8"
      style={{ borderColor: C.amber, backgroundColor: `${C.amber}0D` }}
      aria-labelledby="safety-feedback-heading"
    >
      <p className="font-ui text-xs font-medium uppercase tracking-widest mb-2" style={{ color: C.amber }}>
        Returned after safety review
      </p>
      <h2 id="safety-feedback-heading" className="font-display text-2xl mb-3" style={{ color: C.ink }}>
        Safety Officer feedback
      </h2>
      <p className="font-ui text-sm mb-5" style={{ color: C.inkFaint }}>
        Current event state: planning. Revise the affected arrangements below, then submit them for a completely fresh Operational Safety Check.
      </p>

      {state.status === 'loading' && <p className="font-ui text-sm">Loading safety feedback…</p>}
      {state.status === 'error' && <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>{state.error}</p>}
      {state.status === 'ready' && feedback && (
        <div className="font-ui text-sm space-y-2">
          <p className="whitespace-pre-wrap"><span className="font-medium">Reason:</span> {feedback.reason}</p>
          <p>
            <span className="font-medium">Safety Officer:</span>{' '}
            {feedback.safety_officer?.name || feedback.safety_officer_id}
          </p>
          <p><span className="font-medium">Decision time:</span> {new Date(feedback.decided_at).toLocaleString()}</p>
          <p className="sr-only">Safety review history contains {state.detail.safety_review_history.length} review records.</p>
        </div>
      )}

      {submit.status === 'success' ? (
        <p role="status" className="font-ui text-sm font-medium mt-5" style={{ color: C.green }}>
          Revised arrangements submitted for a fresh safety review. The event is now pending its safety check.
        </p>
      ) : (
        <>
          {submit.error && <p role="alert" className="font-ui text-sm mt-4" style={{ color: C.rose }}>{submit.error}</p>}
          {submit.outstanding.length > 0 && (
            <ul className="divide-y mt-3 font-ui text-sm" aria-label="Outstanding arrangements" style={{ borderColor: C.line }}>
              {submit.outstanding.map((item) => (
                <li key={item.key} className="py-2 flex justify-between gap-4">
                  <span style={{ color: C.ink }}>{item.label}</span>
                  <span style={{ color: C.amber }}>{item.statusLabel}</span>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            onClick={resubmit}
            disabled={state.status !== 'ready' || submit.status === 'saving'}
            className="mt-5 px-5 py-3 rounded-sm font-ui font-medium text-sm text-white disabled:opacity-60"
            style={{ backgroundColor: C.teal }}
          >
            {submit.status === 'saving' ? 'Resubmitting…' : 'Resubmit for Safety Review'}
          </button>
        </>
      )}
    </section>
  )
}

export default function EventCoordinatorEventDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const [state, setState] = useState({ status: 'loading', event: null, error: null })
  const [safetyNotice, setSafetyNotice] = useState(null)
  const location = useLocation()
  const navigate = useNavigate()
  // Set by the venue request screen after a send. Read once, then cleared
  // from history so a reload or Back does not announce the same send again.
  const [notice] = useState(location.state?.notice ?? null)
  // S-61: the cancellation decision panel, and what the last decision did.
  const [decisionPanel, setDecisionPanel] = useState(null)
  const [cancellationNotice, setCancellationNotice] = useState(null)
  const [bookingsVersion, setBookingsVersion] = useState(0)
  const decisionTriggerRef = useRef(null)

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
  const isCoordinator = hasPermission(user?.role, PERMISSIONS.EDIT_EQUIPMENT_REQUIREMENTS)
  const canEditEvent = hasPermission(user?.role, PERMISSIONS.UPDATE_ASSIGNED_EVENT)
  const canAssignTechnicalSupport = hasPermission(user?.role, PERMISSIONS.ASSIGN_TECHNICAL_SUPPORT)
  const showVenueRequest = Boolean(state.event) && canRequestVenue(state.event.status)

  return (
    <div className="min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        .csp-focus:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
        @keyframes panelIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .csp-panel-in { animation: panelIn 0.32s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .csp-panel-in { animation: none; }
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
            <CancellationReview
              event={state.event}
              notice={cancellationNotice}
              onDecide={(decision, trigger) => {
                decisionTriggerRef.current = trigger
                setDecisionPanel(decision)
              }}
            />

            {state.event.status === 'submitted' ? (
              <DecisionForm
                eventId={state.event.id}
                onDecided={(updated) => setState({ status: 'ready', event: updated, error: null })}
              />
            ) : (
              <DecisionRecord event={state.event} />
            )}

            <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
              <h1 className="font-display text-3xl mb-2" style={{ color: C.ink }}>
                {form.name || 'Untitled event request'}
              </h1>
              {/* S-82: who changed or decided what on this event, and when. */}
              <Link
                to={`/events/${state.event.id}/history`}
                className="inline-block font-ui text-sm mb-8"
                style={{ color: C.teal }}
              >
                View change history
              </Link>

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
                <Field label="Other requirements" value={form.specialRequirements} />
                <Field label="Contact name" value={form.contactName} />
                <Field label="Contact email" value={form.contactEmail} />
                <Field label="Contact phone" value={form.contactPhone} />
                <Field label="Internal notes" value={form.internalNotes} />
              </div>
              {canEditEvent && (
                <EventInformationEditor
                  event={state.event}
                  onSaved={(updated) => setState({ status: 'ready', event: updated, error: null })}
                />
              )}
            </section>

            {state.event.status === 'planning' && state.event.safety_decision === 'changes_requested' && (
              <SafetyReturnPanel
                event={state.event}
                onResubmitted={(updated) => {
                  setState({ status: 'ready', event: updated, error: null })
                  setSafetyNotice('Revised arrangements submitted for a fresh safety review. The event is now pending its safety check.')
                }}
              />
            )}
            {isCoordinator && state.event.status === 'planning' && !state.event.safety_decision && (
              <SafetySubmissionPanel
                eventId={state.event.id}
                onSubmitted={(updated) => {
                  setState({ status: 'ready', event: updated, error: null })
                  setSafetyNotice('Submitted for the Operational Safety Check. The Safety Officer will confirm the event.')
                }}
              />
            )}
            {state.event.status === 'pending_safety_check' && !safetyNotice && (
              <p role="status" className="font-ui text-sm mt-6" style={{ color: C.inkFaint }}>
                Pending Safety Check. The Safety Officer will confirm the event or send it back with feedback.
              </p>
            )}
            {safetyNotice && (
              <p role="status" className="font-ui text-sm font-medium mt-6" style={{ color: C.green }}>
                {safetyNotice}
              </p>
            )}
            <EventReadinessPanel event={state.event} />
            {isCoordinator && REASSIGNABLE_STATUSES.has(state.event.status) && <ReassignmentRequestPanel eventId={state.event.id} />}

            <div
              role="group"
              aria-label="Event resources"
              className="border rounded-sm p-7 sm:p-8 mt-8"
              style={{ borderColor: C.line }}
            >
              {isCoordinator && (
                <VenueRequests
                  key={bookingsVersion}
                  eventId={state.event.id}
                  eventStatus={state.event.status}
                  canRequest={showVenueRequest}
                  notice={notice}
                />
              )}

              <section
                aria-labelledby="equipment-requirements-heading"
                className={isCoordinator ? 'border-t pt-8 mt-8' : undefined}
                style={{ borderColor: C.line }}
              >
                <h2 id="equipment-requirements-heading" className="font-display text-2xl mb-2" style={{ color: C.ink }}>
                  Required equipment
                </h2>
                <p className="font-ui text-sm mb-6" style={{ color: C.inkFaint }}>
                  Record the types and quantities Technical Support must prepare for this event.
                </p>
                <EquipmentRequirementsPanel
                  eventId={state.event.id}
                  status={state.event.status}
                  editable={isCoordinator}
                />
                <div className="border rounded-sm p-5" style={{ borderColor: C.line }} aria-label="Equipment preparation readiness">
                  <p className="font-ui text-xs uppercase tracking-wide mb-1" style={{ color: C.inkFaint }}>Equipment preparation</p>
                  <p className="font-ui text-base font-medium" style={{ color: C.ink }}>
                    {equipmentPreparationLabel(state.event.equipment_preparation_status)}
                  </p>
                  <p className="font-ui text-xs uppercase tracking-wide mt-4 mb-1" style={{ color: C.inkFaint }}>Technical Support sign-off</p>
                  <p className="font-ui text-base font-medium" style={{ color: C.ink }}>
                    {describeSignoff(state.event).label}
                  </p>
                  {describeSignoff(state.event).note && (
                    <p className="font-ui text-sm mt-1 whitespace-pre-wrap" style={{ color: C.inkFaint }}>
                      {describeSignoff(state.event).note}
                    </p>
                  )}
                </div>
              </section>

              {canAssignTechnicalSupport && (
                <TechnicalSupportAssignment
                  eventId={state.event.id}
                  eventStatus={state.event.status}
                />
              )}
            </div>
          </>
        )}
      </div>

      {decisionPanel && state.event && (
        <CancellationDecisionPanel
          eventId={state.event.id}
          decision={decisionPanel}
          onClose={() => {
            setDecisionPanel(null)
            decisionTriggerRef.current?.focus()
          }}
          onDecided={({ released_bookings: released, ...event }) => {
            setDecisionPanel(null)
            setState({ status: 'ready', event, error: null })
            setCancellationNotice(
              event.cancellation_decision === 'approved'
                ? cancellationApprovedNotice(released)
                : 'Request declined. The Organiser can see your reason.',
            )
            // The bookings list re-reads, so released bookings disappear.
            setBookingsVersion((version) => version + 1)
          }}
        />
      )}

      <style>{`
        @keyframes panelIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .csp-panel-in { animation: panelIn 0.32s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .csp-panel-in { animation: none; }
        }
      `}</style>
    </div>
  )
}
