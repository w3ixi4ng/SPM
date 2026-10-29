import { ArrowLeft, CheckCircle2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  decideSafetyCheck,
  formatSafetyWindow,
  getSafetyCheck,
  safetyCheckErrorMessage,
} from '../lib/safetyChecks.js'

const C = {
  ink: '#10192B', inkFaint: '#4C5A70', paper: '#F8F6F1', paperDim: '#F0EDE5',
  line: '#E3DFD3', teal: '#0E7C74', rose: '#B25547', green: '#3F8F5F',
}

const DECISIONS = [
  { value: 'approved', label: 'Approve' },
  { value: 'rejected', label: 'Reject safety arrangement' },
  { value: 'changes_requested', label: 'Request changes' },
]

const label = (value) => String(value || '').replaceAll('_', ' ')


function Evidence({ detail }) {
  const { event, organiser, confirmed_venues, technical_support, technical_support_notes, equipment_requirements } = detail
  return (
    <div className="space-y-8">
      <section>
        <h2 className="font-display text-xl mb-3" style={{ color: C.ink }}>Event and organiser</h2>
        <dl className="grid sm:grid-cols-2 gap-x-8 gap-y-3 font-ui text-sm">
          <div><dt style={{ color: C.inkFaint }}>Organiser</dt><dd>{organiser?.name || 'Unknown organiser'}</dd></div>
          <div><dt style={{ color: C.inkFaint }}>Attendance</dt><dd>{event.expected_attendance}</dd></div>
          <div className="sm:col-span-2"><dt style={{ color: C.inkFaint }}>Schedule</dt><dd>{formatSafetyWindow(event)}</dd></div>
          <div className="sm:col-span-2"><dt style={{ color: C.inkFaint }}>Purpose</dt><dd>{event.purpose}</dd></div>
          <div className="sm:col-span-2"><dt style={{ color: C.inkFaint }}>Special requirements</dt><dd>{event.special_requirements || 'None recorded'}</dd></div>
        </dl>
      </section>

      <section>
        <h2 className="font-display text-xl mb-3" style={{ color: C.ink }}>Confirmed venues</h2>
        {confirmed_venues.length === 0 ? <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No confirmed venue was returned.</p> : (
          <div className="space-y-3">
            {confirmed_venues.map((venue) => (
              <article key={venue.booking_id} className="border rounded-sm p-4 font-ui text-sm" style={{ borderColor: C.line }}>
                <h3 className="font-medium mb-2">{venue.name}</h3>
                <p>{venue.location}</p>
                <p>Capacity: {venue.capacity}</p>
                <p>Layout: {label(venue.layout) || 'Not recorded'}</p>
                <p>Accessibility: {venue.accessibility.length ? venue.accessibility.map(label).join(', ') : 'None recorded'}</p>
                <p>Restrictions: {venue.restrictions || 'None recorded'}</p>
                {venue.booking_notes && <p>Booking notes: {venue.booking_notes}</p>}
              </article>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="font-display text-xl mb-3" style={{ color: C.ink }}>Technical arrangements</h2>
        <div className="font-ui text-sm space-y-1">
          <p>Technical Support: {technical_support?.name || 'Not assigned'}</p>
          <p>Technical notes: {technical_support_notes || 'None recorded'}</p>
        </div>
        <h3 className="font-ui font-medium mt-4 mb-2">Equipment requirements</h3>
        {equipment_requirements.length === 0 ? <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No equipment requirements recorded.</p> : (
          <ul className="list-disc pl-5 font-ui text-sm">
            {equipment_requirements.map((requirement) => (
              <li key={requirement.id}>{requirement.equipment.type}: {requirement.required_quantity}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}


export default function SafetyCheckDetail() {
  const { id } = useParams()
  const [state, setState] = useState({ status: 'loading', detail: null, error: null })
  const [decision, setDecision] = useState('approved')
  const [reason, setReason] = useState('')
  const [submit, setSubmit] = useState({ status: 'idle', error: null, result: null })

  useEffect(() => {
    let active = true
    getSafetyCheck(id).then(
      (detail) => { if (active) setState({ status: 'ready', detail, error: null }) },
      (error) => { if (active) setState({ status: 'error', detail: null, error: safetyCheckErrorMessage(error) }) },
    )
    return () => { active = false }
  }, [id])

  async function record(event) {
    event.preventDefault()
    const requiredReason = decision !== 'approved'
    if (requiredReason && !reason.trim()) {
      setSubmit({ status: 'idle', error: 'Provide a reason for this safety decision.', result: null })
      return
    }
    setSubmit({ status: 'saving', error: null, result: null })
    try {
      const result = await decideSafetyCheck(id, { decision, reason: requiredReason ? reason.trim() : null })
      setSubmit({ status: 'success', error: null, result })
    } catch (error) {
      setSubmit({ status: 'idle', error: safetyCheckErrorMessage(error), result: null })
    }
  }

  return (
    <main className="min-h-screen px-6 py-10" style={{ backgroundColor: C.paper, color: C.ink }}>
      <div className="max-w-4xl mx-auto">
        <Link to="/dashboard/safety-officer" className="inline-flex items-center gap-2 font-ui text-sm mb-6" style={{ color: C.teal }}>
          <ArrowLeft size={16} aria-hidden="true" /> Back to safety checks
        </Link>
        {state.status === 'loading' && <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading safety review details…</p>}
        {state.status === 'error' && <p role="alert" className="font-ui text-sm" style={{ color: C.rose }}>{state.error}</p>}
        {state.status === 'ready' && (
          <>
            <h1 className="font-display text-3xl mb-2">{state.detail.event.name}</h1>
            {/* S-82: attendance, venue, access and equipment changes so far. */}
            <Link to={`/events/${id}/history`} className="inline-block font-ui text-sm mb-8" style={{ color: C.teal }}>
              View change history
            </Link>
            <Evidence detail={state.detail} />
            <section className="mt-10 border-t pt-8" style={{ borderColor: C.line }}>
              <h2 className="font-display text-xl mb-4">Operational safety decision</h2>
              {submit.status === 'success' ? (
                <div role="status" className="flex items-start gap-2 rounded-sm p-4 font-ui text-sm" style={{ backgroundColor: C.paperDim, color: C.green }}>
                  <CheckCircle2 size={18} aria-hidden="true" />
                  <span>Operational safety decision recorded. Event status: {label(submit.result.status)}.</span>
                </div>
              ) : (
                <form onSubmit={record}>
                  <fieldset className="space-y-2 font-ui text-sm">
                    <legend className="sr-only">Safety decision</legend>
                    {DECISIONS.map((option) => (
                      <label key={option.value} className="flex items-center gap-2">
                        <input type="radio" name="decision" value={option.value} checked={decision === option.value} onChange={() => setDecision(option.value)} />
                        {option.label}
                      </label>
                    ))}
                  </fieldset>
                  {decision !== 'approved' && (
                    <label className="block font-ui text-sm mt-4">
                      Reason (required)
                      <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={4} className="block w-full border rounded-sm p-3 mt-1" style={{ borderColor: C.line }} />
                    </label>
                  )}
                  {submit.error && <p role="alert" className="font-ui text-sm mt-3" style={{ color: C.rose }}>{submit.error}</p>}
                  <button type="submit" disabled={submit.status === 'saving'} className="mt-5 px-5 py-2.5 rounded-sm font-ui text-sm text-white" style={{ backgroundColor: C.teal }}>
                    {submit.status === 'saving' ? 'Recording…' : 'Record safety decision'}
                  </button>
                </form>
              )}
            </section>
          </>
        )}
      </div>
    </main>
  )
}

