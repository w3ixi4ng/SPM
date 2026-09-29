import { CalendarCheck, ListChecks, LogOut, MessagesSquare } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import useVenueList from '../components/useVenueList.js'
import VenueFilters from '../components/VenueFilters.jsx'
import VenueList from '../components/VenueList.jsx'
import { getRoleAccess } from '../lib/access.js'
import { eventErrorMessage, eventStatusMeta, listAssignedEventRequests } from '../lib/eventRequests.js'
import { emptyVenueFilters, filterVenues, getVenueOptions } from '../lib/venues.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F0EDE5',
  line: '#E3DFD3',
  teal: '#0E7C74',
  sky: '#3C6E96',
  green: '#3F8F5F',
}

const UPCOMING_AREAS = [
  {
    icon: ListChecks,
    title: 'Timeline coordination',
    description: 'Track logistics milestones across a request, from booking to day-of.',
  },
  {
    icon: MessagesSquare,
    title: 'Vendor communication log',
    description: 'Keep a record of vendor and venue conversations tied to an event.',
  },
]

const TABS = [
  { id: 'venues', label: 'Venues' },
  { id: 'events', label: 'Events' },
]

function Tabs({ active, onSelect }) {
  const refs = useRef({})

  // Arrow keys, Home and End move between tabs, per the ARIA tabs pattern.
  function onKeyDown(event) {
    const index = TABS.findIndex((tab) => tab.id === active)
    const next = {
      ArrowRight: (index + 1) % TABS.length,
      ArrowLeft: (index - 1 + TABS.length) % TABS.length,
      Home: 0,
      End: TABS.length - 1,
    }[event.key]
    if (next === undefined) return
    event.preventDefault()
    onSelect(TABS[next].id)
    refs.current[TABS[next].id]?.focus()
  }

  return (
    <div
      role="tablist"
      aria-label="Coordinator workspace"
      className="flex gap-6 border-b mb-8"
      style={{ borderColor: C.line }}
      onKeyDown={onKeyDown}
    >
      {TABS.map((tab) => {
        const selected = tab.id === active
        return (
          <button
            key={tab.id}
            ref={(element) => { refs.current[tab.id] = element }}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onSelect(tab.id)}
            className="csp-tab font-ui text-sm font-medium pb-3 -mb-px border-b-2"
            style={{
              borderColor: selected ? C.teal : 'transparent',
              color: selected ? C.ink : C.inkFaint,
            }}
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}

export default function EventCoordinatorDashboard({ role }) {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const access = getRoleAccess(role)
  const { venues, loading, error, reload } = useVenueList()
  // S-34: the Venues tab's filters start empty -- there is no event here.
  const [venueFilters, setVenueFilters] = useState(emptyVenueFilters)
  const [venueOptions, setVenueOptions] = useState(null)

  useEffect(() => {
    let active = true
    getVenueOptions()
      .then((options) => { if (active) setVenueOptions(options) })
      .catch(() => { if (active) setVenueOptions(null) })
    return () => { active = false }
  }, [])

  const filteredVenues = filterVenues(venues, venueFilters)
  const [assigned, setAssigned] = useState({ status: 'loading', events: [], error: null })
  // Kept in the URL so a reload or a shared link opens the same tab.
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = TABS.some((tab) => tab.id === searchParams.get('tab'))
    ? searchParams.get('tab')
    : TABS[0].id

  function selectTab(id) {
    setSearchParams(id === TABS[0].id ? {} : { tab: id }, { replace: true })
  }

  useEffect(() => {
    let active = true
    listAssignedEventRequests()
      .then((events) => {
        if (active) setAssigned({ status: 'ready', events, error: null })
      })
      .catch((error) => {
        if (active) setAssigned({ status: 'error', events: [], error: eventErrorMessage(error) })
      })
    return () => {
      active = false
    }
  }, [])

  async function handleSignOut() {
    await signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
        }

        .csp-signout-btn {
          border-color: ${C.ink};
          color: ${C.ink};
          transition: background-color 0.2s, color 0.2s;
        }
        .csp-signout-btn:hover { background-color: ${C.ink}; color: ${C.paper}; }
        .csp-signout-btn:focus-visible,
        .csp-tab:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
        .csp-tab { transition: color 0.2s; }
        .csp-tab:hover { color: ${C.ink} !important; }
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
            Coordinator workspace
          </h1>
          <p className="font-ui text-base leading-relaxed" style={{ color: C.inkFaint }}>
            {access.description}
          </p>
          <p className="font-ui text-xs mt-3" style={{ color: C.inkFaint }}>
            {user.name} · {user.email}
          </p>
        </div>

        <div className="max-w-3xl">
          <Tabs active={activeTab} onSelect={selectTab} />

          <div
            role="tabpanel"
            id="panel-venues"
            aria-labelledby="tab-venues"
            hidden={activeTab !== 'venues'}
          >
            {venues.length > 0 && (
              <VenueFilters
                idPrefix="venue-filter"
                filters={venueFilters}
                onChange={setVenueFilters}
                options={venueOptions}
              />
            )}
            <VenueList
              venues={filteredVenues}
              loading={loading}
              error={error}
              onRetry={reload}
              emptyMessage={venues.length > 0
                ? 'No venues match these filters.'
                : 'No venues have been added yet. Venue staff add them from their workspace.'}
            />
          </div>

          <div
            role="tabpanel"
            id="panel-events"
            aria-labelledby="tab-events"
            hidden={activeTab !== 'events'}
          >
            <section className="border rounded-sm p-7 sm:p-8 mb-10" style={{ borderColor: C.line }}>
              <h2 className="font-display text-2xl mb-6" style={{ color: C.ink }}>
                Assigned requests
              </h2>

              {assigned.status === 'loading' && (
                <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                  Loading your assigned requests…
                </p>
              )}

              {assigned.status === 'error' && (
                <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                  {assigned.error}
                </p>
              )}

              {assigned.status === 'ready' && assigned.events.length === 0 && (
                <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                  No event requests have been routed to you yet.
                </p>
              )}

              {assigned.status === 'ready' && assigned.events.length > 0 && (
                <ul className="divide-y" style={{ borderColor: C.line }}>
                  {assigned.events.map((event) => {
                    const { label: statusLabel, color: statusColor } = eventStatusMeta(event.status)
                    return (
                      <li key={event.id} className="py-4 first:pt-0 last:pb-0">
                        <Link
                          to={`/coordinator/events/${event.id}`}
                          className="flex items-start gap-4 group"
                        >
                          <CalendarCheck
                            size={20}
                            aria-hidden="true"
                            className="mt-0.5 shrink-0"
                            style={{ color: C.sky }}
                          />
                          <div className="min-w-0 flex-1">
                            <h3
                              className="font-ui text-base font-medium group-hover:underline"
                              style={{ color: C.ink }}
                            >
                              {event.name || 'Untitled event request'}
                            </h3>
                            <p className="font-ui text-sm mt-0.5" style={{ color: C.inkFaint }}>
                              {event.start_date} at {event.start_time?.slice(0, 5)}{event.venue && ` · ${event.venue}`}
                            </p>
                          </div>
                          <span
                            className="font-ui text-xs font-medium px-2.5 py-1 rounded-sm shrink-0"
                            style={{ color: statusColor, backgroundColor: `${statusColor}1F` }}
                          >
                            {statusLabel}
                          </span>
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              )}
            </section>

            <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
              <p className="font-ui text-xs uppercase tracking-widest mb-3" style={{ color: C.teal }}>
                Coming to this workspace
              </p>
              <h2 className="font-display text-2xl mb-6" style={{ color: C.ink }}>
                Coordination tools, on the way
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
        </div>
      </div>
    </div>
  )
}
