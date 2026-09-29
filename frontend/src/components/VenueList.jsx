import { Building2, CalendarDays, Clock, MapPin, Pencil, Users } from 'lucide-react'
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

function VenueRow({ venue, canEdit, canViewAvailability }) {
  return (
    <li className="py-5 first:pt-0 last:pb-0 flex items-start gap-4" style={{ borderColor: C.line }}>
      <Building2 size={20} aria-hidden="true" className="mt-0.5 shrink-0" style={{ color: C.sky }} />
      <div className="min-w-0 flex-1">
        {/* What the venue is on the left; its size, and what can be done with
            it, on the right under the capacity. */}
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
          <div className="min-w-0">
            <h3 className="font-ui text-base font-medium" style={{ color: C.ink }}>{venue.name}</h3>
            <p className="font-ui text-sm mt-1 flex items-center gap-1.5" style={{ color: C.inkFaint }}>
              <MapPin size={14} aria-hidden="true" className="shrink-0" />
              {venue.location}
            </p>
          </div>
          <div className="flex flex-col items-start sm:items-end gap-1.5">
            <span className="inline-flex items-center gap-1.5 font-ui text-sm" style={{ color: C.inkFaint }}>
              <Users size={14} aria-hidden="true" />
              Capacity {venue.capacity.toLocaleString()}
            </span>
            {(canViewAvailability || canEdit) && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-ui text-sm font-medium">
                {canViewAvailability && (
                  <Link
                    to={`/venues/${venue.id}/availability`}
                    className="inline-flex items-center gap-1.5 rounded-sm transition-colors duration-200"
                    style={{ color: C.teal }}
                    aria-label={`Availability for ${venue.name}`}
                  >
                    <CalendarDays size={15} aria-hidden="true" />
                    Availability
                  </Link>
                )}
                {canEdit && (
                  <Link
                    to={`/venues/${venue.id}/edit`}
                    className="inline-flex items-center gap-1.5 rounded-sm transition-colors duration-200"
                    style={{ color: C.teal }}
                    aria-label={`Edit ${venue.name}`}
                  >
                    <Pencil size={14} aria-hidden="true" />
                    Edit
                  </Link>
                )}
              </div>
            )}
          </div>
        </div>
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
export default function VenueList({
  venues, loading, error, onRetry, emptyMessage, canEdit = false, canViewAvailability = false,
}) {
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
      {venues.map((venue) => (
        <VenueRow key={venue.id} venue={venue} canEdit={canEdit} canViewAvailability={canViewAvailability} />
      ))}
    </ul>
  )
}
