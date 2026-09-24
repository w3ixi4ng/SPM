import { useEffect, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import { eventErrorMessage, eventResponseToForm, getAssignedEventRequest } from '../lib/eventRequests.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
  green: '#3F8F5F',
}

function Field({ label, value }) {
  return (
    <div>
      <p className="font-ui text-xs uppercase tracking-wide" style={{ color: C.inkFaint }}>
        {label}
      </p>
      <p className="font-ui text-base mt-1" style={{ color: C.ink }}>
        {value || '—'}
      </p>
    </div>
  )
}

function equipmentSummary(equipmentRequests) {
  const entries = Object.entries(equipmentRequests ?? {})
  if (entries.length === 0) return null
  return entries.map(([name, quantity]) => `${quantity}× ${name}`).join(', ')
}

export default function EventCoordinatorEventDetail() {
  const { id } = useParams()
  const [state, setState] = useState({ status: 'loading', form: null, error: null })

  useEffect(() => {
    let active = true
    setState({ status: 'loading', form: null, error: null })

    getAssignedEventRequest(id)
      .then((event) => {
        if (active) setState({ status: 'ready', form: eventResponseToForm(event), error: null })
      })
      .catch((error) => {
        if (active) setState({ status: 'error', form: null, error: eventErrorMessage(error) })
      })

    return () => {
      active = false
    }
  }, [id])

  return (
    <div className="min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <div className="w-full max-w-3xl mx-auto">
        <header className="flex items-center justify-between gap-6 mb-10">
          <Logo />
          <Link
            to="/dashboard/event-coordinator"
            className="inline-flex items-center gap-2 font-ui text-sm"
            style={{ color: C.ink }}
          >
            <ArrowLeft size={15} aria-hidden="true" />
            Back to workspace
          </Link>
        </header>

        {state.status === 'loading' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
            Loading the event request…
          </p>
        )}

        {state.status === 'error' && (
          <p className="font-ui text-sm" style={{ color: C.inkFaint }}>
            {state.error}
          </p>
        )}

        {state.status === 'ready' && (
          <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
            <div
              className="inline-flex items-center gap-2 text-xs font-ui px-3 py-1 rounded-sm mb-6"
              style={{ backgroundColor: 'rgba(63,143,95,0.12)', color: C.green }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.green }} />
              Assigned to you
            </div>

            <h1 className="font-display text-3xl mb-8" style={{ color: C.ink }}>
              {state.form.name || 'Untitled event request'}
            </h1>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <Field label="Purpose" value={state.form.purpose} />
              <Field label="Venue" value={state.form.venue} />
              <Field
                label="Starts"
                value={state.form.startDate && `${state.form.startDate} at ${state.form.startTime}`}
              />
              <Field
                label="Ends"
                value={state.form.endDate && `${state.form.endDate} at ${state.form.endTime}`}
              />
              <Field label="Expected attendance" value={state.form.attendance} />
              <Field label="Equipment requested" value={equipmentSummary(state.form.equipmentRequests)} />
              <Field label="Accessibility requirements" value={state.form.accessibility} />
              <Field label="Other requirements" value={state.form.specialRequirements} />
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
