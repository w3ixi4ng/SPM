import { Building2, Clock, MapPin, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { DAY_LABELS, optionLabel } from '../lib/venues.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  line: '#E3DFD3',
  teal: '#0E7C74',
  sky: '#3C6E96',
  rose: '#B25547',
}

function hoursSummary(hours) {
  return hours
    .map(({ day, open, close }) => `${DAY_LABELS[day]?.slice(0, 3) ?? day} ${open.slice(0, 5)}–${close.slice(0, 5)}`)
    .join(' · ')
}

function listLabels(codes) {
  return codes.map(optionLabel).join(', ')
}

function VenueRow({ venue, canEdit }) {
  return (
    <li className="py-5 first:pt-0 last:pb-0 flex items-start gap-4" style={{ borderColor: C.line }}>
      <Building2 size={20} aria-hidden="true" className="mt-0.5 shrink-0" style={{ color: C.sky }} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h3 className="font-ui text-base font-medium" style={{ color: C.ink }}>{venue.name}</h3>
          {canEdit && <Link to={`/venues/${venue.id}/edit`} className="underline" style={{ color: C.teal }} aria-label={`Edit ${venue.name}`}>Edit</Link>}
          <span className="inline-flex items-center gap-1.5 font-ui text-sm" style={{ color: C.inkFaint }}>
            <Users size={14} aria-hidden="true" />
            Capacity {venue.capacity.toLocaleString()}
          </span>
        </div>
        <p className="font-ui text-sm mt-1 flex items-center gap-1.5" style={{ color: C.inkFaint }}>
          <MapPin size={14} aria-hidden="true" className="shrink-0" />
          {venue.location}
        </p>
        <dl className="font-ui text-sm mt-3 grid gap-1" style={{ color: C.inkFaint }}>
          <div className="flex gap-2">
            <dt className="font-medium shrink-0" style={{ color: C.ink }}>Layouts</dt>
            <dd>{listLabels(venue.room_layouts)}</dd>
          </div>
          {venue.facilities.length > 0 && (
            <div className="flex gap-2">
              <dt className="font-medium shrink-0" style={{ color: C.ink }}>Facilities</dt>
              <dd>{listLabels(venue.facilities)}</dd>
            </div>
          )}
          {venue.accessibility.length > 0 && (
            <div className="flex gap-2">
              <dt className="font-medium shrink-0" style={{ color: C.ink }}>Accessibility</dt>
              <dd>{listLabels(venue.accessibility)}</dd>
            </div>
          )}
          <div className="flex gap-2">
            <dt className="shrink-0" style={{ color: C.ink }}>
              <Clock size={14} aria-label="Opening hours" className="mt-0.5" />
            </dt>
            <dd>{hoursSummary(venue.operating_hours)}</dd>
          </div>
        </dl>
        {venue.description && (
          <p className="font-ui text-sm leading-relaxed mt-3 max-w-md" style={{ color: C.inkFaint }}>
            {venue.description}
          </p>
        )}
      </div>
    </li>
  )
}

// Read-only venue list, shared by the venue staff and coordinator dashboards.
export default function VenueList({ venues, loading, error, onRetry, emptyMessage, canEdit = false }) {
  if (loading) {
    return <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading venues…</p>
  }

  if (error) {
    return (
      <div role="alert" className="font-ui text-sm" style={{ color: C.rose }}>
        {error}{' '}
        <button
          type="button"
          onClick={onRetry}
          className="underline"
          style={{ color: C.teal }}
        >
          Try again
        </button>
      </div>
    )
  }

  if (!venues.length) {
    return <p className="font-ui text-sm" style={{ color: C.inkFaint }}>{emptyMessage}</p>
  }

  return (
    <ul className="divide-y" aria-label="Venues">
      {venues.map((venue) => <VenueRow key={venue.id} venue={venue} canEdit={canEdit} />)}
    </ul>
  )
}
