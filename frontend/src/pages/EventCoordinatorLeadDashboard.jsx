import { Loader2, LogOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import {
  assignEventRequest,
  assignmentErrorMessage,
  listActiveAssignments,
  listAssignmentCoordinators,
  listUnassignedEventRequests,
  reassignEvent,
  reassignmentErrorMessage,
} from '../lib/eventAssignments.js'
import { getRoleAccess } from '../lib/access.js'

const C = {
  ink: '#10192B', inkFaint: '#4C5A70', paper: '#F8F6F1', line: '#E3DFD3',
  teal: '#0E7C74', green: '#3F8F5F', paperDim: '#F0EDE5',
}

function formatWindow(event) {
  return `${event.start_date} ${event.start_time?.slice(0, 5)} – ${event.end_date} ${event.end_time?.slice(0, 5)}`
}

export default function EventCoordinatorLeadDashboard({ role }) {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const access = getRoleAccess(role)
  const [state, setState] = useState({ status: 'loading', events: [], assignedEvents: [], coordinators: [], error: null })
  const [choices, setChoices] = useState({})
  const [assigning, setAssigning] = useState(null)
  const [notice, setNotice] = useState('')

  function load() {
    setState((current) => ({ ...current, status: 'loading', error: null }))
    Promise.all([listUnassignedEventRequests(), listActiveAssignments(), listAssignmentCoordinators()])
      .then(([events, assignedEvents, coordinators]) => setState({ status: 'ready', events, assignedEvents, coordinators, error: null }))
      .catch((error) => setState({ status: 'error', events: [], assignedEvents: [], coordinators: [], error: assignmentErrorMessage(error) }))
  }

  useEffect(() => {
    let active = true
    Promise.all([listUnassignedEventRequests(), listActiveAssignments(), listAssignmentCoordinators()])
      .then(([events, assignedEvents, coordinators]) => {
        if (active) setState({ status: 'ready', events, assignedEvents, coordinators, error: null })
      })
      .catch((error) => {
        if (active) setState({ status: 'error', events: [], assignedEvents: [], coordinators: [], error: assignmentErrorMessage(error) })
      })
    return () => { active = false }
  }, [])

  async function handleAssign(event) {
    const coordinatorId = choices[event.id]
    if (!coordinatorId) {
      setNotice('Choose an Event Coordinator before assigning.')
      return
    }
    setAssigning(event.id)
    setNotice('')
    try {
      const coordinator = state.coordinators.find((item) => item.id === coordinatorId)
      await assignEventRequest(event.id, coordinatorId)
      setState((current) => ({
        ...current,
        events: current.events.filter((item) => item.id !== event.id),
      }))
      setNotice(`${event.name} was assigned to ${coordinator?.name || 'the selected coordinator'}.`)
    } catch (error) {
      setNotice(assignmentErrorMessage(error))
    } finally {
      setAssigning(null)
    }
  }

  async function handleReassign(event) {
    const choiceKey = `reassign:${event.id}`
    const coordinatorId = choices[choiceKey]
    if (!coordinatorId) {
      setNotice('Choose a different Event Coordinator before reassigning.')
      return
    }
    setAssigning(event.id)
    setNotice('')
    try {
      const coordinator = state.coordinators.find((item) => item.id === coordinatorId)
      const updated = await reassignEvent(
        event.id,
        coordinatorId,
        event.assigned_coordinator_id,
        event.coordinator_assignment_version,
      )
      setState((current) => ({
        ...current,
        assignedEvents: current.assignedEvents.map((item) => (
          item.id === event.id
            ? { ...item, ...updated, coordinator }
            : item
        )),
      }))
      setChoices((current) => ({ ...current, [choiceKey]: '' }))
      setNotice(`${event.name} was reassigned to ${coordinator?.name || 'the selected coordinator'}.`)
    } catch (error) {
      setNotice(reassignmentErrorMessage(error))
    } finally {
      setAssigning(null)
    }
  }

  async function handleSignOut() {
    await signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <div className="w-full max-w-5xl mx-auto">
        <header className="flex items-center justify-between gap-6 mb-14">
          <Logo />
          <button type="button" onClick={handleSignOut} className="inline-flex items-center gap-2 px-4 py-2 rounded-sm font-ui text-sm border" style={{ borderColor: C.ink, color: C.ink }}>
            <LogOut size={15} aria-hidden="true" /> Sign out
          </button>
        </header>
        <div className="max-w-2xl mb-10">
          <div className="inline-flex items-center gap-2 text-xs font-ui px-3 py-1 rounded-sm mb-5" style={{ backgroundColor: 'rgba(63,143,95,0.12)', color: C.green }}>
            Signed in as {access.label}
          </div>
          <h1 className="font-display text-4xl sm:text-5xl mb-4" style={{ color: C.ink }}>Assignment queue</h1>
          <p className="font-ui text-base" style={{ color: C.inkFaint }}>{access.description}</p>
          <p className="font-ui text-xs mt-3" style={{ color: C.inkFaint }}>{user.name} · {user.email}</p>
        </div>

        {notice && <p role="status" className="font-ui text-sm mb-5" style={{ color: C.teal }}>{notice}</p>}
        <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
          <h2 className="font-display text-2xl mb-6" style={{ color: C.ink }}>Unassigned event requests</h2>
          {state.status === 'loading' && <p className="font-ui text-sm flex gap-2" style={{ color: C.inkFaint }}><Loader2 size={16} className="animate-spin" /> Loading queue…</p>}
          {state.status === 'error' && <div role="alert" className="font-ui text-sm" style={{ color: C.inkFaint }}><p>{state.error}</p><button type="button" onClick={load} className="underline mt-2">Try again</button></div>}
          {state.status === 'ready' && state.events.length === 0 && <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No event requests are waiting for assignment.</p>}
          {state.status === 'ready' && state.events.length > 0 && (
            <ul className="space-y-5">
              {state.events.map((event) => (
                <li key={event.id} className="rounded-sm p-5" style={{ backgroundColor: C.paperDim }}>
                  <h3 className="font-display text-xl" style={{ color: C.ink }}>{event.name}</h3>
                  <p className="font-ui text-sm mt-2" style={{ color: C.inkFaint }}>{formatWindow(event)}</p>
                  <p className="font-ui text-sm mt-1" style={{ color: C.inkFaint }}>Expected attendance: {event.expected_attendance}</p>
                  <p className="font-ui text-sm mt-1" style={{ color: C.inkFaint }}>Organiser: {event.organiser?.name || event.organiser_id}{event.organiser?.email && ` · ${event.organiser.email}`}</p>
                  <div className="flex flex-col sm:flex-row gap-3 mt-5">
                    <label className="sr-only" htmlFor={`coordinator-${event.id}`}>Event Coordinator for {event.name}</label>
                    <select id={`coordinator-${event.id}`} value={choices[event.id] || ''} onChange={(e) => setChoices((current) => ({ ...current, [event.id]: e.target.value }))} className="border rounded-sm px-3 py-2 font-ui text-sm bg-white" style={{ borderColor: C.line, color: C.ink }}>
                      <option value="">Choose an Event Coordinator</option>
                      {state.coordinators.map((coordinator) => <option key={coordinator.id} value={coordinator.id}>{coordinator.name}</option>)}
                    </select>
                    <button type="button" disabled={assigning === event.id} onClick={() => handleAssign(event)} className="rounded-sm px-5 py-2 font-ui text-sm text-white disabled:opacity-60" style={{ backgroundColor: C.teal }}>
                      {assigning === event.id ? 'Assigning…' : 'Assign request'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="border rounded-sm p-7 sm:p-8 mt-8" style={{ borderColor: C.line }}>
          <h2 className="font-display text-2xl mb-6" style={{ color: C.ink }}>Assigned active events</h2>
          {state.status === 'loading' && <p className="font-ui text-sm flex gap-2" style={{ color: C.inkFaint }}><Loader2 size={16} className="animate-spin" /> Loading assignments…</p>}
          {state.status === 'ready' && state.assignedEvents.length === 0 && <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No active events are currently assigned.</p>}
          {state.status === 'ready' && state.assignedEvents.length > 0 && (
            <ul className="space-y-5">
              {state.assignedEvents.map((event) => {
                const choiceKey = `reassign:${event.id}`
                return (
                  <li key={event.id} className="rounded-sm p-5" style={{ backgroundColor: C.paperDim }}>
                    <h3 className="font-display text-xl" style={{ color: C.ink }}>{event.name}</h3>
                    <p className="font-ui text-sm mt-2" style={{ color: C.inkFaint }}>{formatWindow(event)}</p>
                    <p className="font-ui text-sm mt-1" style={{ color: C.inkFaint }}>Organiser: {event.organiser?.name || event.organiser_id}</p>
                    <p className="font-ui text-sm mt-1" style={{ color: C.inkFaint }}>Current Coordinator: {event.coordinator?.name || event.assigned_coordinator_id}</p>
                    <div className="flex flex-col sm:flex-row gap-3 mt-5">
                      <label className="sr-only" htmlFor={`reassign-coordinator-${event.id}`}>New Event Coordinator for {event.name}</label>
                      <select id={`reassign-coordinator-${event.id}`} value={choices[choiceKey] || ''} onChange={(e) => setChoices((current) => ({ ...current, [choiceKey]: e.target.value }))} className="border rounded-sm px-3 py-2 font-ui text-sm bg-white" style={{ borderColor: C.line, color: C.ink }}>
                        <option value="">Choose a different Event Coordinator</option>
                        {state.coordinators.filter((coordinator) => coordinator.id !== event.assigned_coordinator_id).map((coordinator) => <option key={coordinator.id} value={coordinator.id}>{coordinator.name}</option>)}
                      </select>
                      <button type="button" disabled={assigning === event.id} onClick={() => handleReassign(event)} className="rounded-sm px-5 py-2 font-ui text-sm text-white disabled:opacity-60" style={{ backgroundColor: C.teal }}>
                        {assigning === event.id ? 'Reassigning…' : 'Reassign event'}
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
