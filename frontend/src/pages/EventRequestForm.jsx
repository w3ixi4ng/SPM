import { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Loader2,
  Save,
  Send,
  X,
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { optionLabel } from '../lib/venues.js'
import useAuth from '../auth/useAuth.js'
import {
  CANCELLATION_REASON_MAX,
  cancellationDeclinedLabel,
  cancellationErrorMessage,
  cancellationRequestedLabel,
  cancellationSentMessage,
  canRequestCancellation,
  createEventDraft,
  createSubmittedEvent,
  eventErrorMessage,
  resubmitErrorMessage,
  eventFieldErrorsToForm,
  eventResponseToForm,
  getEventOptions,
  eventStatusMeta,
  getEventRequest,
  requestEventCancellation,
  submitEventDraft,
  updateEventDraft,
  validateCancellationReason,
} from '../lib/eventRequests.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  teal: '#0E7C74',
  sky: '#3C6E96',
  amber: '#B5842B',
  green: '#3F8F5F',
  rose: '#B25547',
}

const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const EMPTY_FORM = {
  id: '',
  name: '',
  purpose: '',
  startDate: '',
  startTime: '',
  endDate: '',
  endTime: '',
  attendance: '',
  venue: '',
  accessibility: '',
  specialRequirements: '',
  roomLayout: '',
  requiredFacilities: [],
  requiredAccessibility: [],
}

// Mirrors the backend's same-day rule (see events service schemas.py): once
// either date is missing, or the two dates match, the event is treated as
// single-day and start/end times must be ordered. A later end date allows
// the end time to read earlier than the start time (an overnight event).
function isSameDay(form) {
  return !form.startDate || !form.endDate || form.startDate === form.endDate
}

