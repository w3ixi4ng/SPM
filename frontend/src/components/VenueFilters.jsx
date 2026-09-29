import { emptyVenueFilters, optionLabel } from '../lib/venues.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  teal: '#0E7C74',
}

const INPUT_CLASS = 'csp-filter-input w-full rounded-sm border px-3 py-2 font-ui text-sm'
const INPUT_STYLE = { borderColor: C.line, color: C.ink, backgroundColor: C.paper }

function Field({ id, label, children }) {
  return (
    <div>
      <label htmlFor={id} className="font-ui text-sm font-medium block mb-1.5" style={{ color: C.ink }}>
        {label}
      </label>
      {children}
    </div>
  )
}

function Checklist({ legend, codes, selected, onToggle }) {
  return (
    <fieldset className="border-0 p-0 m-0">
      <legend className="font-ui text-sm font-medium mb-2" style={{ color: C.ink }}>{legend}</legend>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5">
        {codes.map((code) => (
          <label key={code} className="flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
            <input type="checkbox" checked={selected.includes(code)} onChange={() => onToggle(code)} />
            {optionLabel(code)}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

// S-34: the venue filters, shared by the Coordinator's Venues tab and the
// venue request screen. Controlled: the page owns `filters` and filters the
// list itself (filterVenues), so the results follow every change. On the
// request screen the date and time are the booking's own fields, so
// `showDateTime` is off there and a checkbox (`openThen`) switches the
// open-at-the-booking's-time filter instead.
export default function VenueFilters({
  idPrefix,
  filters,
  onChange,
  options,
  showDateTime = true,
  openThen = false,
  onOpenThenChange,
}) {
  function set(field, value) {
    onChange({ ...filters, [field]: value })
  }

  function toggle(field, code) {
    set(field, filters[field].includes(code)
      ? filters[field].filter((item) => item !== code)
      : [...filters[field], code])
  }

  // Clears everything, so every venue shows -- on the request screen that
  // includes the open-then filter, which the checkbox turns back on.
  function clear() {
    onChange(emptyVenueFilters())
    onOpenThenChange?.(false)
  }

  return (
    <section
      className="rounded-sm px-5 py-5 mb-6"
      style={{ backgroundColor: C.paperDim }}
      aria-label="Filter venues"
    >
      <style>{`
        .csp-filter-input:focus-visible,
        .csp-filter-clear:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
      `}</style>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
        <Field id={`${idPrefix}-query`} label="Search by name or location">
          <input
            id={`${idPrefix}-query`}
            type="search"
            value={filters.query}
            onChange={(e) => set('query', e.target.value)}
            placeholder="e.g. Anson Road"
            className={INPUT_CLASS}
            style={INPUT_STYLE}
          />
        </Field>
        <Field id={`${idPrefix}-attendance`} label="Holds at least">
          <input
            id={`${idPrefix}-attendance`}
            type="number"
            min="1"
            inputMode="numeric"
            value={filters.attendance}
            onChange={(e) => set('attendance', e.target.value)}
            placeholder="People"
            className={INPUT_CLASS}
            style={INPUT_STYLE}
          />
        </Field>
        <Field id={`${idPrefix}-layout`} label="Room layout">
          <select
            id={`${idPrefix}-layout`}
            value={filters.layout}
            onChange={(e) => set('layout', e.target.value)}
            className={INPUT_CLASS}
            style={INPUT_STYLE}
          >
            <option value="">Any layout</option>
            {(options?.room_layouts ?? []).map((code) => (
              <option key={code} value={code}>{optionLabel(code)}</option>
            ))}
          </select>
        </Field>
      </div>

      {showDateTime && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          <Field id={`${idPrefix}-date`} label="Open on">
            <input
              id={`${idPrefix}-date`}
              type="date"
              value={filters.date}
              onChange={(e) => set('date', e.target.value)}
              className={INPUT_CLASS}
              style={INPUT_STYLE}
            />
          </Field>
          <Field id={`${idPrefix}-start`} label="Open from">
            <input
              id={`${idPrefix}-start`}
              type="time"
              value={filters.startTime}
              onChange={(e) => set('startTime', e.target.value)}
              className={INPUT_CLASS}
              style={INPUT_STYLE}
            />
          </Field>
          <Field id={`${idPrefix}-end`} label="Open until">
            <input
              id={`${idPrefix}-end`}
              type="time"
              value={filters.endTime}
              onChange={(e) => set('endTime', e.target.value)}
              className={INPUT_CLASS}
              style={INPUT_STYLE}
            />
          </Field>
        </div>
      )}

      {!showDateTime && onOpenThenChange && (
        <label className="flex items-center gap-2 font-ui text-sm mb-4" style={{ color: C.ink }}>
          <input
            type="checkbox"
            checked={openThen}
            onChange={(e) => onOpenThenChange(e.target.checked)}
          />
          Only venues open at the booking&apos;s date and time
        </label>
      )}

      {options && (
        <div className="grid grid-cols-1 gap-4 mb-4">
          <Checklist
            legend="Facilities"
            codes={options.facilities}
            selected={filters.facilities}
            onToggle={(code) => toggle('facilities', code)}
          />
          <Checklist
            legend="Accessibility"
            codes={options.accessibility}
            selected={filters.accessibility}
            onToggle={(code) => toggle('accessibility', code)}
          />
        </div>
      )}

      <button
        type="button"
        onClick={clear}
        className="csp-filter-clear px-4 py-2 rounded-sm font-ui text-sm font-medium border transition-colors duration-200"
        style={{ borderColor: C.ink, color: C.ink }}
      >
        Clear filters
      </button>
    </section>
  )
}
