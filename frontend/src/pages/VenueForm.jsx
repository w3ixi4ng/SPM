import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ROLE_ACCESS } from '../lib/access.js'
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
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  teal: '#0E7C74',
  rose: '#B25547',
}

const DASHBOARD = ROLE_ACCESS.venue_staff.dashboardPath

// Where to put focus for each error key, so a failed save lands the user on
// the first thing to fix instead of leaving them at the bottom of the form.
const FOCUS_FOR = {
  name: '#name',
  location: '#location',
  capacity: '#capacity',
  room_layouts: 'input[name="room_layouts"]',
  operating_hours: 'input[name^="open-"]',
  facilities: 'input[name="facilities"]',
  accessibility: 'input[name="accessibility"]',
  description: '#description',
}

function focusFirstError(errors) {
  for (const key of Object.keys(errors)) {
    const selector = key.startsWith('hours.')
      ? `input[name="${key.slice(6)}-open"]`
      : FOCUS_FOR[key]
    const element = selector && document.querySelector(selector)
    if (element) {
      element.focus()
      return
    }
  }
}

function FieldError({ id, message }) {
  if (!message) return null
  return (
    <p id={id} role="alert" className="font-ui text-xs mt-1.5" style={{ color: C.rose }}>
      {message}
    </p>
  )
}

function Section({ title, hint, children }) {
  return (
    <section className="py-8 first:pt-0 border-t first:border-t-0" style={{ borderColor: C.line }}>
      <h2 className="font-display text-2xl mb-1" style={{ color: C.ink }}>{title}</h2>
      {hint && <p className="font-ui text-sm mb-5 max-w-md" style={{ color: C.inkFaint }}>{hint}</p>}
      <div className="grid gap-6">{children}</div>
    </section>
  )
}

