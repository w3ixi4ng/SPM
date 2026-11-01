import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import {
  VENUE_CANCELLATION_TEXT_MAX,
  canCancelForUnavailableVenue,
  cancelForUnavailableVenue,
  venueCancellationBody,
  venueCancellationErrorMessage,
  venueCancellationErrors,
  venueCancellationIncomplete,
} from '../lib/venueCancellation.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
  amber: '#B5842B',
  rose: '#B25547',
  green: '#3F8F5F',
}

const FOCUSABLE = 'button, textarea'

// S-89: the house slide-over. The reason and the alternatives considered
// with the Organiser are both recorded on the event and in its history.
function CancelEventPanel({ event, onClose, onCancelled }) {
  const [form, setForm] = useState({ reason: '', alternativesConsidered: '' })
  const [errors, setErrors] = useState({})
  const [failure, setFailure] = useState(null)
  const [sending, setSending] = useState(false)
  const panelRef = useRef(null)

  useEffect(() => {
    const panel = panelRef.current
    panel?.querySelector('textarea')?.focus()
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panel) return
      const focusable = [...panel.querySelectorAll(FOCUSABLE)].filter((el) => !el.disabled)
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

  async function submit(e) {
    e.preventDefault()
    const found = venueCancellationErrors(form)
    setErrors(found)
    setFailure(null)
    if (Object.keys(found).length) return
    setSending(true)
    try {
      onCancelled(await cancelForUnavailableVenue(event.id, venueCancellationBody(form, event)))
    } catch (error) {
      const outcome = venueCancellationErrorMessage(error)
      setErrors(outcome.fieldErrors ?? {})
      setFailure(outcome)
      setSending(false)
    }
  }

  function field(name, key, label, hint) {
    const id = `venue-cancellation-${name}`
    return (
      <div className="mb-5">
        <label htmlFor={id} className="block text-sm font-medium mb-1" style={{ color: C.ink }}>{label}</label>
        <p id={`${id}-hint`} className="text-xs mb-2" style={{ color: C.inkFaint }}>{hint}</p>
        <textarea
          id={id}
          rows={4}
          maxLength={VENUE_CANCELLATION_TEXT_MAX}
          value={form[key]}
          onChange={(e) => setForm({ ...form, [key]: e.target.value })}
          aria-invalid={Boolean(errors[name])}
          aria-describedby={`${id}-hint${errors[name] ? ` ${id}-error` : ''}`}
          className="csp-focus w-full rounded-sm border p-3 text-sm"
          style={{ borderColor: errors[name] ? C.rose : C.line, color: C.ink, backgroundColor: '#FFFFFF' }}
        />
        {errors[name] && (
          <p id={`${id}-error`} className="text-sm mt-1" style={{ color: C.rose }}>{errors[name]}</p>
        )}
      </div>
    )
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ backgroundColor: 'rgba(16,25,43,0.5)' }} onClick={onClose} aria-hidden="true" />
      <form
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="venue-cancellation-title"
        onSubmit={submit}
        noValidate
        className="csp-panel-in fixed top-0 right-0 z-50 h-full w-full max-w-md overflow-y-auto border-l p-7 font-ui"
        style={{ backgroundColor: C.paper, borderColor: C.line }}
      >
        <div className="flex items-start justify-between gap-4 mb-2">
          <h2 id="venue-cancellation-title" className="font-display text-2xl" style={{ color: C.ink }}>
            Cancel event
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-sm p-1" style={{ color: C.inkFaint }}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <p className="text-sm leading-relaxed mb-6" style={{ color: C.inkFaint }}>
          Every venue booking and hold for {event.name} is released, and the Organiser and
          registered Attendees are told. This can&apos;t be undone.
        </p>
        {field('reason', 'reason', 'Reason for cancelling', 'The Organiser sees this in their notification.')}
        {field(
          'alternatives_considered', 'alternativesConsidered', 'Alternatives considered',
          'Which venues or dates you discussed with the Organiser, and why none work.',
        )}
        {failure && <p role="alert" className="text-sm mb-4" style={{ color: C.rose }}>{failure.message}</p>}
        <div className="grid gap-3">
          <button
            type="submit"
            disabled={sending}
            className="px-5 py-3 rounded-sm font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            {sending ? 'Cancelling…' : failure?.retry ? 'Cancel again to finish' : 'Cancel event'}
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={sending}
            className="px-5 py-3 rounded-sm font-medium text-sm border transition-colors duration-200"
            style={{ borderColor: C.ink, color: C.ink }}
          >
            Keep event
          </button>
        </div>
      </form>
    </>
  )
}

