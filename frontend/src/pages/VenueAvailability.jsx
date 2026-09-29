import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, CalendarX2, ChevronLeft, ChevronRight, RefreshCw, X } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import { hasPermission, PERMISSIONS } from '../lib/access.js'
import {
  addVenueBlock,
  availabilityDays,
  availabilityErrorMessage,
  BLOCK_REASONS,
  blockErrorMessages,
  earliestFrom,
  earliestTo,
  emptyBlockForm,
  getVenueAvailability,
  initialMonth,
  isBeforeMonth,
  localToday,
  MONTH_NAMES,
  monthGrids,
  monthRange,
  removeVenueBlock,
  shiftMonth,
  shortDayLabel,
  STATE_META,
  tint,
  validateBlockForm,
  WEEKDAY_HEADINGS,
  yearOptions,
} from '../lib/venueAvailability.js'
import { bookingDateLabel } from '../lib/venueBookings.js'
import { optionLabel } from '../lib/venues.js'

// S-30: a venue's availability calendar. Coordinators see when it is free,
// held, booked or unavailable; Venue Staff also mark days unavailable and
// clear them. Every open, month change and Refresh fetches what is saved now.

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
const LEGEND = ['available', 'held', 'confirmed', 'blocked', 'closed']

// A day's colours: the state's colour as a light fill with a matching edge.
// Closed is dashed, as closed status is elsewhere.
function stateStyle(state) {
  const color = STATE_META[state].color
  return {
    backgroundColor: tint(color),
    border: `1px ${state === 'closed' ? 'dashed' : 'solid'} ${color}`,
  }
}

function Label({ htmlFor, children }) {
  return (
    <label htmlFor={htmlFor} className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
      {children}
    </label>
  )
}

// A small sample of a state's block, for the legend and the day's detail.
function Swatch({ state }) {
  return <span className="w-3.5 h-3.5 rounded-sm shrink-0 inline-block" style={stateStyle(state)} aria-hidden="true" />
}

function Legend() {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-2 font-ui text-xs mb-5" aria-label="What the colours mean">
      {LEGEND.map((state) => (
        <li key={state} className="inline-flex items-center gap-1.5" style={{ color: C.inkFaint }}>
          <Swatch state={state} />
          {STATE_META[state].label}
        </li>
      ))}
    </ul>
  )
}

// One month at a time, moved with the arrows or picked from the Month and
// Year dropdowns, as DateSelect does. Nothing before the month tomorrow falls
// in can be reached.
function MonthControls({ view, earliest, onChange, onRefresh, loading }) {
  const atEarliest = !isBeforeMonth(earliest, view)
  const years = yearOptions(earliest)
  const atLatest = view.year === years[years.length - 1] && view.month === 12

  function pick(next) {
    onChange(isBeforeMonth(next, earliest) ? earliest : next)
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => pick(shiftMonth(view, -1))}
          disabled={atEarliest}
          aria-label="Previous month"
          className="csp-icon-btn rounded-sm p-2 border disabled:opacity-40"
          style={{ borderColor: C.line, color: C.ink }}
        >
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <select
          aria-label="Month"
          value={view.month}
          onChange={(e) => pick({ ...view, month: Number(e.target.value) })}
          className="csp-input rounded-sm border px-3 py-2 font-ui text-sm font-medium"
          style={INPUT_STYLE}
        >
          {MONTH_NAMES.map((name, index) => (
            <option key={name} value={index + 1} disabled={isBeforeMonth({ year: view.year, month: index + 1 }, earliest)}>
              {name}
            </option>
          ))}
        </select>
        <select
          aria-label="Year"
          value={view.year}
          onChange={(e) => pick({ ...view, year: Number(e.target.value) })}
          className="csp-input rounded-sm border px-3 py-2 font-ui text-sm font-medium"
          style={INPUT_STYLE}
        >
          {years.map((year) => <option key={year} value={year}>{year}</option>)}
        </select>
        <button
          type="button"
          onClick={() => pick(shiftMonth(view, 1))}
          disabled={atLatest}
          aria-label="Next month"
          className="csp-icon-btn rounded-sm p-2 border disabled:opacity-40"
          style={{ borderColor: C.line, color: C.ink }}
        >
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>
      <button
        type="button"
        onClick={onRefresh}
        disabled={loading}
        className="csp-secondary-btn inline-flex items-center justify-center gap-2 px-5 py-2 rounded-sm font-ui font-medium text-sm border transition-colors duration-200 disabled:opacity-60"
        style={{ borderColor: C.ink, color: C.ink }}
      >
        <RefreshCw size={15} aria-hidden="true" />
        {loading ? 'Refreshing…' : 'Refresh'}
      </button>
    </div>
  )
}

