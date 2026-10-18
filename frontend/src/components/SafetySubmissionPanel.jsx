import { CircleDashed, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  buildSubmissionReadiness,
  getSubmissionReadiness,
  submissionErrorMessage,
  submitForSafetyCheck,
} from '../lib/safetySubmission.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
  amber: '#B5842B',
  green: '#3F8F5F',
  rose: '#B25547',
}

function OutstandingList({ items }) {
  return (
    <ul className="divide-y mt-4" aria-label="Outstanding arrangements" style={{ borderColor: C.line }}>
      {items.map((item) => (
        <li key={item.key} className="py-3 first:pt-0 last:pb-0 flex items-start justify-between gap-5">
          <p className="font-ui text-sm" style={{ color: C.ink }}>{item.label}</p>
          <span className="inline-flex items-center gap-1.5 font-ui text-xs shrink-0" style={{ color: C.amber }}>
            <CircleDashed size={15} aria-hidden="true" />
            {item.statusLabel}
          </span>
        </li>
      ))}
    </ul>
  )
}

// S-17: shown to the assigned Coordinator while the event is in planning.
// The list is the server's own check, so it is exactly what Submit refuses.
export default function SafetySubmissionPanel({ eventId, onSubmitted }) {
  const [readiness, setReadiness] = useState({ status: 'loading', view: null })
  const [submit, setSubmit] = useState({ status: 'idle', error: null })

  const load = useCallback(() => {
    let active = true
    setReadiness({ status: 'loading', view: null })
    getSubmissionReadiness(eventId).then(
      (result) => { if (active) setReadiness({ status: 'ready', view: buildSubmissionReadiness(result) }) },
      () => { if (active) setReadiness({ status: 'error', view: null }) },
    )
    return () => { active = false }
  }, [eventId])

  useEffect(load, [load])

  async function handleSubmit() {
    setSubmit({ status: 'saving', error: null })
    try {
      const updated = await submitForSafetyCheck(eventId)
      setSubmit({ status: 'idle', error: null })
      onSubmitted(updated)
    } catch (error) {
      if (error.outstanding) {
        setReadiness({
          status: 'ready',
          view: buildSubmissionReadiness({ ready: false, outstanding: error.outstanding }),
        })
      }
      setSubmit({ status: 'idle', error: submissionErrorMessage(error) })
    }
  }

  const view = readiness.view
  return (
    <section className="border rounded-sm p-7 sm:p-8 mt-8" style={{ borderColor: C.line }} aria-labelledby="safety-submission-heading">
      <h2 id="safety-submission-heading" className="font-display text-2xl mb-2" style={{ color: C.ink }}>
        Operational Safety Check
      </h2>
      <p className="font-ui text-sm leading-relaxed max-w-md" style={{ color: C.inkFaint }}>
        Submit once every venue booking is approved and Technical Support has signed off the equipment. The Safety Officer then confirms the event.
      </p>

      {readiness.status === 'loading' && (
        <p className="font-ui text-sm mt-4" style={{ color: C.inkFaint }}>Checking the arrangements…</p>
      )}
      {readiness.status === 'error' && (
        <p role="alert" className="font-ui text-sm mt-4" style={{ color: C.rose }}>
          We couldn&apos;t check the arrangements. Reload the page to try again.
        </p>
      )}
      {readiness.status === 'ready' && view.items.length > 0 && <OutstandingList items={view.items} />}
      {readiness.status === 'ready' && view.canSubmit && (
        <p className="inline-flex items-center gap-1.5 font-ui text-sm mt-4" style={{ color: C.green }}>
          <ShieldCheck size={16} aria-hidden="true" />
          Every mandatory arrangement is complete
        </p>
      )}

      {submit.error && (
        <p role="alert" className="font-ui text-sm mt-4" style={{ color: C.rose }}>{submit.error}</p>
      )}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={readiness.status === 'loading' || submit.status === 'saving'}
        className="mt-5 px-5 py-3 rounded-sm font-ui font-medium text-sm transition-transform duration-200 hover:-translate-y-0.5 disabled:opacity-60 disabled:hover:translate-y-0"
        style={{ backgroundColor: C.teal, color: C.paper }}
      >
        {submit.status === 'saving' ? 'Submitting…' : 'Submit for safety check'}
      </button>
    </section>
  )
}