function CancelledRecord({ event, onFinished }) {
  const [state, setState] = useState({ sending: false, error: null })
  const incomplete = venueCancellationIncomplete(event)

  // Resuming sends the recorded values back; the service keeps the original.
  async function finish() {
    setState({ sending: true, error: null })
    try {
      onFinished(await cancelForUnavailableVenue(event.id, venueCancellationBody({
        reason: event.venue_cancellation_reason,
        alternativesConsidered: event.venue_cancellation_alternatives,
      }, event)))
      setState({ sending: false, error: null })
    } catch (error) {
      setState({ sending: false, error: venueCancellationErrorMessage(error).message })
    }
  }

  return (
    <>
      <p className="font-ui text-sm flex items-center gap-2" style={{ color: C.ink }}>
        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: incomplete ? C.amber : C.inkFaint }} aria-hidden="true" />
        {incomplete
          ? 'Cancelled. Releasing bookings or notifying people is not finished yet.'
          : `Cancelled on ${new Date(event.venue_cancelled_at).toLocaleString()}. Every booking was released and everyone was notified.`}
      </p>
      <p className="font-ui text-sm mt-3 whitespace-pre-wrap max-w-md" style={{ color: C.ink }}>
        <span style={{ color: C.inkFaint }}>Reason: </span>{event.venue_cancellation_reason}
      </p>
      <p className="font-ui text-sm mt-2 whitespace-pre-wrap max-w-md" style={{ color: C.ink }}>
        <span style={{ color: C.inkFaint }}>Alternatives considered: </span>{event.venue_cancellation_alternatives}
      </p>
      {state.error && <p role="alert" className="font-ui text-sm mt-4" style={{ color: C.rose }}>{state.error}</p>}
      {incomplete && (
        <button
          type="button"
          onClick={finish}
          disabled={state.sending}
          className="mt-6 px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
          style={{ backgroundColor: C.teal, color: C.paper }}
        >
          {state.sending ? 'Finishing…' : 'Finish cancellation'}
        </button>
      )}
    </>
  )
}

// S-89: shown only when venue unavailability affects one of this event's
// bookings, or once the event has been cancelled this way. `bookings` is the
// list the page's venue section already loaded (with S-77's flag), so this
// panel adds no request of its own.
export default function VenueCancellationPanel({ event, bookings, onCancelled }) {
  const [open, setOpen] = useState(false)
  const [notice, setNotice] = useState(null)
  const triggerRef = useRef(null)
  const cancelled = Boolean(event.venue_cancelled_at)

  if (!cancelled && !canCancelForUnavailableVenue(event, bookings)) return null

  function close() {
    setOpen(false)
    triggerRef.current?.focus()
  }

  function done(result) {
    const { released_bookings: released, notified_attendees: notified, ...updated } = result
    setOpen(false)
    setNotice(`Event cancelled. ${released} venue booking${released === 1 ? '' : 's'} released; the Organiser and ${notified} Attendee${notified === 1 ? '' : 's'} notified.`)
    onCancelled(updated)
  }

  return (
    <section aria-labelledby="venue-cancellation-heading" className="border rounded-sm p-7 sm:p-8 mb-8" style={{ borderColor: C.line }}>
      <h2 id="venue-cancellation-heading" className="font-display text-2xl mb-2" style={{ color: C.ink }}>
        {cancelled ? 'Event cancelled' : 'Venue unavailable'}
      </h2>
      {notice && <p role="status" className="font-ui text-sm mb-4" style={{ color: C.green }}>{notice}</p>}
      {cancelled ? (
        <CancelledRecord event={event} onFinished={done} />
      ) : (
        <>
          <p className="font-ui text-sm leading-relaxed max-w-md" style={{ color: C.inkFaint }}>
            A venue this event is booked into is unavailable. If you and the Organiser can&apos;t find
            an alternative venue, you can cancel the event and release everything it holds.
          </p>
          <button
            type="button"
            onClick={(e) => {
              triggerRef.current = e.currentTarget
              setOpen(true)
            }}
            className="csp-focus mt-6 px-5 py-3 rounded-sm font-ui font-medium text-sm border transition-colors duration-200"
            style={{ borderColor: C.ink, color: C.ink }}
          >
            Cancel event
          </button>
        </>
      )}
      {open && <CancelEventPanel event={event} onClose={close} onCancelled={done} />}
    </section>
  )
}
