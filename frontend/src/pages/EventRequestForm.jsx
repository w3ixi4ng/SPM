import { useEffect, useRef, useState } from 'react'
import {
  Armchair,
  Cable,
  CalendarDays,
  Camera,
  ChevronLeft,
  ChevronRight,
  Clock,
  CupSoda,
  Fan,
  Flag,
  Flashlight,
  Laptop,
  Lightbulb,
  Loader2,
  MapPin,
  Mic,
  Package,
  Plug,
  Plus,
  Printer,
  Projector,
  QrCode,
  Save,
  Search,
  Send,
  ShieldAlert,
  Speaker,
  Table2,
  Thermometer,
  Trash2,
  Tv,
  Umbrella,
  Utensils,
  Wifi,
  Wrench,
  X,
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getEventRequest, saveEventRequest } from '../lib/eventRequests.js'

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

const EQUIPMENT_CATALOG = [
  { id: 'projector', label: 'Projector', available: 6, icon: Projector },
  { id: 'microphone', label: 'Wireless microphone', available: 10, icon: Mic },
  { id: 'speaker', label: 'PA speaker system', available: 4, icon: Speaker },
  { id: 'tables', label: 'Folding tables', available: 20, icon: Table2 },
  { id: 'chairs', label: 'Chairs', available: 100, icon: Armchair },
  { id: 'extension-cords', label: 'Extension cords', available: 15, icon: Cable },
  { id: 'stage-lighting', label: 'Stage lighting kit', available: 8, icon: Lightbulb },
  { id: 'video-camera', label: 'Video camera', available: 3, icon: Camera },
  { id: 'tv-screen', label: 'TV display screen', available: 6, icon: Tv },
  { id: 'wifi-router', label: 'Portable Wi-Fi router', available: 5, icon: Wifi },
  { id: 'power-strip', label: 'Power strip', available: 12, icon: Plug },
  { id: 'signage', label: 'Directional signage set', available: 10, icon: MapPin },
  { id: 'waste-bins', label: 'Waste bins', available: 15, icon: Trash2 },
  { id: 'utensil-set', label: 'Catering utensil set', available: 20, icon: Utensils },
  { id: 'beverage-dispenser', label: 'Beverage dispenser', available: 6, icon: CupSoda },
  { id: 'storage-crates', label: 'Storage crates', available: 25, icon: Package },
  { id: 'umbrellas', label: 'Outdoor umbrellas', available: 8, icon: Umbrella },
  { id: 'pedestal-fans', label: 'Pedestal fans', available: 10, icon: Fan },
  { id: 'portable-heaters', label: 'Portable heaters', available: 6, icon: Thermometer },
  { id: 'first-aid-kit', label: 'First aid kit', available: 4, icon: ShieldAlert },
  { id: 'toolkit', label: 'Toolkit', available: 5, icon: Wrench },
  { id: 'flashlights', label: 'Flashlights', available: 12, icon: Flashlight },
  { id: 'laptop', label: 'Presentation laptop', available: 4, icon: Laptop },
  { id: 'printer', label: 'Portable printer', available: 2, icon: Printer },
  { id: 'checkin-kiosk', label: 'QR check-in kiosk', available: 3, icon: QrCode },
  { id: 'banners', label: 'Event banners', available: 10, icon: Flag },
]

const EMPTY_EQUIPMENT_REQUESTS = Object.fromEntries(
  EQUIPMENT_CATALOG.map((item) => [item.id, '']),
)

const EMPTY_FORM = {
  id: '',
  name: '',
  purpose: '',
  date: '',
  startTime: '',
  endTime: '',
  attendance: '',
  venue: '',
  equipmentRequests: EMPTY_EQUIPMENT_REQUESTS,
  accessibility: '',
}

