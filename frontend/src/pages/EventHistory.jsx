import { useEffect, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import { describeEntry, entryActor, entryLines, entryTime, loadEventHistory } from '../lib/eventHistory.js'

// S-82: who changed or decided what on an event, and when. Its own screen
// rather than a slide-over: a long list the reader scans and compares.
// Read-only by design -- nothing here can change or remove an entry.

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F1EEE6',
  line: '#E3DFD3',
  teal: '#0E7C74',
  sky: '#3C6E96',
  rose: '#B25547',
}

function backLink(role, id) {
  if (role === 'event_coordinator') return { to: `/coordinator/events/${id}`, label: 'Back to event' }
  if (role === 'safety_officer') return { to: '/dashboard/safety-officer', label: 'Back to safety checks' }
  return { to: '/dashboard/event-coordinator-lead', label: 'Back to dashboard' }
}

function errorMessage(error) {
  if (error?.status === 404) {
    return "This event's history isn't available to you. It may have been reassigned, or it hasn't reached you yet."
  }
  return error?.message || "We couldn't load the change history. Try again in a moment."
}

function Entry({ entry, people }) {
  const lines = entryLines(entry, people)
  return (
    <li className="py-5 grid grid-cols-1 sm:grid-cols-4 gap-1 sm:gap-6" style={{ borderColor: C.line }}>
      <p className="font-ui text-xs pt-0.5" style={{ color: C.inkFaint }}>
        <time dateTime={entry.occurred_at}>{entryTime(entry)}</time>
      </p>
      <div className="sm:col-span-3 min-w-0">
        <p className="font-ui text-base font-medium" style={{ color: C.ink }}>{describeEntry(entry, people)}</p>
        <p className="font-ui text-sm mt-0.5" style={{ color: C.inkFaint }}>{entryActor(entry)}</p>
        {lines.length > 0 && (
          <ul className="font-ui text-sm mt-2 space-y-0.5" style={{ color: C.ink }}>
            {lines.map((line) => <li key={line}>{line}</li>)}
          </ul>
        )}
      </div>
    </li>
  )
}

export default function EventHistory() {
  const { id } = useParams()
  const { user } = useAuth()
  const [state, setState] = useState({ status: 'loading', history: null, error: null })

  useEffect(() => {
    let active = true
    loadEventHistory(user?.role, id).then(
      (history) => { if (active) setState({ status: 'ready', history, error: null }) },
      (error) => { if (active) setState({ status: 'error', history: null, error: errorMessage(error) }) },
    )
    return () => { active = false }
  }, [id, user?.role])

  const back = backLink(user?.role, id)
  const { history } = state

  return (
    <div className="font-ui min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        .csp-link:focus-visible { outline: 2px solid ${C.teal}; outline-offset: 2px; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
        }
      `}</style>
      <div className="w-full max-w-3xl mx-auto">
        <header className="flex items-center justify-between gap-6 mb-10">
          <Logo />
          <Link to={back.to} className="csp-link inline-flex items-center gap-2 font-ui text-sm transition-colors duration-200" style={{ color: C.ink }}>
            <ArrowLeft size={15} aria-hidden="true" />
            {back.label}
          </Link>
        </header>

        <h1 className="font-display text-3xl mb-2" style={{ color: C.ink }}>Change history</h1>
        {history?.event_name && (
          <p className="font-ui text-base mb-1" style={{ color: C.ink }}>{history.event_name}</p>
        )}
        <p className="font-ui text-sm leading-relaxed max-w-md mb-8" style={{ color: C.inkFaint }}>
          {user?.role === 'safety_officer'
            ? 'Attendance, venue, layout, access and equipment changes, and every safety decision. Newest first, in Singapore time.'
            : 'Every submission, decision, assignment, edit, venue and safety step. Newest first, in Singapore time.'}
        </p>

        {state.status === 'loading' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading the change history…</p>
        )}
        {state.status === 'error' && (
          <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>{state.error}</p>
        )}
        {state.status === 'ready' && history.entries.length === 0 && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Nothing has been recorded for this event yet.</p>
        )}
        {state.status === 'ready' && history.entries.length > 0 && (
          <ol aria-label="Change history" className="rise-in divide-y border-t border-b" style={{ borderColor: C.line }}>
            {history.entries.map((entry) => <Entry key={entry.id} entry={entry} people={history.people} />)}
          </ol>
        )}
      </div>
    </div>
  )
}
