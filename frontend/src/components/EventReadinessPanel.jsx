import { CheckCircle2, CircleDashed, Construction } from 'lucide-react'
import { useEffect, useState } from 'react'
import { loadEventReadiness } from '../lib/eventReadiness.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  line: '#E3DFD3',
  green: '#3F8F5F',
  amber: '#B5842B',
  sky: '#3C6E96',
  rose: '#B25547',
}

const META = {
  complete: { label: 'Complete', color: C.green, Icon: CheckCircle2 },
  outstanding: { label: 'Outstanding', color: C.amber, Icon: CircleDashed },
  unavailable: { label: 'Not available yet', color: C.sky, Icon: Construction },
}

export default function EventReadinessPanel({ event }) {
  const [state, setState] = useState({ status: 'loading', readiness: null })

  useEffect(() => {
    let active = true
    setState({ status: 'loading', readiness: null })
    loadEventReadiness(event.id, event)
      .then((readiness) => {
        if (active) setState({ status: 'ready', readiness })
      })
      .catch(() => {
        if (active) setState({ status: 'error', readiness: null })
      })
    return () => { active = false }
  }, [event])

  return (
    <section className="border rounded-sm p-7 sm:p-8 mt-8" style={{ borderColor: C.line }} aria-labelledby="event-readiness-heading">
      <h2 id="event-readiness-heading" className="font-display text-2xl mb-2" style={{ color: C.ink }}>
        Event readiness
      </h2>
      {state.status === 'loading' && <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Checking current readiness…</p>}
      {state.status === 'error' && (
        <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>
          We couldn&apos;t load current readiness. Reload the page to try again.
        </p>
      )}
      {state.status === 'ready' && (
        <>
          <p role="status" className="font-ui text-sm mb-5" style={{ color: C.inkFaint }}>
            {state.readiness.summary.complete} of {state.readiness.summary.available} implemented areas complete
          </p>
          <ul className="divide-y" aria-label="Readiness indicators" style={{ borderColor: C.line }}>
            {state.readiness.areas.map((area) => {
              const { label, color, Icon } = META[area.state]
              return (
                <li key={area.id} className="py-3 first:pt-0 last:pb-0 flex items-start justify-between gap-5">
                  <div>
                    <p className="font-ui text-sm font-medium" style={{ color: C.ink }}>{area.label}</p>
                    <p className="font-ui text-xs mt-0.5" style={{ color: C.inkFaint }}>{area.detail}</p>
                    {area.items?.length > 0 && (
                      <ul className="mt-2 space-y-1" aria-label={`${area.label} preparation statuses`}>
                        {area.items.map((item) => (
                          <li key={item.id} className="font-ui text-xs flex gap-2" style={{ color: C.inkFaint }}>
                            <span>{item.label}</span><span aria-hidden="true">/</span><strong>{item.status}</strong>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <span className="inline-flex items-center gap-1.5 font-ui text-xs shrink-0" style={{ color }}>
                    <Icon size={15} aria-hidden="true" />
                    {label}
                  </span>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </section>
  )
}
