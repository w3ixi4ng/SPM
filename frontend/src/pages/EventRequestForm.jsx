import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  Armchair,
  Cable,
  CalendarDays,
  Camera,
  CheckCircle2,
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
import useAuth from '../auth/useAuth.js'
import {
  createEventDraft,
  createSubmittedEvent,
  eventErrorMessage,
  eventFieldErrorsToForm,
  eventResponseToForm,
  eventStatusMeta,
  getEventRequest,
  submitEventDraft,
  updateEventDraft,
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

const EQUIPMENT_CATALOG = [
  { id: 'projector', label: 'Projector', available: 6, costPerDay: 25, icon: Projector, description: '1080p projector with HDMI and VGA input, includes a screen stand.' },
  { id: 'microphone', label: 'Wireless microphone', available: 10, costPerDay: 8, icon: Mic, description: 'Handheld wireless mic with a dedicated receiver, fresh batteries included.' },
  { id: 'speaker', label: 'PA speaker system', available: 4, costPerDay: 35, icon: Speaker, description: 'Powered speaker pair, enough for a room of up to 150 people.' },
  { id: 'tables', label: 'Folding tables', available: 20, costPerDay: 5, icon: Table2, description: '6-foot folding table, seats six comfortably.' },
  { id: 'chairs', label: 'Chairs', available: 100, costPerDay: 2, icon: Armchair, description: 'Stackable padded chair, indoor or outdoor use.' },
  { id: 'extension-cords', label: 'Extension cords', available: 15, costPerDay: 3, icon: Cable, description: '10-metre heavy-duty extension cord with three outlets.' },
  { id: 'stage-lighting', label: 'Stage lighting kit', available: 8, costPerDay: 40, icon: Lightbulb, description: 'Two adjustable LED par lights on stands, with a basic controller.' },
  { id: 'video-camera', label: 'Video camera', available: 3, costPerDay: 30, icon: Camera, description: 'HD camcorder with tripod, good for recording talks or panels.' },
  { id: 'tv-screen', label: 'TV display screen', available: 6, costPerDay: 20, icon: Tv, description: '55-inch display on a rolling stand, HDMI input.' },
  { id: 'wifi-router', label: 'Portable Wi-Fi router', available: 5, costPerDay: 10, icon: Wifi, description: 'Battery-backed router for venues without reliable Wi-Fi.' },
  { id: 'power-strip', label: 'Power strip', available: 12, costPerDay: 3, icon: Plug, description: '6-outlet power strip with surge protection.' },
  { id: 'signage', label: 'Directional signage set', available: 10, costPerDay: 6, icon: MapPin, description: 'Freestanding A-frame sign with a blank insert for your own text.' },
  { id: 'waste-bins', label: 'Waste bins', available: 15, costPerDay: 4, icon: Trash2, description: '50-litre bin with a liner, general waste or recycling.' },
  { id: 'utensil-set', label: 'Catering utensil set', available: 20, costPerDay: 12, icon: Utensils, description: 'Serving set for one table: tongs, ladles, and serving spoons.' },
  { id: 'beverage-dispenser', label: 'Beverage dispenser', available: 6, costPerDay: 10, icon: CupSoda, description: '10-litre insulated dispenser with a tap, hot or cold drinks.' },
  { id: 'storage-crates', label: 'Storage crates', available: 25, costPerDay: 3, icon: Package, description: 'Stackable plastic crate, holds up to 20kg.' },
  { id: 'umbrellas', label: 'Outdoor umbrellas', available: 8, costPerDay: 8, icon: Umbrella, description: '2.5-metre market umbrella with a weighted base.' },
  { id: 'pedestal-fans', label: 'Pedestal fans', available: 10, costPerDay: 6, icon: Fan, description: 'Oscillating floor fan, three speed settings.' },
  { id: 'portable-heaters', label: 'Portable heaters', available: 6, costPerDay: 9, icon: Thermometer, description: 'Electric space heater, safe for indoor use.' },
  { id: 'first-aid-kit', label: 'First aid kit', available: 4, costPerDay: 5, icon: ShieldAlert, description: 'Fully stocked kit meeting standard workplace first-aid guidelines.' },
  { id: 'toolkit', label: 'Toolkit', available: 5, costPerDay: 7, icon: Wrench, description: 'General-purpose toolkit for last-minute setup fixes.' },
  { id: 'flashlights', label: 'Flashlights', available: 12, costPerDay: 2, icon: Flashlight, description: 'Rechargeable LED flashlight, useful for backstage or outdoor areas.' },
  { id: 'laptop', label: 'Presentation laptop', available: 4, costPerDay: 18, icon: Laptop, description: 'Laptop pre-loaded with presentation software, HDMI and USB-C out.' },
  { id: 'printer', label: 'Portable printer', available: 2, costPerDay: 10, icon: Printer, description: 'Compact printer for name tags or last-minute handouts.' },
  { id: 'checkin-kiosk', label: 'QR check-in kiosk', available: 3, costPerDay: 15, icon: QrCode, description: 'Tablet on a stand for scanning guest QR codes at the door.' },
  { id: 'banners', label: 'Event banners', available: 10, costPerDay: 6, icon: Flag, description: 'Retractable banner stand, 85 x 200cm, reusable frame.' },
]

const EMPTY_EQUIPMENT_REQUESTS = Object.fromEntries(
  EQUIPMENT_CATALOG.map((item) => [item.id, '']),
)

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
  equipmentRequests: EMPTY_EQUIPMENT_REQUESTS,
  accessibility: '',
  specialRequirements: '',
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

// A quantity that is negative or exceeds stock is not an "incomplete field"
// -- it is impossible to fulfil -- so it blocks Save Draft too, unlike the
// rest of validateForSubmit's checks.
function hasInvalidEquipment(form) {
  return EQUIPMENT_CATALOG.some((item) => {
    const raw = form.equipmentRequests[item.id]
    if (raw === '' || raw === undefined) return false
    const q = Number(raw)
    return q < 0 || q > item.available
  })
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
  const invalidEquipment = Object.values(form.equipmentRequests).some((quantity) => {
    if (quantity === '' || Number(quantity) === 0) return false
    return !Number.isInteger(Number(quantity)) || Number(quantity) <= 0
  })
  if (invalidEquipment) {
    errors.equipmentRequests = 'Equipment quantities must be positive whole numbers.'
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
  if (!form.venue.trim()) errors.venue = 'Please enter a venue.'

  if (hasInvalidEquipment(form)) {
    errors.equipmentRequests = 'Fix the equipment quantities before submitting.'
  }

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

function EquipmentDetail({ item, quantity, onQuantityChange, disabled }) {
  const Icon = item.icon
  const numericValue = Number(quantity)
  const isNegative = quantity !== '' && numericValue < 0
  const isOverStock = quantity !== '' && numericValue > item.available
  const isInvalid = isNegative || isOverStock
  const errorId = `equip-detail-${item.id}-error`

  return (
    <div className="flex flex-col gap-5">
      <div
        className="w-56 aspect-square rounded-sm flex items-center justify-center"
        style={{ backgroundColor: C.paperDim }}
      >
        <Icon size={96} aria-hidden="true" style={{ color: C.sky }} />
      </div>

      <div>
        <h3 className="font-display text-2xl" style={{ color: C.ink }}>
          {item.label}
        </h3>
        <p className="font-ui text-sm mt-1" style={{ color: C.inkFaint }}>
          {item.available} available
        </p>
      </div>

      <p className="font-display text-xl" style={{ color: C.ink }}>
        ${item.costPerDay}
        <span className="font-ui text-sm" style={{ color: C.inkFaint }}>
          {' '}
          / day
        </span>
      </p>

      <p className="font-ui text-sm leading-relaxed max-w-sm" style={{ color: C.inkFaint }}>
        {item.description}
      </p>

      <div>
        <label htmlFor={`equip-detail-${item.id}`} className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
          Quantity
        </label>
        <input
          id={`equip-detail-${item.id}`}
          type="number"
          min="0"
          max={item.available}
          placeholder="0"
          value={quantity}
          onChange={(e) => onQuantityChange(e.target.value)}
          disabled={disabled}
          aria-invalid={isInvalid}
          aria-describedby={isInvalid ? errorId : undefined}
          className="csp-input w-24 rounded-sm px-3 py-2 font-ui text-sm"
        />
        {isInvalid && (
          <p id={errorId} role="alert" className="font-ui text-xs mt-1" style={{ color: C.rose }}>
            {isNegative ? 'Enter 0 or more.' : `Only ${item.available} available.`}
          </p>
        )}
      </div>
    </div>
  )
}

function EquipmentPanel({ open, onClose, quantities, onQuantityChange, disabled }) {
  const panelRef = useRef(null)
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState(null)

  useEffect(() => {
    if (open) {
      setQuery('')
      setSelectedId(EQUIPMENT_CATALOG[0]?.id ?? null)
    }
  }, [open])

  const focusableSelector =
    'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'

  function getFocusable() {
    return panelRef.current ? Array.from(panelRef.current.querySelectorAll(focusableSelector)) : []
  }

  // Runs once per open/close transition only -- deliberately depends on
  // `open` alone. `onClose` is a new function on every render of the parent
  // form, and including it here would re-run this on every keystroke
  // anywhere in the form (e.g. a quantity input), yanking focus back to the
  // first focusable element -- the search box -- mid-type.
  useEffect(() => {
    if (!open) return undefined
    const focusTimer = setTimeout(() => {
      getFocusable()[0]?.focus()
    }, 0)
    return () => clearTimeout(focusTimer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // The Tab-trap and Escape listener can safely depend on `onClose` -- all
  // it does is attach/detach a document listener, which has no visible
  // effect on focus by itself.
  useEffect(() => {
    if (!open) return undefined

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
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  if (!open) return null

  const filtered = EQUIPMENT_CATALOG.filter((item) =>
    item.label.toLowerCase().includes(query.trim().toLowerCase()),
  )
  const selectedItem = filtered.find((item) => item.id === selectedId) ?? filtered[0] ?? null

  const hasInvalidQuantity = EQUIPMENT_CATALOG.some((item) => {
    const raw = quantities[item.id]
    if (raw === '' || raw === undefined) return false
    const q = Number(raw)
    return q < 0 || q > item.available
  })

  return (
    <>
      <div
        className="fixed inset-0 z-40"
        style={{ backgroundColor: 'rgba(16,25,43,0.5)' }}
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-label="Add equipment"
          className="csp-modal-in w-full max-w-4xl rounded-sm border overflow-hidden flex flex-col"
          style={{ backgroundColor: C.paper, borderColor: C.line, maxHeight: 'calc(100vh - 3rem)' }}
        >
          <div className="flex items-center justify-between px-6 py-4 border-b shrink-0" style={{ borderColor: C.line }}>
            <span className="font-ui text-sm font-medium" style={{ color: C.ink }}>
              Equipment
            </span>
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

          <div className="flex-1 overflow-y-auto md:flex md:overflow-hidden">
            <div
              className="border-b md:border-b-0 md:border-r md:w-2/5 flex flex-col md:overflow-hidden"
              style={{ borderColor: C.line }}
            >
              <div className="csp-panel-header sticky top-0 z-10 px-4 py-3 border-b shrink-0">
                <div className="relative">
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
                    className="csp-input w-full rounded-sm pl-9 pr-3 py-2 font-ui text-sm"
                  />
                </div>
              </div>

              <div className="md:flex-1 md:overflow-y-auto p-3">
                {filtered.length === 0 ? (
                  <p className="font-ui text-sm px-2 py-6" style={{ color: C.inkFaint }}>
                    No equipment matches &ldquo;{query}&rdquo;.
                  </p>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {filtered.map((item) => {
                      const Icon = item.icon
                      const qty = Number(quantities[item.id]) || 0
                      const isSelected = selectedItem?.id === item.id
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => setSelectedId(item.id)}
                          aria-pressed={isSelected}
                          className="csp-catalog-tile relative flex flex-col items-start gap-2 rounded-sm p-2 text-left"
                          style={isSelected ? { backgroundColor: withAlpha(C.teal, 0.1) } : undefined}
                        >
                          <div
                            className="w-full aspect-square rounded-sm flex items-center justify-center"
                            style={{ backgroundColor: C.paperDim }}
                          >
                            <Icon size={36} aria-hidden="true" style={{ color: C.sky }} />
                          </div>
                          <span className="font-ui text-xs font-medium leading-snug" style={{ color: C.ink }}>
                            {item.label}
                          </span>
                          {qty > 0 && (
                            <span
                              className="absolute top-1 right-1 flex items-center justify-center w-5 h-5 rounded-full font-ui text-xs font-medium"
                              style={{ backgroundColor: C.teal, color: C.paper }}
                            >
                              {qty}
                            </span>
                          )}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>

            <div className="md:flex-1 md:overflow-y-auto p-6">
              {selectedItem ? (
                <EquipmentDetail
                  item={selectedItem}
                  quantity={quantities[selectedItem.id]}
                  onQuantityChange={(v) => onQuantityChange(selectedItem.id, v)}
                  disabled={disabled}
                />
              ) : (
                <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                  Select an item to see rental details.
                </p>
              )}
            </div>
          </div>

          <div className="px-6 py-4 border-t shrink-0" style={{ borderColor: C.line }}>
            <button
              type="button"
              onClick={onClose}
              disabled={hasInvalidQuantity}
              className={`w-full flex items-center justify-center px-5 py-3 rounded-sm font-medium font-ui transition-transform duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${
                hasInvalidQuantity ? '' : 'hover:-translate-y-0.5'
              }`}
              style={{ backgroundColor: C.teal, color: C.paper }}
            >
              Save
            </button>
            {hasInvalidQuantity && (
              <p className="font-ui text-xs mt-2 text-center" style={{ color: C.rose }}>
                Fix the highlighted quantities before saving.
              </p>
            )}
          </div>
        </div>
      </div>
    </>
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
  const [equipmentPanelOpen, setEquipmentPanelOpen] = useState(false)
  const [toast, setToast] = useState(null)

  function showToast(tone, message) {
    setToast({ tone, message })
  }

  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(timer)
  }, [toast])

  const fieldRefs = useRef({})
  const equipmentTriggerRef = useRef(null)
  const backLinkRef = useRef(null)
  // The last form state known to match the server (or, for a brand-new
  // request, the empty form) -- compared against live form state to decide
  // whether leaving would lose work. Updated on load and after every
  // successful save/submit, never on every keystroke.
  const [savedForm, setSavedForm] = useState(EMPTY_FORM)
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false)

  function applyEvent(event) {
    const nextForm = eventResponseToForm(event)
    const merged = {
      ...EMPTY_FORM,
      ...nextForm,
      equipmentRequests: {
        ...EMPTY_EQUIPMENT_REQUESTS,
        ...nextForm.equipmentRequests,
      },
    }
    setForm(merged)
    setSavedForm(merged)
    setStatus(event.status)
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
    if (firstInvalid === 'equipmentRequests') equipmentTriggerRef.current?.focus()
    else fieldRefs.current[firstInvalid]?.focus()
  }

  function handleApiFailure(error) {
    const fieldErrors = eventFieldErrorsToForm(error.fieldErrors)
    setErrors(fieldErrors)
    setFormError(eventErrorMessage(error))
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
  const isApproved = status === 'approved'
  const isRejected = status === 'rejected'
  const isReturned = status === 'returned'
  // Approved and rejected are both decided -- neither is meant to be edited
  // further from here (rejected is enforced server-side too; approved is a
  // product choice, since re-editing a confirmed event without a fresh
  // review would undercut the point of deciding on it at all).
  const isLocked = isApproved || isRejected
  // A returned request still has to satisfy every submitted-required field
  // once resubmitted -- the same stricter check as an already-submitted or
  // approved one, not the permissive draft rules.
  const requiresStrictValidation = isSubmitted || isApproved || isReturned
  // Submitted and approved have no further "submit" step of their own; the
  // form's one submit button at that point is "Save changes". Draft and
  // returned both still need a real submit/resubmit action.
  const routesSubmitToSave = isSubmitted || isApproved
  const isBusy = loadState === 'loading' || saveState === 'saving' || submitState === 'submitting'
  const canShowForm = !routeId || loadState === 'ready'
  // Submitting no longer freezes the record, so it can be dirty too -- the
  // leave-confirmation applies the same way to an in-progress edit of a
  // submitted event as it does to a draft.
  const isDirty = JSON.stringify(form) !== JSON.stringify(savedForm)

  const selectedEquipment = EQUIPMENT_CATALOG.filter(
    (item) => Number(form.equipmentRequests[item.id]) > 0,
  )

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

  function updateEquipmentQuantity(itemId, value) {
    setForm((prev) => ({
      ...prev,
      equipmentRequests: { ...prev.equipmentRequests, [itemId]: value },
    }))
    if (errors.equipmentRequests) {
      setErrors((prev) => ({ ...prev, equipmentRequests: undefined }))
    }
    if (formError) setFormError(null)
    if (saveState === 'saved') setSaveState('idle')
  }

  const closeEquipmentPanel = useCallback(() => {
    // X, Escape and the backdrop all close the panel without going through
    // the (disabled-while-invalid) Save button, so a negative or over-stock
    // value the user was mid-typing would otherwise sit in form state
    // untouched. Rather than guess what they meant (e.g. clamping to the
    // max), just drop it -- the field goes back to empty, as if nothing
    // was entered.
    setForm((prev) => {
      let changed = false
      const sanitized = { ...prev.equipmentRequests }
      for (const item of EQUIPMENT_CATALOG) {
        const raw = sanitized[item.id]
        if (raw === '' || raw === undefined) continue
        const q = Number(raw)
        if (q < 0 || q > item.available) {
          sanitized[item.id] = ''
          changed = true
        }
      }
      return changed ? { ...prev, equipmentRequests: sanitized } : prev
    })
    setErrors((prev) => (
      prev.equipmentRequests
        ? { ...prev, equipmentRequests: undefined }
        : prev
    ))
    setEquipmentPanelOpen(false)
    equipmentTriggerRef.current?.focus()
  }, [])

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

    const validationErrors = requiresStrictValidation ? validateForSubmit(form) : validateDraft(form)
    if (!requiresStrictValidation && hasInvalidEquipment(form)) {
      validationErrors.equipmentRequests = 'Fix the equipment quantities before saving.'
    }
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
      handleApiFailure(error)
      setSubmitState('idle')
      showToast('error', eventErrorMessage(error))
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
          .rise-in, .csp-modal-in, .csp-toast-in { animation: none !important; }
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
                {isApproved && 'This request has been approved.'}
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
                  aria-invalid={Boolean(errors.venue)}
                  aria-describedby={errors.venue ? 'event-venue-error' : undefined}
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                />
                <FieldError id="event-venue-error" message={errors.venue} />
              </div>
            </div>

            <div>
              <span className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
                Equipment
                <span className="font-normal" style={{ color: C.inkFaint }}> (optional)</span>
              </span>
              <button
                ref={equipmentTriggerRef}
                type="button"
                onClick={() => setEquipmentPanelOpen(true)}
                className="inline-flex items-center gap-2 px-5 py-3 rounded-sm font-medium font-ui border transition-colors duration-200 disabled:opacity-60"
                style={{ borderColor: C.ink, color: C.ink }}
              >
                <Plus size={16} aria-hidden="true" />
                Add equipment
              </button>
              <FieldError
                id="event-equipment-error"
                message={errors.equipmentRequests}
              />

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
              <label htmlFor="event-accessibility" className="block font-display text-s font-medium mb-1.5" style={{ color: C.ink }}>
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
                className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm resize-none"
              />
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

      <EquipmentPanel
        open={equipmentPanelOpen}
        onClose={closeEquipmentPanel}
        quantities={form.equipmentRequests}
        onQuantityChange={updateEquipmentQuantity}
      />

      {showLeaveConfirm && (
        <UnsavedChangesDialog
          onCancel={cancelLeave}
          onDiscard={discardAndLeave}
          onSave={saveAndLeave}
        />
      )}

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  )
}