function TextField({ id, label, value, onChange, error, required, inputMode, hint, className = '' }) {
  const errorId = `${id}-error`
  const hintId = `${id}-hint`
  return (
    <div className={className}>
      <label htmlFor={id} className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
        {label}
        {required && <span style={{ color: C.inkFaint }}> (required)</span>}
      </label>
      {hint && <p id={hintId} className="font-ui text-xs mb-1.5" style={{ color: C.inkFaint }}>{hint}</p>}
      <input
        id={id}
        name={id}
        type="text"
        inputMode={inputMode}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={[hint && hintId, error && errorId].filter(Boolean).join(' ') || undefined}
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
      <legend className="font-ui text-sm font-medium mb-3" style={{ color: C.ink }}>
        {legend}
        {required && <span style={{ color: C.inkFaint }}> (required)</span>}
      </legend>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3">
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
      <legend className="sr-only">Opening hours</legend>
      <ul className="divide-y" aria-label="Opening hours by day">
        {days.map((day) => {
          const open = Boolean(hours[day])
          const rowError = errors[`hours.${day}`]
          return (
            <li key={day} className="py-3 first:pt-0" style={{ borderColor: C.line }}>
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 min-h-9">
                <label className="flex items-center gap-2 font-ui text-sm w-32" style={{ color: C.ink }}>
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
                      className="csp-input rounded-sm px-3 py-2 font-ui text-sm"
                    />
                    <span className="font-ui text-sm" style={{ color: C.inkFaint }}>to</span>
                    <input
                      type="time"
                      name={`${day}-close`}
                      aria-label={`${DAY_LABELS[day]} closing time`}
                      value={hours[day].close}
                      onChange={(event) => setTime(day, 'close', event.target.value)}
                      aria-invalid={Boolean(rowError)}
                      className="csp-input rounded-sm px-3 py-2 font-ui text-sm"
                    />
                  </div>
                ) : (
                  <span className="font-ui text-sm" style={{ color: C.inkFaint }}>Closed</span>
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

export default function VenueForm() {
  const navigate = useNavigate()
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
      .catch((error) => {
        if (!active) return
        setOptionsError(error.status === 401 || error.status === 403
          ? venueErrorMessage(error)
          : "We couldn't load the venue form. Refresh the page to try again.")
      })
    return () => { active = false }
  }, [])

  function update(field) {
    return (value) => setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setFormError(null)

    const found = validateVenueForm(form)
    setErrors(found)
    if (Object.keys(found).length) {
      setFormError('Complete the highlighted fields before saving.')
      focusFirstError(found)
      return
    }

    setSaving(true)
    try {
      await createVenue(form)
      navigate(DASHBOARD, { state: { notice: 'Venue saved.' } })
    } catch (error) {
      const fieldErrors = venueFieldErrorsToForm(error.fieldErrors, form)
      setErrors(fieldErrors)
      setFormError(venueErrorMessage(error))
      setSaving(false)
      if (error.status === 409) document.querySelector('#name')?.focus()
      else focusFirstError(fieldErrors)
    }
  }

  return (
    <div className="min-h-screen font-ui" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
          .csp-primary-btn:hover { transform: none; }
        }

        .csp-input {
          border: 1px solid ${C.line};
          background: ${C.paper};
          color: ${C.ink};
          transition: border-color 0.2s;
        }
        .csp-input:focus-visible { outline: 2px solid ${C.teal}; outline-offset: 0; border-color: ${C.teal}; }
        .csp-input[aria-invalid="true"] { border-color: ${C.rose}; }

        .csp-check { accent-color: ${C.teal}; width: 16px; height: 16px; }
        .csp-check:focus-visible,
        .csp-primary-btn:focus-visible,
        .csp-back-link:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
        .csp-primary-btn:disabled { opacity: 0.65; cursor: not-allowed; transform: none; }
        .csp-back-link { transition: color 0.2s; }
        .csp-back-link:hover { color: ${C.ink}; }
      `}</style>

      <div className="max-w-3xl mx-auto px-6 py-12 md:py-16">
        <Link
          to={DASHBOARD}
          className="csp-back-link inline-block font-ui text-sm mb-6 hover:underline"
          style={{ color: C.inkFaint }}
        >
          ← Back to dashboard
        </Link>

        <h1 className="font-display text-4xl sm:text-5xl leading-tight mb-3" style={{ color: C.ink }}>
          New venue
        </h1>
        <p className="font-ui text-base leading-relaxed mb-10 max-w-md" style={{ color: C.inkFaint }}>
          Once saved, the venue can receive booking requests. Fields marked required must be
          filled in first.
        </p>

        {optionsError && (
          <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>{optionsError}</p>
        )}
        {!options && !optionsError && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading form…</p>
        )}

        {options && (
          <form noValidate onSubmit={handleSubmit} className="rise-in" aria-label="New venue">
            <Section title="About the venue">
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
                className="max-w-xs"
              />
              <div>
                <label htmlFor="description" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                  Description
                </label>
                <textarea
                  id="description"
                  name="description"
                  rows={4}
                  value={form.description}
                  onChange={(event) => update('description')(event.target.value)}
                  className="csp-input w-full rounded-sm px-4 py-3 font-ui text-sm"
                />
              </div>
            </Section>

            <Section title="Room layouts">
              <CheckboxGroup
                name="room_layouts"
                legend="Layouts the venue can be set up in"
                required
                options={options.room_layouts}
                selected={form.roomLayouts}
                onChange={update('roomLayouts')}
                error={errors.room_layouts}
              />
            </Section>

            <Section title="Opening hours" hint="Tick the days the venue is open. Unticked days count as closed. At least one day is required.">
              <HoursField days={options.days} hours={form.hours} onChange={update('hours')} errors={errors} />
            </Section>

            <Section title="Facilities & accessibility">
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
            </Section>

            <div className="pt-8 border-t" style={{ borderColor: C.line }}>
              {formError && (
                <p role="alert" className="font-ui text-sm mb-4" style={{ color: C.rose }}>{formError}</p>
              )}
              <button
                type="submit"
                disabled={saving}
                className="csp-primary-btn px-5 py-3 rounded-sm font-ui font-medium transition-transform duration-200 hover:-translate-y-0.5"
                style={{ backgroundColor: C.teal, color: C.paper }}
              >
                {saving ? 'Saving…' : 'Save venue'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
