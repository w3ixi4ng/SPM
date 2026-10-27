import { useEffect, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import { describeRegistration, formatEventWhen, listPublicEvents } from '../lib/registration.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  teal: '#0E7C74',
  tealBright: '#149E92',
  rose: '#B25547',
}

export default function PublicEvents() {
  const auth = useAuth()
  const [load, setLoad] = useState({ status: 'loading', events: [], error: null })

  useEffect(() => {
    let active = true
    listPublicEvents()
      .then((events) => { if (active) setLoad({ status: 'ready', events, error: null }) })
      .catch((error) => {
        if (active) setLoad({ status: 'error', events: [], error: error.message })
      })
    return () => { active = false }
  }, [])

  return (
    <div className="font-ui min-h-screen" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        .csp-row { transition: color 0.2s; }
        .csp-row:hover .csp-row-name { color: ${C.teal}; }
        .csp-row:focus-visible, .csp-ghost:focus-visible {
          outline: 2px solid ${C.tealBright};
          outline-offset: 2px;
        }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
        }
      `}</style>

      <header className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-between gap-6">
        <Logo />
        <Link
          to={auth.status === 'authenticated' ? '/dashboard' : '/login'}
          className="csp-ghost px-5 py-3 rounded-sm font-ui text-sm font-medium border"
          style={{ borderColor: C.ink, color: C.ink }}
        >
          {auth.status === 'authenticated' ? 'Your dashboard' : 'Sign in'}
        </Link>
      </header>

      <main className="max-w-6xl mx-auto px-6 pb-20">
        <div className="rise-in max-w-3xl mb-10">
          <h1 className="text-4xl sm:text-5xl font-display leading-tight mb-4" style={{ color: C.ink }}>
            Upcoming events
          </h1>
          <p className="font-ui text-base leading-relaxed max-w-md" style={{ color: C.inkFaint }}>
            Every confirmed event, with when it runs, where, and when registration opens and closes.
          </p>
        </div>

        {load.status === 'loading' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading events…</p>
        )}
        {load.status === 'error' && (
          <p role="alert" className="font-ui text-sm max-w-md" style={{ color: C.rose }}>
            {load.error}
          </p>
        )}
        {load.status === 'ready' && load.events.length === 0 && (
          <p className="font-ui text-sm max-w-md" style={{ color: C.inkFaint }}>
            No events are confirmed yet. Events appear here once they are.
          </p>
        )}
        {load.events.length > 0 && (
          <ul aria-label="Upcoming events" className="max-w-3xl divide-y border-t border-b" style={{ borderColor: C.line }}>
            {load.events.map((event) => {
              const { period, status } = describeRegistration(event)
              return (
                <li key={event.id}>
                  <Link
                    to={`/public/events/${event.id}`}
                    className="csp-row flex items-center justify-between gap-6 py-5"
                  >
                    <div>
                      <p className="csp-row-name font-ui text-base font-medium" style={{ color: C.ink }}>
                        {event.name}
                      </p>
                      <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
                        {formatEventWhen(event)}
                        {event.venues.length > 0 && ` · ${event.venues.join(', ')}`}
                      </p>
                      <p className="font-ui text-xs mt-1" style={{ color: C.inkFaint }}>
                        {period ?? status}
                      </p>
                    </div>
                    <ArrowRight size={18} aria-hidden="true" style={{ color: C.inkFaint, flexShrink: 0 }} />
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </main>
    </div>
  )
}
