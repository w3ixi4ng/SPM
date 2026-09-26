import { CalendarDays, ListChecks, LogOut, MapPin, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import useVenueList from '../components/useVenueList.js'
import VenueList from '../components/VenueList.jsx'
import { getRoleAccess, hasPermission, PERMISSIONS } from '../lib/access.js'

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

export default function VenueStaffDashboard({ role }) {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const access = getRoleAccess(role)
  const canAdd = hasPermission(role, PERMISSIONS.CREATE_VENUE)
  const { venues, loading, error, reload } = useVenueList()
  const location = useLocation()
  // Set by the venue form after a save. Read once, then cleared from history
  // so a reload or Back does not announce the same save again.
  const [notice, setNotice] = useState(location.state?.notice ?? null)

  useEffect(() => {
    if (location.state?.notice) {
      navigate(location.pathname, { replace: true, state: null })
    }
  }, [location, navigate])

  useEffect(() => {
    if (!notice) return undefined
    const timer = setTimeout(() => setNotice(null), 4000)
    return () => clearTimeout(timer)
  }, [notice])

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
          .csp-primary-btn:hover { transform: none; }
        }

        .csp-signout-btn {
          border-color: ${C.ink};
          color: ${C.ink};
          transition: background-color 0.2s, color 0.2s;
        }
        .csp-signout-btn:hover { background-color: ${C.ink}; color: ${C.paper}; }
        .csp-signout-btn:focus-visible,
        .csp-primary-btn:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
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
              <Link
                to="/venues/new"
                className="csp-primary-btn inline-flex items-center gap-2 px-5 py-3 rounded-sm font-ui font-medium transition-transform duration-200 hover:-translate-y-0.5"
                style={{ backgroundColor: C.teal, color: C.paper }}
              >
                <Plus size={16} aria-hidden="true" />
                Add venue
              </Link>
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
          <ul className="divide-y">
            {UPCOMING_AREAS.map(({ icon: Icon, title, description }) => (
              <li
                key={title}
                className="py-4 first:pt-0 last:pb-0 flex items-start gap-4"
                style={{ borderColor: C.line }}
              >
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
  )
}
