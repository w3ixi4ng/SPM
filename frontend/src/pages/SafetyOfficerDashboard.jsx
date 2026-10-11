import { ChevronRight, LogOut, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import { formatSafetyWindow, listSafetyChecks, safetyCheckErrorMessage } from '../lib/safetyChecks.js'

const C = {
  ink: '#10192B', inkFaint: '#4C5A70', paper: '#F8F6F1', line: '#E3DFD3',
  teal: '#0E7C74', rose: '#B25547', green: '#3F8F5F',
}


export default function SafetyOfficerDashboard() {
  const { user, signOut } = useAuth()
  const [state, setState] = useState({ status: 'loading', events: [], error: null })

  const load = useCallback(() => {
    setState({ status: 'loading', events: [], error: null })
    listSafetyChecks().then(
      (events) => setState({ status: 'ready', events, error: null }),
      (error) => setState({ status: 'error', events: [], error: safetyCheckErrorMessage(error) }),
    )
  }, [])

  useEffect(() => {
    let active = true
    listSafetyChecks().then(
      (events) => { if (active) setState({ status: 'ready', events, error: null }) },
      (error) => {
        if (active) setState({ status: 'error', events: [], error: safetyCheckErrorMessage(error) })
      },
    )
    return () => { active = false }
  }, [])

  return (
    <div className="min-h-screen" style={{ backgroundColor: C.paper }}>
      <header className="border-b" style={{ borderColor: C.line }}>
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Logo />
          <div className="flex items-center gap-4 font-ui text-sm" style={{ color: C.inkFaint }}>
            <span>{user?.name}</span>
            <button type="button" onClick={signOut} className="inline-flex items-center gap-1.5" style={{ color: C.teal }}>
              <LogOut size={15} aria-hidden="true" /> Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-6 py-10">
        <div className="flex items-center gap-3 mb-2">
          <ShieldCheck size={26} aria-hidden="true" style={{ color: C.green }} />
          <h1 className="font-display text-3xl" style={{ color: C.ink }}>Operational safety checks</h1>
        </div>
        <p className="font-ui mb-8" style={{ color: C.inkFaint }}>
          Review events whose venue and technical arrangements are confirmed.
        </p>

        {state.status === 'loading' && <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading safety reviews…</p>}
        {state.status === 'error' && (
          <div className="font-ui text-sm" style={{ color: C.rose }}>
            <p role="alert">{state.error}</p>
            <button type="button" onClick={load} className="underline mt-2" style={{ color: C.teal }}>Try again</button>
          </div>
        )}
        {state.status === 'ready' && state.events.length === 0 && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
            No events are awaiting an operational safety check.
          </p>
        )}
        {state.status === 'ready' && state.events.length > 0 && (
          <ul className="divide-y border-y" style={{ borderColor: C.line }} aria-label="Events awaiting safety review">
            {state.events.map((event) => (
              <li key={event.id}>
                <Link
                  to={`/safety-checks/${event.id}`}
                  className="flex items-center justify-between gap-5 px-3 py-5 -mx-3 rounded-sm csp-request-row"
                  aria-label={`Review ${event.name}`}
                >
                  <span>
                    <span className="block font-ui font-medium" style={{ color: C.ink }}>{event.name}</span>
                    <span className="block font-ui text-sm" style={{ color: C.inkFaint }}>
                      {event.organiser?.name || 'Unknown organiser'} · {event.expected_attendance} attendees
                    </span>
                    <span className="block font-ui text-xs mt-1" style={{ color: C.inkFaint }}>{formatSafetyWindow(event)}</span>
                  </span>
                  <ChevronRight size={18} aria-hidden="true" style={{ color: C.teal }} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  )
}
