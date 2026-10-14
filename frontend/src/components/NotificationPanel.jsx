import { Bell, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { listNotifications, notificationErrorMessage } from '../lib/notifications.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  line: '#E3DFD3',
  teal: '#0E7C74',
  paperDim: '#F0EDE5',
}

function displayTime(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export default function NotificationPanel() {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({ status: 'loading', rows: [], error: null })

  useEffect(() => {
    let active = true
    listNotifications()
      .then((rows) => {
        if (active) setState({ status: 'ready', rows, error: null })
      })
      .catch((error) => {
        if (active) setState({ status: 'error', rows: [], error: notificationErrorMessage(error) })
      })
    return () => { active = false }
  }, [attempt])

  return (
    <section
      aria-labelledby="notifications-heading"
      className="border rounded-sm p-6 mb-8"
      style={{ borderColor: C.line }}
    >
      <div className="flex items-center gap-3 mb-4">
        <Bell size={18} aria-hidden="true" style={{ color: C.teal }} />
        <h2 id="notifications-heading" className="font-display text-xl" style={{ color: C.ink }}>
          Notifications
        </h2>
      </div>

      {state.status === 'loading' && (
        <p className="font-ui text-sm flex items-center gap-2" style={{ color: C.inkFaint }}>
          <Loader2 size={15} className="animate-spin" aria-hidden="true" /> Loading notifications…
        </p>
      )}
      {state.status === 'error' && (
        <div role="alert" className="font-ui text-sm" style={{ color: C.inkFaint }}>
          <p>{state.error}</p>
          <button type="button" className="underline mt-2" onClick={() => setAttempt((value) => value + 1)}>
            Try again
          </button>
        </div>
      )}
      {state.status === 'ready' && state.rows.length === 0 && (
        <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No notifications yet.</p>
      )}
      {state.status === 'ready' && state.rows.length > 0 && (
        <ul className="space-y-3">
          {state.rows.map((row) => (
            <li key={row.id} className="rounded-sm px-4 py-3" style={{ backgroundColor: C.paperDim }}>
              <p className="font-ui text-sm" style={{ color: C.ink }}>{row.message}</p>
              <time className="font-ui text-xs mt-1 block" style={{ color: C.inkFaint }} dateTime={row.created_at}>
                {displayTime(row.created_at)}
              </time>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