function longDate(iso) {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
  })
}

function DayCell({ cell, day, selected, onSelect }) {
  if (cell.disabled || !day) {
    return (
      <button
        type="button"
        disabled
        className="csp-day rounded-sm py-2 px-1 font-ui text-sm text-left min-h-16"
        style={{ color: C.inkFaint, backgroundColor: C.paperDim, opacity: 0.55, cursor: 'not-allowed' }}
        aria-label={`${longDate(cell.date)}: not selectable`}
      >
        {cell.day}
      </button>
    )
  }
  // The whole block takes the day's colour; the selected day is ringed in
  // teal on top of it, so its state still shows.
  return (
    <button
      type="button"
      onClick={() => onSelect(cell.date)}
      aria-pressed={selected}
      aria-label={`${longDate(cell.date)}: ${day.label}`}
      className="csp-day rounded-sm py-2 px-1.5 font-ui text-sm text-left min-h-16 flex flex-col gap-1"
      style={{
        ...stateStyle(day.state),
        color: C.ink,
        boxShadow: selected ? `0 0 0 2px ${C.teal}` : 'none',
      }}
    >
      <span className="font-medium">{cell.day}</span>
      <span className="block text-xs truncate" style={{ color: C.ink }}>{shortDayLabel(day)}</span>
    </button>
  )
}

