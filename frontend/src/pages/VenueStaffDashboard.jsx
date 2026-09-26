import { CalendarDays, ListChecks, LogOut, MapPin, Plus, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import useVenueList from '../components/useVenueList.js'
import VenueList from '../components/VenueList.jsx'
import { getRoleAccess, hasPermission, PERMISSIONS } from '../lib/access.js'
import {
  createVenue,
  DAY_LABELS,
  DEFAULT_HOURS,
  emptyVenueForm,
  getVenueOptions,
  optionLabel,
  validateVenueForm,
  venueErrorMessage,
  venueFieldErrorsToForm,
} from '../lib/venues.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F0EDE5',
  line: '#E3DFD3',
  teal: '#0E7C74',
  sky: '#3C6E96',
  rose: '#B25547',
  green: '#3F8F5F',
}

const UPCOMING_AREAS = [
  {
    icon: CalendarDays,
    title: 'Venue availability',
    description: 'Mark a venue as available or booked for a given date.',
  },
  {
    icon: ListChecks,
    title: 'Setup & teardown checklists',
    description: 'Confirm a space is ready before an event and reset after.',
  },
  {
    icon: MapPin,
    title: 'Space assignment requests',
    description: 'Review incoming requests for a specific venue or room.',
  },
]

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

function FieldError({ id, message }) {
  if (!message) return null
  return (
    <p id={id} role="alert" className="font-ui text-xs mt-1.5" style={{ color: C.rose }}>
      {message}
    </p>
  )
}

function TextField({ id, label, value, onChange, error, required, inputMode, hint }) {
  const errorId = `${id}-error`
  return (
    <div>
      <label htmlFor={id} className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
        {label}
        {required && <span style={{ color: C.inkFaint }}> (required)</span>}
      </label>
      {hint && <p className="font-ui text-xs mb-1.5" style={{ color: C.inkFaint }}>{hint}</p>}
      <input
        id={id}
        name={id}
        type="text"
        inputMode={inputMode}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
        className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
      />
      <FieldError id={errorId} message={error} />
    </div>
  )
}

function CheckboxGroup({ name, legend, options, selected, onChange, error, required }) {
  const errorId = `${name}-error`
  function toggle(code) {
    onChange(selected.includes(code)
      ? selected.filter((value) => value !== code)
      : [...selected, code])
  }

  return (
    <fieldset aria-describedby={error ? errorId : undefined}>
      <legend className="font-ui text-sm font-medium mb-2" style={{ color: C.ink }}>
        {legend}
        {required && <span style={{ color: C.inkFaint }}> (required)</span>}
      </legend>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        {options.map((code) => (
          <label key={code} className="flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
            <input
              type="checkbox"
              name={name}
              value={code}
              checked={selected.includes(code)}
              onChange={() => toggle(code)}
              className="csp-check"
            />
            {optionLabel(code)}
          </label>
        ))}
      </div>
      <FieldError id={errorId} message={error} />
    </fieldset>
  )
}