function withAlpha(hex, alpha) {
  const n = Number.parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function validateForSubmit(form) {
  const errors = {}
  if (!form.name.trim()) errors.name = 'Please enter an event name.'
  if (!form.purpose.trim()) errors.purpose = 'Please describe the purpose of this event.'
  if (!form.date) errors.date = 'Please choose a date.'
  if (!form.startTime) errors.startTime = 'Please choose a start time.'
  if (!form.endTime) errors.endTime = 'Please choose an end time.'
  if (form.startTime && form.endTime && form.endTime <= form.startTime) {
    errors.endTime = 'End time must be after the start time.'
  }
  if (!form.attendance || Number(form.attendance) <= 0) {
    errors.attendance = 'Please enter expected attendance.'
  }
  if (!form.venue.trim()) errors.venue = 'Please enter a venue.'
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

function DateSelect({ id, value, onChange, error, disabled }) {
  const [open, setOpen] = useState(false)
  const today = new Date()
  const parsed = value ? value.split('-').map(Number) : null
  const [viewYear, setViewYear] = useState(parsed ? parsed[0] : today.getFullYear())
  const [viewMonth, setViewMonth] = useState(parsed ? parsed[1] - 1 : today.getMonth())

  const containerRef = useRef(null)
  const triggerRef = useRef(null)

  useClickOutside(open, containerRef, () => setOpen(false))

  const startOffset = new Date(viewYear, viewMonth, 1).getDay()
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
  const cells = [
    ...Array.from({ length: startOffset }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ]

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

  function isToday(day) {
    return (
      today.getFullYear() === viewYear &&
      today.getMonth() === viewMonth &&
      today.getDate() === day
    )
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
          <div className="flex items-center justify-between mb-3">
            <button
              type="button"
              onClick={goPrevMonth}
              aria-label="Previous month"
              className="csp-nav-btn rounded-sm p-1"
              style={{ color: C.inkFaint }}
            >
              <ChevronLeft size={16} aria-hidden="true" />
            </button>
            <span className="font-ui text-sm font-medium">
              {MONTH_NAMES[viewMonth]} {viewYear}
            </span>
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
            {cells.map((day, i) =>
              day === null ? (
                <span key={`blank-${i}`} />
              ) : (
                <button
                  key={day}
                  type="button"
                  onClick={() => selectDay(day)}
                  className="csp-day-btn font-ui text-sm rounded-sm py-1.5"
                  style={
                    isSelected(day)
                      ? { backgroundColor: C.teal, color: C.paper }
                      : {
                          color: C.ink,
                          border: `1px solid ${isToday(day) ? C.teal : 'transparent'}`,
                        }
                  }
                >
                  {day}
                </button>
              ),
            )}
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

function TimeSelect({ id, value, onChange, error, disabled }) {
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
          {TIME_OPTIONS.map((time) => (
            <button
              key={time}
              type="button"
              role="option"
              aria-selected={value === time}
              data-selected={value === time}
              onClick={() => selectTime(time)}
              className="csp-time-option w-full text-left px-4 py-2 font-ui text-sm"
              style={value === time ? { backgroundColor: C.teal, color: C.paper } : { color: C.ink }}
            >
              {formatTimeDisplay(time)}
            </button>
          ))}
        </div>
      )}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  )
}

function EquipmentPanel({ open, onClose, quantities, onQuantityChange, disabled }) {
  const panelRef = useRef(null)
  const [query, setQuery] = useState('')

  useEffect(() => {
    if (open) setQuery('')
  }, [open])

  useEffect(() => {
    if (!open) return undefined

    const panel = panelRef.current
    const focusableSelector =
      'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'

    function getFocusable() {
      return panel ? Array.from(panel.querySelectorAll(focusableSelector)) : []
    }

    const focusTimer = setTimeout(() => {
      getFocusable()[0]?.focus()
    }, 0)

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab') return
      const items = getFocusable()
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
    return () => {
      clearTimeout(focusTimer)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open, onClose])

  if (!open) return null

  const filtered = EQUIPMENT_CATALOG.filter((item) =>
    item.label.toLowerCase().includes(query.trim().toLowerCase()),
  )

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
        aria-label="Add equipment"
        className="csp-panel-slide fixed inset-y-0 right-0 z-50 w-full max-w-md flex flex-col"
        style={{ backgroundColor: C.paper }}
      >
        <div className="flex-1 overflow-y-auto">
          <div className="csp-panel-header sticky top-0 z-10 flex items-center gap-3 px-6 py-4 border-b">
            <div className="relative flex-1">
              <Search
                size={16}
                aria-hidden="true"
                className="absolute left-3 top-1/2 -translate-y-1/2"
                style={{ color: C.inkFaint }}
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search equipment..."
                aria-label="Search equipment"
                className="csp-input w-full rounded-sm pl-9 pr-4 py-2.5 font-ui text-sm"
              />
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close equipment panel"
              className="csp-icon-btn shrink-0 rounded-sm p-2"
              style={{ color: C.inkFaint }}
            >
              <X size={20} aria-hidden="true" />
            </button>
          </div>

          {filtered.length === 0 ? (
            <p className="font-ui text-sm px-6 py-8" style={{ color: C.inkFaint }}>
              No equipment matches &ldquo;{query}&rdquo;.
            </p>
          ) : (
            <div className="divide-y" style={{ color: C.line }}>
              {filtered.map((item) => {
                const Icon = item.icon
                return (
                  <div key={item.id} className="flex items-center gap-4 px-6 py-3">
                    <Icon size={20} aria-hidden="true" className="shrink-0" style={{ color: C.sky }} />
                    <div className="flex-1 min-w-0">
                      <p className="font-ui text-base font-medium" style={{ color: C.ink }}>
                        {item.label}
                      </p>
                      <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                        Available quantity: {item.available}
                      </p>
                    </div>
                    <div>
                      <label htmlFor={`equip-${item.id}`} className="sr-only">
                        Quantity of {item.label} to request
                      </label>
                      <input
                        id={`equip-${item.id}`}
                        type="number"
                        min="0"
                        max={item.available}
                        placeholder="0"
                        value={quantities[item.id]}
                        onChange={(e) => onQuantityChange(item.id, e.target.value)}
                        disabled={disabled}
                        className="csp-input w-20 rounded-sm px-3 py-2 font-ui text-sm"
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

function StatusBadge({ status }) {
  const isDraft = status === 'draft'
  const color = isDraft ? C.amber : C.green
  const label = isDraft ? 'Draft' : 'Submitted'

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm font-ui text-xs font-medium"
      style={{ color, backgroundColor: withAlpha(color, 0.12) }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      {label}
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

export default function EventRequestForm() {
  const { id: routeId } = useParams()
  const navigate = useNavigate()

  const [form, setForm] = useState(EMPTY_FORM)
  const [status, setStatus] = useState('draft')
  const [errors, setErrors] = useState({})
  const [saveState, setSaveState] = useState('idle')
  const [submitState, setSubmitState] = useState('idle')
  const [equipmentPanelOpen, setEquipmentPanelOpen] = useState(false)

  const fieldRefs = useRef({})
  const equipmentTriggerRef = useRef(null)

  useEffect(() => {
    if (!routeId) return
    const existing = getEventRequest(routeId)
    if (existing) {
      setForm({
        ...EMPTY_FORM,
        ...existing,
        equipmentRequests: { ...EMPTY_EQUIPMENT_REQUESTS, ...existing.equipmentRequests },
      })
      setStatus(existing.status)
    }
  }, [routeId])

  const isSubmitted = status === 'submitted'
  const isBusy = saveState === 'saving' || submitState === 'submitting'

  const selectedEquipment = EQUIPMENT_CATALOG.filter(
    (item) => Number(form.equipmentRequests[item.id]) > 0,
  )

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }))
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: undefined }))
    if (saveState === 'saved') setSaveState('idle')
  }

  function updateEquipmentQuantity(itemId, value) {
    setForm((prev) => ({
      ...prev,
      equipmentRequests: { ...prev.equipmentRequests, [itemId]: value },
    }))
    if (saveState === 'saved') setSaveState('idle')
  }

  function closeEquipmentPanel() {
    setEquipmentPanelOpen(false)
    equipmentTriggerRef.current?.focus()
  }

  function handleSaveDraft() {
    if (isBusy || isSubmitted) return
    setSaveState('saving')
    const record = saveEventRequest(form, 'draft')
    setForm(record)
    setStatus('draft')
    if (!routeId) navigate(`/events/${record.id}`, { replace: true })
    setSaveState('saved')
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (isBusy || isSubmitted) return

    const validationErrors = validateForSubmit(form)
    setErrors(validationErrors)

    const firstInvalid = Object.keys(validationErrors)[0]
    if (firstInvalid) {
      fieldRefs.current[firstInvalid]?.focus()
      return
    }

    setSubmitState('submitting')
    setTimeout(() => {
      const record = saveEventRequest(form, 'submitted')
      setForm(record)
      setStatus('submitted')
      setSubmitState('idle')
      if (!routeId) navigate(`/events/${record.id}`, { replace: true })
    }, 500)
  }

  return (
    <div className="min-h-screen" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: none; }
        }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }

        @keyframes panelSlideIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .csp-panel-slide { animation: panelSlideIn 0.32s cubic-bezier(0.22, 1, 0.36, 1) both; }

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
        .csp-time-option:hover { background-color: ${C.paperDim}; }

        @media (prefers-reduced-motion: reduce) {
          .rise-in, .csp-panel-slide { animation: none !important; }
        }
      `}</style>

      <div className="max-w-3xl mx-auto px-6 py-12 md:py-16">
        <Link
          to="/dashboard"
          className="inline-block font-ui text-sm mb-6 transition-colors duration-200 hover:underline"
          style={{ color: C.inkFaint }}
        >
          ← Back to dashboard
        </Link>

        <div className="flex items-start justify-between gap-4 mb-2">
          <h1 className="font-display text-3xl sm:text-4xl leading-tight" style={{ color: C.ink }}>
            New event request
          </h1>
          <StatusBadge status={status} />
        </div>
        <p className="font-ui text-sm leading-relaxed mb-8 max-w-md" style={{ color: C.inkFaint }}>
          Fill in what you know and save a draft, or submit when the request
          is ready for review.
        </p>

        <div
          className="rise-in border rounded-sm px-6 py-8 sm:px-10 sm:py-10"
          style={{ borderColor: C.line }}
        >
          {isSubmitted && (
            <p
              className="font-ui text-sm rounded-sm px-4 py-3 mb-6"
              style={{ backgroundColor: withAlpha(C.green, 0.1), color: C.green }}
            >
              This request has been submitted and can no longer be edited.
            </p>
          )}

          <form noValidate onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="event-name" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
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
                disabled={isSubmitted}
                aria-invalid={Boolean(errors.name)}
                aria-describedby={errors.name ? 'event-name-error' : undefined}
                className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
              />
              <FieldError id="event-name-error" message={errors.name} />
            </div>

            <div>
              <label htmlFor="event-purpose" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
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
                disabled={isSubmitted}
                aria-invalid={Boolean(errors.purpose)}
                aria-describedby={errors.purpose ? 'event-purpose-error' : undefined}
                className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm resize-none"
              />
              <FieldError id="event-purpose-error" message={errors.purpose} />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label htmlFor="event-date" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                  Date
                </label>
                <DateSelect
                  id="event-date"
                  value={form.date}
                  onChange={(v) => updateField('date', v)}
                  error={errors.date}
                  disabled={isSubmitted}
                />
              </div>
              <div>
                <label htmlFor="event-start" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                  Start time
                </label>
                <TimeSelect
                  id="event-start"
                  value={form.startTime}
                  onChange={(v) => updateField('startTime', v)}
                  error={errors.startTime}
                  disabled={isSubmitted}
                />
              </div>
              <div>
                <label htmlFor="event-end" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                  End time
                </label>
                <TimeSelect
                  id="event-end"
                  value={form.endTime}
                  onChange={(v) => updateField('endTime', v)}
                  error={errors.endTime}
                  disabled={isSubmitted}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="event-attendance" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
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
                  disabled={isSubmitted}
                  aria-invalid={Boolean(errors.attendance)}
                  aria-describedby={errors.attendance ? 'event-attendance-error' : undefined}
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                />
                <FieldError id="event-attendance-error" message={errors.attendance} />
              </div>
              <div>
                <label htmlFor="event-venue" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                  Venue
                </label>
                <input
                  ref={(el) => { fieldRefs.current.venue = el }}
                  id="event-venue"
                  name="venue"
                  type="text"
                  placeholder="e.g. Main auditorium"
                  value={form.venue}
                  onChange={(e) => updateField('venue', e.target.value)}
                  disabled={isSubmitted}
                  aria-invalid={Boolean(errors.venue)}
                  aria-describedby={errors.venue ? 'event-venue-error' : undefined}
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                />
                <FieldError id="event-venue-error" message={errors.venue} />
              </div>
            </div>

            <div>
              <span className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                Equipment
                <span className="font-normal" style={{ color: C.inkFaint }}> (optional)</span>
              </span>
              <button
                ref={equipmentTriggerRef}
                type="button"
                onClick={() => setEquipmentPanelOpen(true)}
                disabled={isSubmitted}
                className="inline-flex items-center gap-2 px-5 py-3 rounded-sm font-medium font-ui border transition-colors duration-200 disabled:opacity-60"
                style={{ borderColor: C.ink, color: C.ink }}
              >
                <Plus size={16} aria-hidden="true" />
                Add equipment
              </button>

              <div className="mt-4">
                {selectedEquipment.length === 0 ? (
                  <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                    No equipment requested yet.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {selectedEquipment.map((item) => (
                      <li
                        key={item.id}
                        className="flex items-center justify-between font-ui text-sm"
                        style={{ color: C.ink }}
                      >
                        <span>{item.label}</span>
                        <span style={{ color: C.inkFaint }}>
                          ×{form.equipmentRequests[item.id]}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <div>
              <label htmlFor="event-accessibility" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                Accessibility requirements
                <span className="font-normal" style={{ color: C.inkFaint }}> (optional)</span>
              </label>
              <textarea
                id="event-accessibility"
                name="accessibility"
                rows={2}
                placeholder="Wheelchair access, live captioning, quiet room..."
                value={form.accessibility}
                onChange={(e) => updateField('accessibility', e.target.value)}
                disabled={isSubmitted}
                className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm resize-none"
              />
            </div>

            {!isSubmitted && (
              <div className="flex flex-col-reverse sm:flex-row sm:items-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleSaveDraft}
                  disabled={isBusy}
                  className="flex items-center justify-center gap-2 px-5 py-3 rounded-sm font-medium font-ui border transition-colors duration-200 disabled:opacity-60"
                  style={{ borderColor: C.ink, color: C.ink }}
                >
                  <Save size={16} aria-hidden="true" />
                  {saveState === 'saved' ? 'Saved' : 'Save draft'}
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
                      Submitting...
                    </>
                  ) : (
                    <>
                      <Send size={16} aria-hidden="true" />
                      Submit request
                    </>
                  )}
                </button>
              </div>
            )}
          </form>
        </div>
      </div>

      <EquipmentPanel
        open={equipmentPanelOpen}
        onClose={closeEquipmentPanel}
        quantities={form.equipmentRequests}
        onQuantityChange={updateEquipmentQuantity}
        disabled={isSubmitted}
      />
    </div>
  )
}
