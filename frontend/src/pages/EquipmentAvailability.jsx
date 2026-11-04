import { useMemo, useState } from 'react'
import { ArrowLeft, ChevronDown, ChevronRight, Package, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import { equipmentStorageLocationLabel } from '../lib/equipment.js'
import {
  availabilityErrorMessages,
  availabilitySummary,
  checkEquipmentAvailability,
  checkedAtLabel,
  emptyAvailabilityForm,
  validateAvailabilityForm,
} from '../lib/equipmentAvailability.js'
import { localToday } from '../lib/venueAvailability.js'
import { bookingDateLabel, shortTime } from '../lib/venueBookings.js'

// S-44: Technical Support checks how much of each equipment pool is free for
// a window, before confirming there is enough. Every press of "Check
// availability" reads live data; nothing is kept between checks.

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  teal: '#0E7C74',
  rose: '#B25547',
}

const INPUT_CLASS = 'csp-input w-full rounded-sm border px-3 py-2 font-ui text-sm'
const INPUT_STYLE = { borderColor: C.line, color: C.ink, backgroundColor: C.paper }
const STATUS_LABELS = { planning: 'Planning', confirmed: 'Confirmed' }

function Label({ htmlFor, children }) {
  return (
    <label htmlFor={htmlFor} className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
      {children}
    </label>
  )
}

function Field({ id, label, children }) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  )
}

function CheckForm({ form, today, onChange, onSubmit, checking }) {
  function update(field, value) {
    const next = { ...form, [field]: value }
    // The end can't be before the start; keep it in step when the start moves past it.
    if (field === 'startDate' && next.endDate < value) next.endDate = value
    onChange(next)
  }

  return (
    <form onSubmit={onSubmit} noValidate className="grid gap-4 mb-8">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Field id="availability-start-date" label="Start date">
          <input id="availability-start-date" type="date" value={form.startDate} min={today}
            onChange={(e) => update('startDate', e.target.value)} className={INPUT_CLASS} style={INPUT_STYLE} />
        </Field>
        <Field id="availability-start-time" label="Start time">
          <input id="availability-start-time" type="time" value={form.startTime}
            onChange={(e) => update('startTime', e.target.value)} className={INPUT_CLASS} style={INPUT_STYLE} />
        </Field>
        <Field id="availability-end-date" label="End date">
          <input id="availability-end-date" type="date" value={form.endDate} min={form.startDate || today}
            onChange={(e) => update('endDate', e.target.value)} className={INPUT_CLASS} style={INPUT_STYLE} />
        </Field>
        <Field id="availability-end-time" label="End time">
          <input id="availability-end-time" type="time" value={form.endTime}
            onChange={(e) => update('endTime', e.target.value)} className={INPUT_CLASS} style={INPUT_STYLE} />
        </Field>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
        <div className="sm:col-span-2">
          <Field id="availability-type" label="Equipment type (optional)">
            <input id="availability-type" type="search" value={form.type} placeholder="e.g. Microphone"
              onChange={(e) => update('type', e.target.value)} className={INPUT_CLASS} style={INPUT_STYLE} />
          </Field>
        </div>
        <Field id="availability-quantity" label="Quantity needed (optional)">
          <input id="availability-quantity" type="number" min="1" step="1" inputMode="numeric" value={form.quantity}
            onChange={(e) => update('quantity', e.target.value)} className={INPUT_CLASS} style={INPUT_STYLE} />
        </Field>
      </div>
      <div>
        <button
          type="submit"
          disabled={checking}
          className="csp-primary-btn inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
          style={{ backgroundColor: C.teal, color: C.paper }}
        >
          <Search size={16} aria-hidden="true" />
          {checking ? 'Checking…' : 'Check availability'}
        </button>
      </div>
    </form>
  )
}

function when(reservation) {
  const start = `${bookingDateLabel(reservation.start_date)} ${shortTime(reservation.start_time)}`
  const end = reservation.end_date === reservation.start_date
    ? shortTime(reservation.end_time)
    : `${bookingDateLabel(reservation.end_date)} ${shortTime(reservation.end_time)}`
  return `${start}–${end}`
}