function HoursField({ days, hours, onChange, errors }) {
  function toggleDay(day) {
    const next = { ...hours }
    if (next[day]) delete next[day]
    else next[day] = { ...DEFAULT_HOURS }
    onChange(next)
  }

  function setTime(day, key, value) {
    onChange({ ...hours, [day]: { ...hours[day], [key]: value } })
  }

  return (
    <fieldset aria-describedby={errors.operating_hours ? 'operating_hours-error' : undefined}>
      <legend className="font-ui text-sm font-medium mb-1" style={{ color: C.ink }}>
        Opening hours<span style={{ color: C.inkFaint }}> (required)</span>
      </legend>
      <p className="font-ui text-xs mb-3" style={{ color: C.inkFaint }}>
        Tick the days the venue is open. Unticked days count as closed.
      </p>
      <ul className="grid gap-2">
        {days.map((day) => {
          const open = Boolean(hours[day])
          const rowError = errors[`hours.${day}`]
          return (
            <li key={day}>
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 font-ui text-sm w-28" style={{ color: C.ink }}>
                  <input
                    type="checkbox"
                    name={`open-${day}`}
                    checked={open}
                    onChange={() => toggleDay(day)}
                    className="csp-check"
                  />
                  {DAY_LABELS[day]}
                </label>
                {open ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="time"
                      name={`${day}-open`}
                      aria-label={`${DAY_LABELS[day]} opening time`}
                      value={hours[day].open}
                      onChange={(event) => setTime(day, 'open', event.target.value)}
                      aria-invalid={Boolean(rowError)}
                      className="csp-input rounded-sm px-2 py-1.5 font-ui text-sm"
                    />
                    <span className="font-ui text-sm" style={{ color: C.inkFaint }}>to</span>
                    <input
                      type="time"
                      name={`${day}-close`}
                      aria-label={`${DAY_LABELS[day]} closing time`}
                      value={hours[day].close}
                      onChange={(event) => setTime(day, 'close', event.target.value)}
                      aria-invalid={Boolean(rowError)}
                      className="csp-input rounded-sm px-2 py-1.5 font-ui text-sm"
                    />
                  </div>
                ) : (
                  <span className="font-ui text-xs" style={{ color: C.inkFaint }}>Closed</span>
                )}
              </div>
              <FieldError id={`hours-${day}-error`} message={rowError} />
            </li>
          )
        })}
      </ul>
      <FieldError id="operating_hours-error" message={errors.operating_hours} />
    </fieldset>
  )
}