function Calendar({ grids, daysByDate, selectedDate, onSelect }) {
  return (
    <div className="rise-in grid gap-8">
      {grids.map((grid) => (
        <section key={grid.key} aria-label={grid.label}>
          <div className="grid grid-cols-7 gap-1 mb-1">
            {WEEKDAY_HEADINGS.map((heading) => (
              <span key={heading} className="font-ui text-xs text-center" style={{ color: C.inkFaint }}>{heading}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {grid.cells.map((cell, index) => (cell === null
              ? <span key={`blank-${index}`} />
              : (
                <DayCell
                  key={cell.date}
                  cell={cell}
                  day={daysByDate[cell.date]}
                  selected={cell.date === selectedDate}
                  onSelect={onSelect}
                />
              )))}
          </div>
        </section>
      ))}
    </div>
  )
}

function DayDetail({ day, canManage, onRemove, removing }) {
  if (!day) return null
  const heading = longDate(day.date)
  return (
    <section className="rounded-sm px-5 py-4 mt-8" style={{ backgroundColor: C.paperDim }} aria-live="polite" aria-labelledby="day-heading">
      <h3 id="day-heading" className="font-ui text-sm font-medium mb-2" style={{ color: C.ink }}>{heading}</h3>
      {day.items.length > 0 ? (
        <ul className="grid gap-1.5" aria-label={`Bookings on ${heading}`}>
          {day.items.map((item) => (
            <li key={item.label} className="inline-flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
              <Swatch state={item.state} />
              {item.label}
            </li>
          ))}
        </ul>
      ) : (
        <p className="inline-flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
          <Swatch state={day.state} />
          {day.label}
        </p>
      )}
      {day.state === 'blocked' && (
        <p className="font-ui text-xs mt-2" style={{ color: C.inkFaint }}>
          From {bookingDateLabel(day.block.start_date)} to {bookingDateLabel(day.block.end_date)}
          {day.block.note ? ` · ${day.block.note}` : ''}
        </p>
      )}
      {day.state === 'blocked' && canManage && day.block.id && (
        <button
          type="button"
          onClick={() => onRemove(day.block)}
          disabled={removing}
          className="csp-secondary-btn mt-3 px-4 py-2 rounded-sm font-ui font-medium text-sm border transition-colors duration-200 disabled:opacity-60"
          style={{ borderColor: C.rose, color: C.rose }}
        >
          {removing ? 'Removing…' : 'Remove'}
        </button>
      )}
    </section>
  )
}

function BlockPanel({ venueId, venueName, today, onClose, onSaved }) {
  const [form, setForm] = useState(() => emptyBlockForm(venueId, earliestFrom(today)))
  const [state, setState] = useState({ saving: false, errors: [] })
  const panelRef = useRef(null)

  useEffect(() => {
    const panel = panelRef.current
    panel?.querySelector('input, select, textarea, button')?.focus()

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panel) return
      // Keep focus inside the panel while it is open.
      const focusable = [...panel.querySelectorAll('button, input, select, textarea')].filter((el) => !el.disabled)
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

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errors = validateBlockForm(form)
    if (errors.length > 0) {
      setState({ saving: false, errors })
      return
    }
    setState({ saving: true, errors: [] })
    try {
      await addVenueBlock(form)
      onSaved(form)
    } catch (error) {
      setState({ saving: false, errors: blockErrorMessages(error) })
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ backgroundColor: 'rgba(16,25,43,0.5)' }} onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="block-panel-title"
        className="csp-panel-in fixed top-0 right-0 z-50 h-full w-full max-w-md overflow-y-auto border-l p-7"
        style={{ backgroundColor: C.paper, borderColor: C.line }}
      >
        <div className="flex items-start justify-between gap-4 mb-2">
          <h2 id="block-panel-title" className="font-display text-2xl" style={{ color: C.ink }}>Mark unavailable</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="csp-icon-btn rounded-sm p-1" style={{ color: C.inkFaint }}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <p className="font-ui text-sm leading-relaxed mb-6" style={{ color: C.inkFaint }}>
          {venueName} can&apos;t be requested on these days. Existing requests and bookings stay as they are —
          contact their coordinators about moving them.
        </p>
        <form onSubmit={handleSubmit} noValidate className="grid gap-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="block-start">First day</Label>
              <input
                id="block-start"
                type="date"
                value={form.startDate}
                min={earliestFrom(today)}
                onChange={(e) => update('startDate', e.target.value)}
                className={INPUT_CLASS}
                style={INPUT_STYLE}
              />
            </div>
            <div>
              <Label htmlFor="block-end">Last day</Label>
              <input
                id="block-end"
                type="date"
                value={form.endDate}
                min={earliestTo(form.startDate || earliestFrom(today))}
                onChange={(e) => update('endDate', e.target.value)}
                className={INPUT_CLASS}
                style={INPUT_STYLE}
              />
            </div>
          </div>
          <div>
            <Label htmlFor="block-reason">Reason</Label>
            <select
              id="block-reason"
              value={form.reason}
              onChange={(e) => update('reason', e.target.value)}
              className={INPUT_CLASS}
              style={INPUT_STYLE}
            >
              <option value="">Choose a reason</option>
              {BLOCK_REASONS.map((reason) => <option key={reason} value={reason}>{optionLabel(reason)}</option>)}
            </select>
          </div>
          <div>
            <Label htmlFor="block-note">Note for Venue Staff {form.reason === 'other' ? '' : '(optional)'}</Label>
            <textarea
              id="block-note"
              rows={3}
              value={form.note}
              onChange={(e) => update('note', e.target.value)}
              className={INPUT_CLASS}
              style={INPUT_STYLE}
              placeholder="What's wrong, and who to ask"
            />
          </div>
          {state.errors.length > 0 && (
            <div role="alert" className="font-ui text-sm" style={{ color: C.rose }}>
              <p className="font-medium mb-1">This wasn&apos;t saved:</p>
              <ul className="list-disc pl-5 space-y-0.5">
                {state.errors.map((message) => <li key={message}>{message}</li>)}
              </ul>
            </div>
          )}
          <button
            type="submit"
            disabled={state.saving}
            className="csp-primary-btn px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            {state.saving ? 'Saving…' : 'Mark unavailable'}
          </button>
        </form>
      </div>
    </>
  )
}

export default function VenueAvailability() {
  const { id } = useParams()
  const { user } = useAuth()
  const canManage = hasPermission(user?.role, PERMISSIONS.MANAGE_VENUE_BLOCKS)
  const today = useMemo(() => localToday(), [])
  const earliest = useMemo(() => initialMonth(today), [today])
  const [view, setView] = useState(earliest)
  const range = useMemo(() => monthRange(view), [view])
  const [load, setLoad] = useState({ status: 'loading', data: null, error: null })
  // The first day of the month that can be chosen: tomorrow, in its month.
  const firstSelectable = (next) => {
    const { from } = monthRange(next)
    return from < earliestFrom(today) ? earliestFrom(today) : from
  }
  const [selectedDate, setSelectedDate] = useState(() => firstSelectable(earliest))
  const [panelOpen, setPanelOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const [removal, setRemoval] = useState({ removing: false, error: '' })
  const triggerRef = useRef(null)
  const requestRef = useRef(0)

  const refresh = useCallback(() => {
    // Only the latest request may update the page: an earlier, slower one
    // must not overwrite a newer range.
    const request = requestRef.current + 1
    requestRef.current = request
    setLoad((current) => ({ ...current, status: 'loading', error: null }))
    getVenueAvailability(id, range.from, range.to)
      .then((data) => {
        if (requestRef.current === request) setLoad({ status: 'ready', data, error: null })
      })
      .catch((error) => {
        if (requestRef.current === request) setLoad({ status: 'error', data: null, error: availabilityErrorMessage(error) })
      })
  }, [id, range.from, range.to])

  useEffect(() => {
    refresh()
  }, [refresh])

  function changeMonth(next) {
    setView(next)
    setSelectedDate(firstSelectable(next))
  }

  const closePanel = useCallback(() => {
    setPanelOpen(false)
    triggerRef.current?.focus()
  }, [])

  function handleSaved(form) {
    closePanel()
    setNotice(`${load.data?.venue_name ?? 'The venue'} is marked unavailable from ${bookingDateLabel(form.startDate)} to ${bookingDateLabel(form.endDate)}.`)
    refresh()
  }

  async function handleRemove(block) {
    setRemoval({ removing: true, error: '' })
    try {
      await removeVenueBlock(block.id)
      setRemoval({ removing: false, error: '' })
      setNotice(`The block from ${bookingDateLabel(block.start_date)} to ${bookingDateLabel(block.end_date)} is removed.`)
      refresh()
    } catch (error) {
      setRemoval({ removing: false, error: blockErrorMessages(error)[0] })
    }
  }

  const { data } = load
  const days = data ? availabilityDays(range, data.entries, data.operating_hours) : []
  const daysByDate = Object.fromEntries(days.map((day) => [day.date, day]))
  const grids = monthGrids(range, today)

  return (
    <div className="font-ui min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        .csp-input:focus-visible, .csp-primary-btn:focus-visible, .csp-secondary-btn:focus-visible,
        .csp-day:focus-visible, .csp-icon-btn:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
        @keyframes riseIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @keyframes panelIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .csp-panel-in { animation: panelIn 0.32s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in, .csp-panel-in { animation: none; }
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
          <div className="flex flex-wrap items-start justify-between gap-4 mb-2">
            <h1 className="font-display text-3xl" style={{ color: C.ink }}>
              {data ? `${data.venue_name} availability` : 'Venue availability'}
            </h1>
            {canManage && data && (
              <button
                ref={triggerRef}
                type="button"
                onClick={() => setPanelOpen(true)}
                className="csp-primary-btn inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5"
                style={{ backgroundColor: C.teal, color: C.paper }}
              >
                <CalendarX2 size={16} aria-hidden="true" />
                Mark unavailable
              </button>
            )}
          </div>
          <p className="font-ui text-sm leading-relaxed max-w-md mb-6" style={{ color: C.inkFaint }}>
            When the venue is free, tentatively held for an event still in planning, booked, or unavailable.
            Choose a day to see its times.
          </p>

          <MonthControls view={view} earliest={earliest} onChange={changeMonth} onRefresh={refresh} loading={load.status === 'loading'} />

          <div role="status" className="font-ui text-sm mb-4" style={{ color: C.green }}>{notice}</div>

          {load.status === 'error' && (
            <p role="alert" className="font-ui text-sm mb-4" style={{ color: C.rose }}>{load.error}</p>
          )}
          {!data && load.status === 'loading' && (
            <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading availability…</p>
          )}

          {data && (
            <>
              <Legend />
              <Calendar grids={grids} daysByDate={daysByDate} selectedDate={selectedDate} onSelect={setSelectedDate} />
              {removal.error && (
                <p role="alert" className="font-ui text-sm mt-4" style={{ color: C.rose }}>{removal.error}</p>
              )}
              <DayDetail day={daysByDate[selectedDate]} canManage={canManage} onRemove={handleRemove} removing={removal.removing} />
            </>
          )}
        </section>
      </div>

      {panelOpen && data && (
        <BlockPanel venueId={id} venueName={data.venue_name} today={today} onClose={closePanel} onSaved={handleSaved} />
      )}
    </div>
  )
}