function withAlpha(hex, alpha) {
  const n = Number.parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function validateDraft(form) {
  const errors = {}
  if (form.startDate && form.endDate && form.endDate < form.startDate) {
    errors.endDate = 'End date must be on or after the start date.'
  }
  if (form.startTime && form.endTime && isSameDay(form) && form.endTime <= form.startTime) {
    errors.endTime = 'End time must be after the start time.'
  }
  if (
    form.attendance !== ''
    && (!Number.isInteger(Number(form.attendance)) || Number(form.attendance) <= 0)
  ) {
    errors.attendance = 'Expected attendance must be a positive whole number.'
  }
  return errors
}

function validateForSubmit(form) {
  const errors = validateDraft(form)
  if (!form.name.trim()) errors.name = 'Please enter an event name.'
  if (!form.purpose.trim()) errors.purpose = 'Please describe the purpose of this event.'
  if (!form.startDate) errors.startDate = 'Please choose a start date.'
  if (!form.startTime) errors.startTime = 'Please choose a start time.'
  if (!form.endDate) errors.endDate = 'Please choose an end date.'
  if (!form.endTime) errors.endTime = 'Please choose an end time.'
  if (!form.attendance) errors.attendance = 'Please enter expected attendance.'
  return errors
}

function useClickOutside(active, ref, onClose) {
  useEffect(() => {
    if (!active) return undefined

    function handlePointerDown(e) {
      if (ref.current && !ref.current.contains(e.target)) onClose()
    }
    function handleKeyDown(e) {
      if (e.key === 'Escape') onClose()
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [active, ref, onClose])
}

function formatDateDisplay(value) {
  if (!value) return ''
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function toISODate(year, month, day) {
  const mm = String(month + 1).padStart(2, '0')
  const dd = String(day).padStart(2, '0')
  return `${year}-${mm}-${dd}`
}

function DateSelect({ id, value, onChange, error, disabled, minDate }) {
  const [open, setOpen] = useState(false)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  // The earliest selectable day. Plain start dates must be strictly in the
  // future; an end date may match its event's start date (a single-day
  // event), so callers pass that start date through as `minDate` instead.
  let earliestSelectable
  if (minDate) {
    const [minYear, minMonth, minDay] = minDate.split('-').map(Number)
    earliestSelectable = new Date(minYear, minMonth - 1, minDay)
  } else {
    earliestSelectable = new Date(today.getTime() + 24 * 60 * 60 * 1000)
  }
  earliestSelectable.setHours(0, 0, 0, 0)
  const parsed = value ? value.split('-').map(Number) : null
  const [viewYear, setViewYear] = useState(parsed ? parsed[0] : earliestSelectable.getFullYear())
  const [viewMonth, setViewMonth] = useState(parsed ? parsed[1] - 1 : earliestSelectable.getMonth())

  const containerRef = useRef(null)
  const triggerRef = useRef(null)

  useClickOutside(open, containerRef, () => setOpen(false))

  const startOffset = new Date(viewYear, viewMonth, 1).getDay()
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
  const cells = [
    ...Array.from({ length: startOffset }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ]
  const yearOptions = Array.from({ length: 6 }, (_, i) => today.getFullYear() + i)

  function selectDay(day) {
    onChange(toISODate(viewYear, viewMonth, day))
    setOpen(false)
    triggerRef.current?.focus()
  }

  function goPrevMonth() {
    if (viewMonth === 0) {
      setViewMonth(11)
      setViewYear((y) => y - 1)
    } else {
      setViewMonth((m) => m - 1)
    }
  }

  function goNextMonth() {
    if (viewMonth === 11) {
      setViewMonth(0)
      setViewYear((y) => y + 1)
    } else {
      setViewMonth((m) => m + 1)
    }
  }

  function isSelected(day) {
    return parsed && parsed[0] === viewYear && parsed[1] === viewMonth + 1 && parsed[2] === day
  }

  // Anything earlier than `earliestSelectable` is disabled and muted, not
  // just visually de-emphasized -- a plain date must be strictly future, and
  // an end date must not fall before its event's start date.
  function isBeforeEarliestSelectable(day) {
    const cellDate = new Date(viewYear, viewMonth, day)
    return cellDate < earliestSelectable
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        id={id}
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-invalid={Boolean(error)}
        className="csp-input csp-picker-trigger w-full flex items-center justify-between rounded-sm px-4 py-3 font-ui text-sm"
      >
        <span style={{ color: value ? C.ink : C.inkFaint }}>
          {value ? formatDateDisplay(value) : 'Select a date'}
        </span>
        <CalendarDays size={16} aria-hidden="true" style={{ color: C.inkFaint }} />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Choose a date"
          className="csp-popover absolute z-10 mt-2 w-72 rounded-sm border p-4"
          style={{ backgroundColor: C.paper, borderColor: C.line, color: C.ink }}
        >
          <div className="flex items-center justify-between gap-2 mb-3">
            <button
              type="button"
              onClick={goPrevMonth}
              aria-label="Previous month"
              className="csp-nav-btn rounded-sm p-1"
              style={{ color: C.inkFaint }}
            >
              <ChevronLeft size={16} aria-hidden="true" />
            </button>
            <div className="flex items-center gap-1">
              <select
                aria-label="Month"
                value={viewMonth}
                onChange={(e) => setViewMonth(Number(e.target.value))}
                className="csp-calendar-select font-ui text-sm font-medium rounded-sm"
              >
                {MONTH_NAMES.map((m, i) => (
                  <option key={m} value={i}>
                    {m}
                  </option>
                ))}
              </select>
              <select
                aria-label="Year"
                value={viewYear}
                onChange={(e) => setViewYear(Number(e.target.value))}
                className="csp-calendar-select font-ui text-sm font-medium rounded-sm"
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={goNextMonth}
              aria-label="Next month"
              className="csp-nav-btn rounded-sm p-1"
              style={{ color: C.inkFaint }}
            >
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          </div>

          <div className="grid grid-cols-7 gap-1 mb-1">
            {WEEKDAYS.map((wd) => (
              <span
                key={wd}
                className="font-ui text-xs text-center"
                style={{ color: C.inkFaint }}
              >
                {wd}
              </span>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-1">
            {cells.map((day, i) => {
              if (day === null) return <span key={`blank-${i}`} />
              const disabledDay = isBeforeEarliestSelectable(day)
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => selectDay(day)}
                  disabled={disabledDay}
                  className="csp-day-btn font-ui text-sm rounded-sm py-1.5"
                  style={
                    isSelected(day)
                      ? { backgroundColor: C.teal, color: C.paper }
                      : { color: disabledDay ? C.inkFaint : C.ink }
                  }
                >
                  {day}
                </button>
              )
            })}
          </div>
        </div>
      )}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  )
}

function generateTimeOptions(stepMinutes) {
  const options = []
  for (let h = 0; h < 24; h++) {
    for (let m = 0; m < 60; m += stepMinutes) {
      options.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`)
    }
  }
  return options
}
const TIME_OPTIONS = generateTimeOptions(30)

function formatTimeDisplay(value) {
  if (!value) return ''
  const [h, m] = value.split(':').map(Number)
  const period = h >= 12 ? 'PM' : 'AM'
  const hour12 = h % 12 === 0 ? 12 : h % 12
  return `${hour12}:${String(m).padStart(2, '0')} ${period}`
}

function TimeSelect({ id, value, onChange, error, disabled, isOptionDisabled }) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)
  const triggerRef = useRef(null)
  const listRef = useRef(null)

  useClickOutside(open, containerRef, () => setOpen(false))

  useEffect(() => {
    if (open) {
      listRef.current?.querySelector('[data-selected="true"]')?.scrollIntoView({ block: 'nearest' })
    }
  }, [open])

  function selectTime(time) {
    onChange(time)
    setOpen(false)
    triggerRef.current?.focus()
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        id={id}
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-invalid={Boolean(error)}
        className="csp-input csp-picker-trigger w-full flex items-center justify-between rounded-sm px-4 py-3 font-ui text-sm"
      >
        <span style={{ color: value ? C.ink : C.inkFaint }}>
          {value ? formatTimeDisplay(value) : 'Select a time'}
        </span>
        <Clock size={16} aria-hidden="true" style={{ color: C.inkFaint }} />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Choose a time"
          ref={listRef}
          className="csp-popover absolute z-10 mt-2 w-full max-h-56 overflow-y-auto rounded-sm border"
          style={{ backgroundColor: C.paper, borderColor: C.line }}
        >
          {TIME_OPTIONS.map((time) => {
            const optionDisabled = isOptionDisabled?.(time) ?? false
            return (
              <button
                key={time}
                type="button"
                role="option"
                aria-selected={value === time}
                aria-disabled={optionDisabled}
                data-selected={value === time}
                onClick={() => !optionDisabled && selectTime(time)}
                disabled={optionDisabled}
                className="csp-time-option w-full text-left px-4 py-2 font-ui text-sm disabled:opacity-40 disabled:cursor-not-allowed"
                style={value === time ? { backgroundColor: C.teal, color: C.paper } : { color: C.ink }}
              >
                {formatTimeDisplay(time)}
              </button>
            )
          })}
        </div>
      )}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  )
}

function StatusBadge({ status }) {
  // 'unsaved' and null/undefined are local UI states, not backend statuses --
  // everything else defers to the same status meta the dashboards use.
  const presentation =
    status === 'unsaved'
      ? { color: C.sky, label: 'Not saved' }
      : status
        ? eventStatusMeta(status)
        : { color: C.inkFaint, label: 'Not loaded' }

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm font-ui text-xs font-medium"
      style={{
        color: presentation.color,
        backgroundColor: withAlpha(presentation.color, 0.12),
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: presentation.color }}
        aria-hidden="true"
      />
      {presentation.label}
    </span>
  )
}

function FieldError({ id, message }) {
  return (
    <div className="min-h-5 mt-1">
      {message && (
        <p id={id} role="alert" className="font-ui text-xs" style={{ color: C.rose }}>
          {message}
        </p>
      )}
    </div>
  )
}

function Toast({ toast, onDismiss }) {
  if (!toast) return null
  const isError = toast.tone === 'error'
  const color = isError ? C.rose : C.green
  const Icon = isError ? AlertCircle : CheckCircle2

  return (
    <div
      role={isError ? 'alert' : 'status'}
      aria-live={isError ? 'assertive' : 'polite'}
      className="csp-toast-in fixed top-6 right-6 z-[60] w-full max-w-xs flex items-start gap-3 rounded-sm border px-4 py-3"
      style={{ backgroundColor: withAlpha(color, 0.1), borderColor: withAlpha(color, 0.3) }}
    >
      <Icon size={18} aria-hidden="true" className="mt-0.5 shrink-0" style={{ color }} />
      <p className="font-ui text-sm flex-1" style={{ color }}>
        {toast.message}
      </p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="csp-icon-btn shrink-0 rounded-sm p-1 -m-1"
        style={{ color }}
      >
        <X size={16} aria-hidden="true" />
      </button>
    </div>
  )
}

function UnsavedChangesDialog({ onCancel, onDiscard, onSave }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    const focusTimer = setTimeout(() => {
      dialogRef.current?.querySelector('button')?.focus()
    }, 0)
    return () => clearTimeout(focusTimer)
  }, [])

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onCancel()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onCancel])

  return (
    <>
      <div
        className="fixed inset-0 z-40"
        style={{ backgroundColor: 'rgba(16,25,43,0.5)' }}
        onClick={onCancel}
        aria-hidden="true"
      />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
        <div
          ref={dialogRef}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="unsaved-changes-title"
          aria-describedby="unsaved-changes-body"
          className="csp-modal-in w-full max-w-md rounded-sm border p-6"
          style={{ backgroundColor: C.paper, borderColor: C.line }}
        >
          <h2 id="unsaved-changes-title" className="font-display text-xl" style={{ color: C.ink }}>
            Unsaved changes
          </h2>
          <p
            id="unsaved-changes-body"
            className="font-ui text-sm mt-2 leading-relaxed"
            style={{ color: C.inkFaint }}
          >
            This event request has changes that have not been saved. Save
            them before leaving, or leave without saving.
          </p>
          <div className="flex flex-col gap-2 mt-6">
            <button
              type="button"
              onClick={onSave}
              className="flex items-center justify-center gap-2 px-5 py-3 rounded-sm font-medium font-ui transition-transform duration-200 hover:-translate-y-0.5"
              style={{ backgroundColor: C.teal, color: C.paper }}
            >
              <Save size={16} aria-hidden="true" />
              Save and leave
            </button>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onDiscard}
                className="flex-1 whitespace-nowrap px-3 py-3 rounded-sm font-medium font-ui border transition-colors duration-200"
                style={{ borderColor: C.rose, color: C.rose }}
              >
                Leave without saving
              </button>
              <button
                type="button"
                onClick={onCancel}
                className="flex-1 whitespace-nowrap px-3 py-3 rounded-sm font-medium font-ui border transition-colors duration-200"
                style={{ borderColor: C.line, color: C.inkFaint }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

// S-62: the Organiser's cancellation request, as the house slide-over. The
// request is only sent from the confirm step, so nothing leaves the browser
// until the Organiser has seen what they are asking for.
function CancellationPanel({ eventId, status, onClose, onSent }) {
  const [step, setStep] = useState('edit')
  const [reason, setReason] = useState('')
  const [error, setError] = useState(null)
  const [sending, setSending] = useState(false)
  const panelRef = useRef(null)

  useEffect(() => {
    panelRef.current?.querySelector('textarea, button:not([aria-label="Close"])')?.focus()
  }, [step])

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

  function review(e) {
    e.preventDefault()
    const problem = validateCancellationReason(reason)
    setError(problem)
    if (!problem) setStep('confirm')
  }

  async function send() {
    setSending(true)
    setError(null)
    try {
      const event = await requestEventCancellation(eventId, reason)
      onSent(event)
    } catch (failure) {
      setError(cancellationErrorMessage(failure))
      setSending(false)
    }
  }

  const statusLabel = eventStatusMeta(status).label.toLowerCase()

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ backgroundColor: 'rgba(16,25,43,0.5)' }} onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cancellation-panel-title"
        className="csp-panel-in fixed top-0 right-0 z-50 h-full w-full max-w-md overflow-y-auto border-l p-7 font-ui"
        style={{ backgroundColor: C.paper, borderColor: C.line }}
      >
        <div className="flex items-start justify-between gap-4 mb-2">
          <h2 id="cancellation-panel-title" className="font-display text-2xl" style={{ color: C.ink }}>
            {step === 'edit' ? 'Request cancellation' : 'Cancel this event?'}
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="csp-icon-btn rounded-sm p-1" style={{ color: C.inkFaint }}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {step === 'edit' ? (
          <form onSubmit={review} noValidate className="grid gap-4">
            <p className="text-sm leading-relaxed" style={{ color: C.inkFaint }}>
              Your request is reviewed before anything changes. The event stays in {statusLabel} until then.
            </p>
            <div>
              <label htmlFor="cancellation-reason" className="block text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                Why does this event need to be cancelled?
              </label>
              <textarea
                id="cancellation-reason"
                rows={5}
                maxLength={CANCELLATION_REASON_MAX}
                value={reason}
                onChange={(e) => { setReason(e.target.value); setError(null) }}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? 'cancellation-reason-error' : undefined}
                className="csp-input w-full rounded-sm px-4 py-3 text-sm"
              />
              {error && (
                <p id="cancellation-reason-error" role="alert" className="text-sm mt-1.5" style={{ color: C.rose }}>{error}</p>
              )}
            </div>
            <button
              type="submit"
              className="px-5 py-3 rounded-sm font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5"
              style={{ backgroundColor: C.teal, color: C.paper }}
            >
              Review request
            </button>
          </form>
        ) : (
          <div className="grid gap-4">
            <p className="text-sm leading-relaxed" style={{ color: C.inkFaint }}>
              This sends a cancellation request with your reason. The event is not cancelled until the request
              has been reviewed, and stays in {statusLabel} until then.
            </p>
            <blockquote className="text-sm whitespace-pre-wrap border-l-2 pl-4 py-1" style={{ borderColor: C.line, color: C.ink }}>
              {reason.trim()}
            </blockquote>
            {error && (
              <p role="alert" className="text-sm" style={{ color: C.rose }}>{error}</p>
            )}
            <button
              type="button"
              onClick={send}
              disabled={sending}
              className="flex items-center justify-center gap-2 px-5 py-3 rounded-sm font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
              style={{ backgroundColor: C.teal, color: C.paper }}
            >
              {sending && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
              {sending ? 'Sending…' : 'Send cancellation request'}
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
        )}
      </div>
    </>
  )
}

const NO_CANCELLATION = Object.freeze({
  cancellation_reason: null,
  cancellation_requested_at: null,
  cancellation_decision: null,
  cancellation_decision_reason: null,
  cancellation_decided_at: null,
})

function cancellationFields(event) {
  return Object.fromEntries(Object.keys(NO_CANCELLATION).map((field) => [field, event[field] ?? null]))
}

export default function EventRequestForm() {
  const { id: routeId } = useParams()
  const navigate = useNavigate()
  const { refresh } = useAuth()

  const [form, setForm] = useState(EMPTY_FORM)
  const [status, setStatus] = useState(routeId ? null : 'unsaved')
  const [decision, setDecision] = useState(null)
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [loadState, setLoadState] = useState(routeId ? 'loading' : 'ready')
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [saveState, setSaveState] = useState('idle')
  const [submitState, setSubmitState] = useState('idle')
  const [toast, setToast] = useState(null)
  // S-62: the stored cancellation request, if any, and the panel that sends
  // one. S-61: with the Coordinator's decision on it. Kept in the API's own
  // field names so the shared helpers read it directly.
  const [cancellation, setCancellation] = useState(NO_CANCELLATION)
  const [cancelPanelOpen, setCancelPanelOpen] = useState(false)
  const [cancelNotice, setCancelNotice] = useState(null)
  const cancelTriggerRef = useRef(null)
  const cancellationEvent = { status, ...cancellation }

  function showToast(tone, message) {
    setToast({ tone, message })
  }

  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(timer)
  }, [toast])

  const fieldRefs = useRef({})
  const backLinkRef = useRef(null)
  // The last form state known to match the server (or, for a brand-new
  // request, the empty form) -- compared against live form state to decide
  // whether leaving would lose work. Updated on load and after every
  // successful save/submit, never on every keystroke.
  const [savedForm, setSavedForm] = useState(EMPTY_FORM)
  // S-36: the venue requirement option sets, from the events service.
  const [venueOptions, setVenueOptions] = useState({ status: 'loading', options: null })

  useEffect(() => {
    let active = true
    getEventOptions()
      .then((options) => { if (active) setVenueOptions({ status: 'ready', options }) })
      .catch(() => { if (active) setVenueOptions({ status: 'error', options: null }) })
    return () => { active = false }
  }, [])

  function toggleRequirement(field, code) {
    setForm((prev) => ({
      ...prev,
      [field]: prev[field].includes(code)
        ? prev[field].filter((item) => item !== code)
        : [...prev[field], code],
    }))
    if (formError) setFormError(null)
  }
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false)

  function applyEvent(event) {
    const nextForm = eventResponseToForm(event)
    const merged = { ...EMPTY_FORM, ...nextForm }
    setForm(merged)
    setSavedForm(merged)
    setStatus(event.status)
    setCancellation(cancellationFields(event))
    setDecision(
      event.decision
        ? {
            decision: event.decision,
            reason: event.decision_reason,
            comment: event.decision_comment,
            decidedAt: event.decided_at,
          }
        : null,
    )
    setErrors({})
    setFormError(null)
  }

  function focusFirstError(nextErrors) {
    const firstInvalid = Object.keys(nextErrors)[0]
    if (!firstInvalid) return
    fieldRefs.current[firstInvalid]?.focus()
  }

  function handleApiFailure(error, message = eventErrorMessage(error)) {
    const fieldErrors = eventFieldErrorsToForm(error.fieldErrors)
    setErrors(fieldErrors)
    setFormError(message)
    focusFirstError(fieldErrors)
    if (error.status === 401) refresh().catch(() => {})
  }

  useEffect(() => {
    let active = true
    if (!routeId) return undefined

    getEventRequest(routeId)
      .then((event) => {
        if (!active) return
        applyEvent(event)
        setLoadState('ready')
      })
      .catch((error) => {
        if (!active) return
        const fieldErrors = eventFieldErrorsToForm(error.fieldErrors)
        setLoadState('error')
        setErrors(fieldErrors)
        setFormError(eventErrorMessage(error))
        focusFirstError(fieldErrors)
        if (error.status === 401) refresh().catch(() => {})
      })

    return () => {
      active = false
    }
  }, [loadAttempt, refresh, routeId])

  const isSubmitted = status === 'submitted'
  // S-36: an approved request moves to planning -- there is no separate
  // "approved" status any more, only the recorded decision.
  const isPlanning = status === 'planning'
  const isRejected = status === 'rejected'
  const isReturned = status === 'returned'
  // Planning and rejected are both decided -- neither is meant to be edited
  // further from here (rejected is enforced server-side too; planning is a
  // product choice, since re-editing an approved event without a fresh
  // review would undercut the point of deciding on it at all).
  const isLocked = isPlanning || isRejected
  // A returned request still has to satisfy every submitted-required field
  // once resubmitted -- the same stricter check as an already-submitted or
  // planning one, not the permissive draft rules.
  const requiresStrictValidation = isSubmitted || isPlanning || isReturned
  // Submitted and planning have no further "submit" step of their own; the
  // form's one submit button at that point is "Save changes". Draft and
  // returned both still need a real submit/resubmit action.
  const routesSubmitToSave = isSubmitted || isPlanning
  const isBusy = loadState === 'loading' || saveState === 'saving' || submitState === 'submitting'
  const canShowForm = !routeId || loadState === 'ready'
  // Submitting no longer freezes the record, so it can be dirty too -- the
  // leave-confirmation applies the same way to an in-progress edit of a
  // submitted event as it does to a draft.
  const isDirty = JSON.stringify(form) !== JSON.stringify(savedForm)

  function updateField(field, value) {
    // Changing the start date or start time can leave a previously-chosen
    // end date/time invalid (before the new start, or no longer after it on
    // the same day). Rather than leave a stale, now-impossible value sitting
    // in form state, drop it -- the picker greys the field out again until
    // the user re-picks.
    setForm((prev) => {
      const next = { ...prev, [field]: value }
      if (field === 'startDate' && next.endDate && next.endDate < next.startDate) {
        next.endDate = ''
      }
      const sameDay = !next.endDate || next.endDate === next.startDate
      if (
        (field === 'startDate' || field === 'startTime')
        && sameDay && next.startTime && next.endTime && next.endTime <= next.startTime
      ) {
        next.endTime = ''
      }
      return next
    })
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: undefined }))
    if ((field === 'startDate' || field === 'startTime') && (errors.endDate || errors.endTime)) {
      setErrors((prev) => ({ ...prev, endDate: undefined, endTime: undefined }))
    }
    if (formError) setFormError(null)
    if (saveState === 'saved') setSaveState('idle')
  }

  // `redirectTo`, when passed, is where a *successful* save sends the user
  // afterward (the "save and leave" path out of the unsaved-changes dialog)
  // instead of the normal stay-on-page/redirect-to-the-new-id behaviour.
  //
  // Submitting a request no longer locks it: this same save path now also
  // handles editing an already-submitted event, PATCHing it in place and
  // leaving its status as `submitted`. The one difference is which rules the
  // resulting record has to satisfy -- a draft can stay incomplete, but an
  // edited submitted event must still have every submitted-required field,
  // matching the backend's own stricter check on that same PATCH.
  async function handleSave({ redirectTo } = {}) {
    if (isBusy) return

    const validationErrors = requiresStrictValidation
      ? validateForSubmit(form)
      : validateDraft(form)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length) {
      focusFirstError(validationErrors)
      return
    }

    setFormError(null)
    setSaveState('saving')
    try {
      const event = routeId
        ? await updateEventDraft(routeId, form)
        : await createEventDraft(form)
      applyEvent(event)
      setSaveState('saved')
      showToast('success', event.status === 'submitted' ? 'Changes saved.' : 'Draft saved.')
      if (redirectTo) navigate(redirectTo)
      else if (!routeId) navigate(`/events/${event.id}`, { replace: true })
    } catch (error) {
      handleApiFailure(error)
      setSaveState('idle')
      showToast('error', eventErrorMessage(error))
    }
  }

  function handleBackClick(e) {
    if (isDirty) {
      e.preventDefault()
      setShowLeaveConfirm(true)
    }
  }

  function cancelLeave() {
    setShowLeaveConfirm(false)
    backLinkRef.current?.focus()
  }

  function discardAndLeave() {
    setShowLeaveConfirm(false)
    navigate('/dashboard')
  }

  function saveAndLeave() {
    setShowLeaveConfirm(false)
    handleSave({ redirectTo: '/dashboard' })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (isBusy) return

    // Submitted and approved have no further "submit" step -- the form's
    // one submit button at that point is "Save changes", so route it there.
    if (routesSubmitToSave) {
      handleSave()
      return
    }

    const validationErrors = validateForSubmit(form)
    setErrors(validationErrors)

    if (Object.keys(validationErrors).length) {
      focusFirstError(validationErrors)
      return
    }

    setFormError(null)
    setSubmitState('submitting')
    try {
      const event = routeId
        ? await submitEventDraft(routeId, form)
        : await createSubmittedEvent(form)
      applyEvent(event)
      setSubmitState('idle')
      showToast('success', 'Request submitted.')
      if (!routeId) navigate(`/events/${event.id}`, { replace: true })
    } catch (error) {
      const message = isReturned ? resubmitErrorMessage(error) : eventErrorMessage(error)
      handleApiFailure(error, message)
      setSubmitState('idle')
      showToast('error', message)
    }
  }

  return (
    <div className="min-h-screen" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: none; }
        }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }

        @keyframes modalIn {
          from { opacity: 0; transform: scale(0.96); }
          to { opacity: 1; transform: scale(1); }
        }
        .csp-modal-in { animation: modalIn 0.2s cubic-bezier(0.22, 1, 0.36, 1) both; }

        @keyframes panelIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .csp-panel-in { animation: panelIn 0.32s cubic-bezier(0.22, 1, 0.36, 1) both; }

        @keyframes toastIn {
          from { opacity: 0; transform: translate(16px, -8px); }
          to { opacity: 1; transform: none; }
        }
        .csp-toast-in { animation: toastIn 0.32s cubic-bezier(0.22, 1, 0.36, 1) both; }

        .csp-panel-header {
          background-color: ${withAlpha(C.paper, 0.82)};
          border-color: ${C.line};
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
        }

        .csp-input {
          border: 1px solid ${C.line};
          background: ${C.paper};
          color: ${C.ink};
          transition: border-color 0.2s, box-shadow 0.2s;
        }
        .csp-input::placeholder { color: ${C.inkFaint}; opacity: 0.65; }
        .csp-input:focus-visible {
          outline: none;
          border-color: ${C.teal};
          box-shadow: 0 0 0 3px ${withAlpha(C.teal, 0.15)};
        }
        .csp-input[aria-invalid="true"] { border-color: ${C.rose}; }
        .csp-input[aria-invalid="true"]:focus-visible {
          box-shadow: 0 0 0 3px ${withAlpha(C.rose, 0.15)};
        }
        .csp-input:disabled { opacity: 0.65; cursor: not-allowed; }

        .csp-nav-btn:hover, .csp-icon-btn:hover { background-color: ${C.paperDim}; }
        .csp-nav-btn:focus-visible,
        .csp-day-btn:focus-visible,
        .csp-time-option:focus-visible,
        .csp-icon-btn:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
        .csp-day-btn:hover { background-color: ${C.paperDim}; }
        .csp-day-btn:disabled { pointer-events: none; }
        .csp-time-option:hover:not(:disabled) { background-color: ${C.paperDim}; }

        .csp-calendar-select {
          border: 1px solid transparent;
          background: ${C.paper};
          color: ${C.ink};
          padding: 2px 4px;
          cursor: pointer;
        }
        .csp-calendar-select:hover { background-color: ${C.paperDim}; }
        .csp-calendar-select:focus-visible {
          outline: none;
          border-color: ${C.teal};
          box-shadow: 0 0 0 3px ${withAlpha(C.teal, 0.15)};
        }

        .csp-catalog-tile:hover { background-color: ${C.paperDim}; }
        .csp-catalog-tile:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }

        @media (prefers-reduced-motion: reduce) {
          .rise-in, .csp-modal-in, .csp-toast-in, .csp-panel-in { animation: none !important; }
        }
      `}</style>

      <div className="max-w-3xl mx-auto px-6 py-12 md:py-16">
        <Link
          ref={backLinkRef}
          to="/dashboard"
          onClick={handleBackClick}
          className="inline-block font-display text-s mb-6 transition-colors duration-200 hover:underline"
          style={{ color: C.inkFaint }}
        >
          ← Back to dashboard
        </Link>

        <div className="flex items-start justify-between gap-4 mb-2">
          <h1 className="font-display text-3xl sm:text-4xl leading-tight" style={{ color: C.ink }}>
            {routeId ? 'Event request' : 'New event request'}
          </h1>
          <StatusBadge status={status} />
        </div>
        <p className="font-ui text-sm leading-relaxed mb-8" style={{ color: C.inkFaint }}>
          Fill in what you know and save a draft, or submit when the request is ready for review.
        </p>

        <div className="rise-in">
          {loadState === 'loading' && routeId && (
            <p className="font-ui text-sm flex items-center gap-2" style={{ color: C.inkFaint }}>
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
              Loading event request…
            </p>
          )}

          {formError && (
            <div
              role="alert"
              className="font-ui text-sm rounded-sm px-4 py-3 mb-6"
              style={{ backgroundColor: withAlpha(C.rose, 0.1), color: C.rose }}
            >
              <p>{formError}</p>
              {loadState === 'error' && routeId && (
                <button
                  type="button"
                  onClick={() => {
                    setLoadState('loading')
                    setStatus(null)
                    setFormError(null)
                    setLoadAttempt((attempt) => attempt + 1)
                  }}
                  className="font-medium underline mt-2"
                >
                  Try loading again
                </button>
              )}
            </div>
          )}

          {isSubmitted && (
            <p
              className="font-ui text-sm rounded-sm px-4 py-3 mb-6"
              style={{ backgroundColor: withAlpha(C.green, 0.1), color: C.green }}
            >
              This request has been submitted and is awaiting a coordinator's
              decision. You can still make changes — save them below.
            </p>
          )}

          {decision && (
            <div
              className="rounded-sm px-4 py-3 mb-6"
              style={{
                backgroundColor: withAlpha(eventStatusMeta(status).color, 0.1),
                color: eventStatusMeta(status).color,
              }}
            >
              <p className="font-ui text-sm font-medium">
                {isPlanning && 'This request has been approved and is in planning.'}
                {isRejected && 'This request has been rejected and is closed.'}
                {isReturned && 'This request was returned for amendment. Fix the issue below, then resubmit.'}
              </p>
              {decision.reason && (
                <p className="font-ui text-sm mt-1">
                  <span className="font-medium">Reason: </span>
                  {decision.reason}
                </p>
              )}
              {decision.comment && (
                <p className="font-ui text-sm mt-1">
                  <span className="font-medium">Note from the coordinator: </span>
                  {decision.comment}
                </p>
              )}
            </div>
          )}

          {routeId && loadState === 'ready' && (cancellation.cancellation_requested_at || canRequestCancellation(cancellationEvent)) && (
            <section aria-label="Cancellation" className="mb-6">
              {cancelNotice && (
                <p
                  role="status"
                  className="font-ui text-sm rounded-sm px-4 py-3 mb-3"
                  style={{ backgroundColor: withAlpha(C.green, 0.1), color: C.green }}
                >
                  {cancelNotice}
                </p>
              )}
              {cancellation.cancellation_requested_at && !cancellation.cancellation_decision && (
                <div
                  className="font-ui text-sm rounded-sm px-4 py-3"
                  style={{ backgroundColor: withAlpha(C.amber, 0.1), color: C.ink }}
                >
                  <p className="font-medium flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.amber }} aria-hidden="true" />
                    {cancellationRequestedLabel(cancellation)}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap">
                    <span className="font-medium">Reason: </span>
                    {cancellation.cancellation_reason}
                  </p>
                  <p className="mt-1" style={{ color: C.inkFaint }}>
                    The event is not cancelled until the request has been reviewed.
                  </p>
                </div>
              )}
              {cancellation.cancellation_decision === 'declined' && (
                // S-61: declined, so the event goes on; the Organiser may ask again.
                <div
                  className="font-ui text-sm rounded-sm px-4 py-3 mb-3"
                  style={{ backgroundColor: withAlpha(C.inkFaint, 0.08), color: C.ink }}
                >
                  <p className="font-medium flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.inkFaint }} aria-hidden="true" />
                    {cancellationDeclinedLabel(cancellation)}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap">
                    <span className="font-medium">Coordinator&apos;s reason: </span>
                    {cancellation.cancellation_decision_reason}
                  </p>
                  <p className="mt-1" style={{ color: C.inkFaint }}>
                    Your event goes ahead. You can send a new request if it still can&apos;t proceed.
                  </p>
                </div>
              )}
              {cancellation.cancellation_decision === 'approved' && (
                <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                  Your cancellation request was approved. This event is cancelled.
                </p>
              )}
              {canRequestCancellation(cancellationEvent) && (
                <button
                  ref={cancelTriggerRef}
                  type="button"
                  onClick={() => setCancelPanelOpen(true)}
                  className="px-5 py-3 rounded-sm font-ui font-medium text-sm border transition-colors duration-200"
                  style={{ borderColor: C.ink, color: C.ink }}
                >
                  Request cancellation
                </button>
              )}
            </section>
          )}

          {canShowForm && (
          <form noValidate onSubmit={handleSubmit} className="space-y-6">
          <fieldset disabled={isLocked} className="space-y-6 border-0 p-0 m-0">
            <div>
              <label htmlFor="event-name" className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
                Event name
              </label>
              <input
                ref={(el) => { fieldRefs.current.name = el }}
                id="event-name"
                name="name"
                type="text"
                placeholder="e.g. Alumni networking evening"
                value={form.name}
                onChange={(e) => updateField('name', e.target.value)}
                aria-invalid={Boolean(errors.name)}
                aria-describedby={errors.name ? 'event-name-error' : undefined}
                className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
              />
              <FieldError id="event-name-error" message={errors.name} />
            </div>

            <div>
              <label htmlFor="event-purpose" className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
                Purpose
              </label>
              <textarea
                ref={(el) => { fieldRefs.current.purpose = el }}
                id="event-purpose"
                name="purpose"
                rows={3}
                placeholder="What is this event for, and who is it for?"
                value={form.purpose}
                onChange={(e) => updateField('purpose', e.target.value)}
                aria-invalid={Boolean(errors.purpose)}
                aria-describedby={errors.purpose ? 'event-purpose-error' : undefined}
                className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm resize-none"
              />
              <FieldError id="event-purpose-error" message={errors.purpose} />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="event-start-date" className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
                  Start date
                </label>
                <DateSelect
                  id="event-start-date"
                  value={form.startDate}
                  onChange={(v) => updateField('startDate', v)}
                  error={errors.startDate}
                />
              </div>
              <div>
                <label htmlFor="event-start-time" className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
                  Start time
                </label>
                <TimeSelect
                  id="event-start-time"
                  value={form.startTime}
                  onChange={(v) => updateField('startTime', v)}
                  error={errors.startTime}
                />
              </div>
              <div>
                <label htmlFor="event-end-date" className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
                  End date
                </label>
                <DateSelect
                  id="event-end-date"
                  value={form.endDate}
                  onChange={(v) => updateField('endDate', v)}
                  error={errors.endDate}
                  minDate={form.startDate || undefined}
                />
              </div>
              <div>
                <label htmlFor="event-end-time" className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
                  End time
                </label>
                <TimeSelect
                  id="event-end-time"
                  value={form.endTime}
                  onChange={(v) => updateField('endTime', v)}
                  error={errors.endTime}
                  isOptionDisabled={(time) => (
                    isSameDay(form) && Boolean(form.startTime) && time <= form.startTime
                  )}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="event-attendance" className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
                  Expected attendance
                </label>
                <input
                  ref={(el) => { fieldRefs.current.attendance = el }}
                  id="event-attendance"
                  name="attendance"
                  type="number"
                  min="1"
                  placeholder="e.g. 120"
                  value={form.attendance}
                  onChange={(e) => updateField('attendance', e.target.value)}
                  aria-invalid={Boolean(errors.attendance)}
                  aria-describedby={errors.attendance ? 'event-attendance-error' : undefined}
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                />
                <FieldError id="event-attendance-error" message={errors.attendance} />
              </div>
              <div>
                <label htmlFor="event-venue" className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
                  Venue preference
                  <span className="font-normal" style={{ color: C.inkFaint }}> (optional)</span>
                </label>
                <input
                  ref={(el) => { fieldRefs.current.venue = el }}
                  id="event-venue"
                  name="venue"
                  type="text"
                  placeholder="e.g. Main auditorium"
                  value={form.venue}
                  onChange={(e) => updateField('venue', e.target.value)}
                  aria-invalid={Boolean(errors.venue)}
                  aria-describedby={errors.venue ? 'event-venue-error' : undefined}
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                />
                <FieldError id="event-venue-error" message={errors.venue} />
              </div>
            </div>

            <div>
              <p className="block font-display text-s font-medium mb-1" style={{ color: C.ink }}>
                Venue requirements
                <span className="font-normal" style={{ color: C.inkFaint }}> (optional)</span>
              </p>
              <p className="font-ui text-xs mb-3" style={{ color: C.inkFaint }}>
                What the venue has to offer. Your Event Coordinator books a venue that has all of it.
              </p>
              {venueOptions.status === 'loading' && (
                <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading options…</p>
              )}
              {venueOptions.status === 'error' && (
                <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>
                  We couldn&apos;t load the venue requirement options. Reload the page to try again.
                </p>
              )}
              {venueOptions.status === 'ready' && (
                <div className="space-y-4">
                  <div>
                    <label htmlFor="event-room-layout" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                      Room layout
                    </label>
                    <select
                      id="event-room-layout"
                      value={form.roomLayout}
                      onChange={(e) => updateField('roomLayout', e.target.value)}
                      className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                    >
                      <option value="">No preference</option>
                      {venueOptions.options.room_layouts.map((code) => (
                        <option key={code} value={code}>{optionLabel(code)}</option>
                      ))}
                    </select>
                  </div>
                  {[
                    { field: 'requiredFacilities', legend: 'Facilities needed', codes: venueOptions.options.facilities },
                    { field: 'requiredAccessibility', legend: 'Accessibility needed', codes: venueOptions.options.accessibility },
                  ].map(({ field, legend, codes }) => (
                    <fieldset key={field} className="border-0 p-0 m-0">
                      <legend className="font-ui text-sm font-medium mb-2" style={{ color: C.ink }}>{legend}</legend>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
                        {codes.map((code) => (
                          <label key={code} className="flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
                            <input
                              type="checkbox"
                              checked={form[field].includes(code)}
                              onChange={() => toggleRequirement(field, code)}
                            />
                            {optionLabel(code)}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                  ))}
                </div>
              )}
            </div>

            <div>
              <label htmlFor="event-special" className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
                Other requirements
                <span className="font-normal" style={{ color: C.inkFaint }}> (optional)</span>
              </label>
              <textarea
                id="event-special"
                name="specialRequirements"
                rows={2}
                placeholder="Registration or sign-up arrangements, catering, security, anything else..."
                value={form.specialRequirements}
                onChange={(e) => updateField('specialRequirements', e.target.value)}
                className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm resize-none"
              />
            </div>

            {routesSubmitToSave ? (
              <div className="flex sm:items-center gap-3 pt-2">
                <button
                  type="submit"
                  disabled={isBusy}
                  className={`flex items-center justify-center gap-2 px-5 py-3 rounded-sm font-medium font-ui transition-transform duration-200 disabled:opacity-70 ${
                    isBusy ? '' : 'hover:-translate-y-0.5'
                  }`}
                  style={{ backgroundColor: C.teal, color: C.paper }}
                >
                  <Save size={16} aria-hidden="true" />
                  {saveState === 'saving'
                    ? 'Saving…'
                    : saveState === 'saved'
                      ? 'Saved'
                      : 'Save changes'}
                </button>
              </div>
            ) : (
              <div className="flex flex-col-reverse sm:flex-row sm:items-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => handleSave()}
                  disabled={isBusy}
                  className="flex items-center justify-center gap-2 px-5 py-3 rounded-sm font-medium font-ui border transition-colors duration-200 disabled:opacity-60"
                  style={{ borderColor: C.ink, color: C.ink }}
                >
                  <Save size={16} aria-hidden="true" />
                  {saveState === 'saving'
                    ? 'Saving…'
                    : saveState === 'saved'
                      ? 'Saved'
                      : isReturned
                        ? 'Save changes'
                        : 'Save draft'}
                </button>
                <button
                  type="submit"
                  disabled={isBusy}
                  className={`flex items-center justify-center gap-2 px-5 py-3 rounded-sm font-medium font-ui transition-transform duration-200 disabled:opacity-70 ${
                    isBusy ? '' : 'hover:-translate-y-0.5'
                  }`}
                  style={{ backgroundColor: C.teal, color: C.paper }}
                >
                  {submitState === 'submitting' ? (
                    <>
                      <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                      {isReturned ? 'Resubmitting...' : 'Submitting...'}
                    </>
                  ) : (
                    <>
                      <Send size={16} aria-hidden="true" />
                      {isReturned ? 'Resubmit request' : 'Submit request'}
                    </>
                  )}
                </button>
              </div>
            )}
          </fieldset>
          </form>
          )}
        </div>
      </div>

      {showLeaveConfirm && (
        <UnsavedChangesDialog
          onCancel={cancelLeave}
          onDiscard={discardAndLeave}
          onSave={saveAndLeave}
        />
      )}

      {cancelPanelOpen && (
        <CancellationPanel
          eventId={routeId}
          status={status}
          onClose={() => {
            setCancelPanelOpen(false)
            cancelTriggerRef.current?.focus()
          }}
          onSent={(event) => {
            // Only the request changed; the form keeps any unsaved edits.
            setCancelPanelOpen(false)
            setStatus(event.status)
            setCancellation(cancellationFields(event))
            setCancelNotice(cancellationSentMessage(event.status))
          }}
        />
      )}

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  )
}
