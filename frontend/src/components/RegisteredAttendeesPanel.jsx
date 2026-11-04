import { RotateCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  attendeeCountLabel,
  formatRegistrationMoment,
  listEventAttendees,
  waitingListLabel,
} from '../lib/registration.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  line: '#E3DFD3',
}

// A registration time is a real instant; show it in Singapore wall-clock
// time, like every other time on the page.
function singaporeTime(instant) {
  return new Date(new Date(instant).getTime() + 8 * 60 * 60 * 1000).toISOString()
}

function PersonRow({ person, when }) {
  return (
    <li
      className="py-3 flex flex-wrap items-baseline justify-between gap-2"
      style={{ borderColor: C.line }}
    >
      <div>
        <p className="font-ui text-sm font-medium" style={{ color: C.ink }}>
          {person.name || 'Name not on record'}
        </p>
        <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
          {person.email || 'Email not on record'}
        </p>
      </div>
      <p className="font-ui text-xs" style={{ color: C.inkFaint }}>{when}</p>
    </li>
  )
}

// S-48: who holds a place at this confirmed event, earliest first. S-50: and
// who is on its waiting list. S-57: shown to the event's Organiser and to its
// assigned Coordinator -- the composite decides which -- and re-read with
// Refresh list, so withdrawals show without reloading the page. `children`
// sits under the heading: the Organiser's close/reopen control.
export default function RegisteredAttendeesPanel({ eventId, children }) {
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [state, setState] = useState({ status: 'loading', list: null })

  useEffect(() => {
    let active = true
    // A refresh keeps the current list on screen until the new one arrives.
    setState((current) => (
      current.list ? { ...current, refreshing: true } : { status: 'loading', list: null }
    ))
    listEventAttendees(eventId)
      .then((list) => { if (active) setState({ status: 'ready', list }) })
      .catch((error) => {
        if (active) setState({ status: 'error', list: null, message: error.message })
      })
    return () => { active = false }
  }, [eventId, loadAttempt])

  const refresh = () => setLoadAttempt((n) => n + 1)

  return (
    <section aria-labelledby="registered-attendees-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-3 mb-1">
        <h2
          id="registered-attendees-heading"
          className="block font-display text-s font-medium"
          style={{ color: C.ink }}
        >
          Registered attendees
        </h2>
        {state.status === 'ready' && (
          <button
            type="button"
            onClick={refresh}
            disabled={state.refreshing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm border font-ui text-sm font-medium transition-colors duration-200"
            style={{ borderColor: C.line, color: C.ink }}
          >
            <RotateCw size={14} aria-hidden="true" />
            {state.refreshing ? 'Refreshing…' : 'Refresh list'}
          </button>
        )}
      </div>
      {children}
      {state.status === 'loading' && (
        <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading attendees…</p>
      )}
      {state.status === 'error' && (
        <div className="font-ui text-sm" style={{ color: C.inkFaint }}>
          <p role="alert">We couldn&apos;t load who has registered. {state.message}</p>
          <button
            type="button"
            onClick={refresh}
            className="mt-3 px-4 py-2 rounded-sm border font-medium"
            style={{ borderColor: C.ink, color: C.ink }}
          >
            Try again
          </button>
        </div>
      )}
      {state.status === 'ready' && (
        <>
          <p className="font-ui text-sm mb-3" style={{ color: C.inkFaint }} aria-live="polite">
            {attendeeCountLabel(state.list.count)}
          </p>
          {state.list.attendees.length > 0 && (
            <ul className="divide-y border-t border-b" style={{ borderColor: C.line }}>
              {state.list.attendees.map((attendee) => (
                <PersonRow
                  key={attendee.attendee_id}
                  person={attendee}
                  when={`Registered ${formatRegistrationMoment(singaporeTime(attendee.registered_at))}`}
                />
              ))}
            </ul>
          )}
          <section aria-labelledby="waiting-list-heading" className="mt-6">
            <h3
              id="waiting-list-heading"
              className="font-ui text-sm font-medium mb-1"
              style={{ color: C.ink }}
            >
              Waiting list
            </h3>
            <p className="font-ui text-sm mb-3" style={{ color: C.inkFaint }}>
              {waitingListLabel(state.list.waiting_list?.length ?? 0)}
            </p>
            {state.list.waiting_list?.length > 0 && (
              <ol className="divide-y border-t border-b" style={{ borderColor: C.line }}>
                {state.list.waiting_list.map((person) => (
                  <PersonRow
                    key={person.attendee_id}
                    person={person}
                    when={`Joined ${formatRegistrationMoment(singaporeTime(person.joined_at))}`}
                  />
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </section>
  )
}