function ItemRow({ item }) {
  const [open, setOpen] = useState(false)
  const summary = availabilitySummary(item)
  const count = item.reservations.length
  const listId = `reservations-${item.id}`
  return (
    <li className="py-5 first:pt-0 last:pb-0" style={{ borderColor: C.line }}>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="flex items-start gap-3 min-w-0">
          <Package size={20} aria-hidden="true" className="mt-0.5 shrink-0" style={{ color: C.inkFaint }} />
          <div className="min-w-0">
            <h3 className="font-ui text-base font-medium" style={{ color: C.ink }}>{item.type}</h3>
            <p className="font-ui text-xs mt-0.5" style={{ color: C.inkFaint }}>{equipmentStorageLocationLabel(item)}</p>
            <p className="font-ui text-sm mt-0.5" style={{ color: summary.headlineColor ?? C.ink }}>{summary.headline}</p>
            <p className="font-ui text-xs mt-0.5" style={{ color: C.inkFaint }}>{summary.reserved}</p>
          </div>
        </div>
        {summary.verdict && (
          <span className="inline-flex items-center gap-1.5 font-ui text-sm font-medium" style={{ color: summary.verdict.color }}>
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: summary.verdict.color }} aria-hidden="true" />
            {summary.verdict.label}
          </span>
        )}
      </div>
      {count > 0 && (
        <div className="mt-2 ml-8">
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-controls={listId}
            className="csp-link inline-flex items-center gap-1 font-ui text-sm rounded-sm"
            style={{ color: C.teal }}
          >
            {open ? <ChevronDown size={15} aria-hidden="true" /> : <ChevronRight size={15} aria-hidden="true" />}
            {open ? 'Hide' : 'Show'} {count === 1 ? 'the event' : `the ${count} events`} holding it
          </button>
          {open && (
            <ul id={listId} className="mt-2 divide-y rounded-sm px-4" style={{ backgroundColor: C.paperDim }} aria-label={`Events holding ${item.type}`}>
              {item.reservations.map((reservation) => (
                <li key={reservation.event_id} className="py-2.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 font-ui text-sm" style={{ borderColor: C.line }}>
                  <span style={{ color: C.ink }}>{reservation.event_name ?? 'Untitled event'}</span>
                  <span style={{ color: C.inkFaint }}>
                    {when(reservation)} · {STATUS_LABELS[reservation.status] ?? reservation.status} · {reservation.required_quantity}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  )
}

export default function EquipmentAvailability() {
  const today = useMemo(() => localToday(), [])
  const [form, setForm] = useState(() => emptyAvailabilityForm(today))
  const [state, setState] = useState({ status: 'idle', result: null, errors: [] })

  async function handleSubmit(event) {
    event.preventDefault()
    const errors = validateAvailabilityForm(form)
    if (errors.length > 0) {
      setState((current) => ({ ...current, errors }))
      return
    }
    setState((current) => ({ ...current, status: 'checking', errors: [] }))
    try {
      const result = await checkEquipmentAvailability(form)
      setState({ status: 'ready', result, errors: [] })
    } catch (error) {
      // Never leave an old answer showing as if it were this check's.
      setState({ status: 'error', result: null, errors: availabilityErrorMessages(error) })
    }
  }

  const { result } = state
  return (
    <div className="font-ui min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        .csp-input:focus-visible, .csp-primary-btn:focus-visible, .csp-link:focus-visible {
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
          <Link to="/dashboard" className="inline-flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
            <ArrowLeft size={15} aria-hidden="true" />
            Back to dashboard
          </Link>
        </header>

        <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
          <h1 className="font-display text-3xl mb-2" style={{ color: C.ink }}>Check equipment availability</h1>
          <p className="font-ui text-sm leading-relaxed max-w-md mb-6" style={{ color: C.inkFaint }}>
            See how many of each item are free for a time, after what planning and confirmed events have
            reserved and anything out of service.
          </p>

          <CheckForm form={form} today={today} onChange={setForm} onSubmit={handleSubmit} checking={state.status === 'checking'} />

          {state.errors.length > 0 && (
            <div role="alert" className="font-ui text-sm mb-6" style={{ color: C.rose }}>
              <ul className="list-disc pl-5 space-y-0.5">
                {state.errors.map((message) => <li key={message}>{message}</li>)}
              </ul>
            </div>
          )}

          {result && (
            <section aria-labelledby="results-heading">
              <div className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
                <h2 id="results-heading" className="font-display text-2xl" style={{ color: C.ink }}>Availability</h2>
                <p role="status" className="font-ui text-xs" style={{ color: C.inkFaint }}>{checkedAtLabel(result.checked_at)}</p>
              </div>
              {result.items.length === 0 ? (
                <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                  No active equipment matches {result.type ? `“${result.type}”` : 'this check'}. Try another type.
                </p>
              ) : (
                <ul className="divide-y" aria-label="Equipment availability">
                  {result.items.map((item) => <ItemRow key={item.id} item={item} />)}
                </ul>
              )}
            </section>
          )}
        </section>
      </div>
    </div>
  )
}