function AddVenuePanel({ onClose, onSaved }) {
  const panelRef = useRef(null)
  const [options, setOptions] = useState(null)
  const [optionsError, setOptionsError] = useState(null)
  const [form, setForm] = useState(emptyVenueForm)
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true
    getVenueOptions()
      .then((loaded) => { if (active) setOptions(loaded) })
      .catch(() => {
        if (active) setOptionsError("We couldn't load the venue options. Close the panel and try again.")
      })
    return () => { active = false }
  }, [])

  // Escape closes; Tab stays inside the panel while it is open. onClose is a
  // stable callback, so this runs once, on open, and never steals focus back.
  useEffect(() => {
    const panel = panelRef.current
    panel?.querySelector(FOCUSABLE)?.focus()

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !panel) return
      const focusable = [...panel.querySelectorAll(FOCUSABLE)]
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  function update(field) {
    return (value) => setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setFormError(null)

    const found = validateVenueForm(form)
    setErrors(found)
    if (Object.keys(found).length) {
      setFormError('Complete the required fields before saving.')
      return
    }

    setSaving(true)
    try {
      await createVenue(form)
      onSaved()
    } catch (error) {
      setErrors(venueFieldErrorsToForm(error.fieldErrors, form))
      setFormError(venueErrorMessage(error))
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0"
        style={{ backgroundColor: 'rgba(16,25,43,0.5)' }}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-venue-title"
        className="csp-panel relative h-full w-full max-w-md overflow-y-auto"
        style={{ backgroundColor: C.paper }}
      >
        <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4 border-b" style={{ borderColor: C.line }}>
          <div>
            <h2 id="add-venue-title" className="font-display text-2xl" style={{ color: C.ink }}>
              Add a venue
            </h2>
            <p className="font-ui text-sm mt-1" style={{ color: C.inkFaint }}>
              Saved venues can receive booking requests.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="csp-icon-btn p-1.5 rounded-sm"
            style={{ color: C.ink }}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {optionsError && (
          <p role="alert" className="font-ui text-sm px-6 pt-6" style={{ color: C.rose }}>{optionsError}</p>
        )}
        {!options && !optionsError && (
          <p className="font-ui text-sm px-6 pt-6" style={{ color: C.inkFaint }}>Loading form…</p>
        )}

        {options && (
          <form noValidate onSubmit={handleSubmit} className="px-6 py-6 grid gap-6">
            <TextField id="name" label="Name" required value={form.name} onChange={update('name')} error={errors.name} />
            <TextField
              id="location"
              label="Location"
              required
              hint="Street address and postal code."
              value={form.location}
              onChange={update('location')}
              error={errors.location}
            />
            <TextField
              id="capacity"
              label="Capacity"
              required
              inputMode="numeric"
              hint="The most people the venue holds."
              value={form.capacity}
              onChange={update('capacity')}
              error={errors.capacity}
            />
            <CheckboxGroup
              name="room_layouts"
              legend="Room layouts"
              required
              options={options.room_layouts}
              selected={form.roomLayouts}
              onChange={update('roomLayouts')}
              error={errors.room_layouts}
            />
            <HoursField days={options.days} hours={form.hours} onChange={update('hours')} errors={errors} />
            <CheckboxGroup
              name="facilities"
              legend="Facilities"
              options={options.facilities}
              selected={form.facilities}
              onChange={update('facilities')}
              error={errors.facilities}
            />
            <CheckboxGroup
              name="accessibility"
              legend="Accessibility"
              options={options.accessibility}
              selected={form.accessibility}
              onChange={update('accessibility')}
              error={errors.accessibility}
            />
            <div>
              <label htmlFor="description" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                Description
              </label>
              <textarea
                id="description"
                name="description"
                rows={3}
                value={form.description}
                onChange={(event) => update('description')(event.target.value)}
                className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
              />
            </div>

            {formError && (
              <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>{formError}</p>
            )}

            <div className="flex gap-3">
              <button
                type="submit"
                disabled={saving}
                className="csp-primary-btn px-5 py-3 rounded-sm font-ui font-medium transition-transform duration-200 hover:-translate-y-0.5"
                style={{ backgroundColor: C.teal, color: C.paper }}
              >
                {saving ? 'Saving…' : 'Save venue'}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="csp-ghost-btn px-5 py-3 rounded-sm font-ui font-medium border transition-colors duration-200"
                style={{ borderColor: C.ink, color: C.ink }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

export default function VenueStaffDashboard({ role }) {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const access = getRoleAccess(role)
  const canAdd = hasPermission(role, PERMISSIONS.CREATE_VENUE)
  const { venues, loading, error, reload } = useVenueList()
  const [panelOpen, setPanelOpen] = useState(false)
  const [notice, setNotice] = useState(null)
  const addButtonRef = useRef(null)

  useEffect(() => {
    if (!notice) return undefined
    const timer = setTimeout(() => setNotice(null), 4000)
    return () => clearTimeout(timer)
  }, [notice])

  const closePanel = useCallback(() => {
    setPanelOpen(false)
    addButtonRef.current?.focus()
  }, [])

  const handleSaved = useCallback(() => {
    closePanel()
    setNotice('Venue saved.')
    reload()
  }, [closePanel, reload])

  async function handleSignOut() {
    await signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @keyframes panelIn { from { transform: translateX(100%); } to { transform: translateX(0); } }
        .csp-panel { animation: panelIn 0.32s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in, .csp-panel { animation: none; }
          .csp-primary-btn:hover { transform: none; }
        }

        .csp-signout-btn {
          border-color: ${C.ink};
          color: ${C.ink};
          transition: background-color 0.2s, color 0.2s;
        }
        .csp-signout-btn:hover { background-color: ${C.ink}; color: ${C.paper}; }
        .csp-signout-btn:focus-visible,
        .csp-primary-btn:focus-visible,
        .csp-ghost-btn:focus-visible,
        .csp-icon-btn:focus-visible,
        .csp-check:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
        .csp-primary-btn:disabled { opacity: 0.65; cursor: not-allowed; transform: none; }
        .csp-ghost-btn:hover, .csp-icon-btn:hover { background-color: ${C.paperDim}; }
        .csp-check { accent-color: ${C.teal}; width: 16px; height: 16px; }

        .csp-input {
          border: 1px solid ${C.line};
          background: ${C.paper};
          color: ${C.ink};
          transition: border-color 0.2s;
        }
        .csp-input:focus-visible { outline: 2px solid ${C.teal}; outline-offset: 0; border-color: ${C.teal}; }
        .csp-input[aria-invalid="true"] { border-color: ${C.rose}; }
      `}</style>
      <div className="rise-in w-full max-w-5xl mx-auto">
        <header className="flex items-center justify-between gap-6 mb-14">
          <Logo />
          <button
            type="button"
            onClick={handleSignOut}
            className="csp-signout-btn inline-flex items-center gap-2 px-4 py-2 rounded-sm font-ui text-sm border"
          >
            <LogOut size={15} aria-hidden="true" />
            Sign out
          </button>
        </header>

        <div className="max-w-2xl mb-10">
          <div
            className="inline-flex items-center gap-2 text-xs font-ui px-3 py-1 rounded-sm mb-5"
            style={{ backgroundColor: 'rgba(63,143,95,0.12)', color: C.green }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.green }} />
            Signed in as {access.label}
          </div>
          <h1 className="font-display text-4xl sm:text-5xl mb-4" style={{ color: C.ink }}>
            Venue workspace
          </h1>
          <p className="font-ui text-base leading-relaxed" style={{ color: C.inkFaint }}>
            {access.description}
          </p>
          <p className="font-ui text-xs mt-3" style={{ color: C.inkFaint }}>
            {user.name} · {user.email}
          </p>
        </div>

        <section className="max-w-3xl mb-12" aria-labelledby="venues-heading">
          <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
            <h2 id="venues-heading" className="font-display text-3xl" style={{ color: C.ink }}>
              Your venues
            </h2>
            {canAdd && (
              <button
                ref={addButtonRef}
                type="button"
                onClick={() => setPanelOpen(true)}
                className="csp-primary-btn inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium transition-transform duration-200 hover:-translate-y-0.5"
                style={{ backgroundColor: C.teal, color: C.paper }}
              >
                <Plus size={16} aria-hidden="true" />
                Add venue
              </button>
            )}
          </div>
          <div role="status" className="font-ui text-sm mb-4" style={{ color: C.green }}>
            {notice}
          </div>
          <VenueList
            venues={venues}
            loading={loading}
            error={error}
            onRetry={reload}
            emptyMessage="No venues yet. Add your first venue to start receiving booking requests."
          />
        </section>

        <section className="rounded-sm p-7 sm:p-8 max-w-3xl" style={{ backgroundColor: C.paperDim }}>
          <h2 className="font-display text-2xl mb-6" style={{ color: C.ink }}>
            More venue tools, on the way
          </h2>
          <ul className="divide-y" style={{ borderColor: C.line }}>
            {UPCOMING_AREAS.map(({ icon: Icon, title, description }) => (
              <li key={title} className="py-4 first:pt-0 last:pb-0 flex items-start gap-4">
                <Icon size={20} aria-hidden="true" className="mt-0.5 shrink-0" style={{ color: C.sky }} />
                <div className="min-w-0 flex-1">
                  <h3 className="font-ui text-base font-medium" style={{ color: C.ink }}>{title}</h3>
                  <p className="font-ui text-sm mt-0.5" style={{ color: C.inkFaint }}>{description}</p>
                </div>
                <span
                  className="inline-flex items-center gap-1.5 font-ui text-xs shrink-0 mt-1"
                  style={{ color: C.inkFaint }}
                >
                  <span
                    className="w-1.5 h-1.5 rounded-full border"
                    style={{ borderColor: C.inkFaint }}
                    aria-hidden="true"
                  />
                  Not started
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {panelOpen && <AddVenuePanel onClose={closePanel} onSaved={handleSaved} />}
    </div>
  )
}
