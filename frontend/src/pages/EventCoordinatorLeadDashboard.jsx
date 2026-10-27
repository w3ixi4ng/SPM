import { Loader2, LogOut } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import {
  assignEventRequest,
  assignmentErrorMessage,
  coordinatorOptionLabel,
  listAssignmentCoordinators,
  listCoordinatorActiveEvents,
  listCoordinatorOverview,
  listUnassignedEventRequests,
  moveAssignmentInOverview,
  overviewErrorMessage,
  reassignEvent,
  reassignmentErrorMessage,
} from '../lib/eventAssignments.js'
import { getRoleAccess } from '../lib/access.js'
import { listLeadReassignmentRequests, reassignmentRequestError } from '../lib/reassignmentRequests.js'

const C = {
  ink: '#10192B', inkFaint: '#4C5A70', paper: '#F8F6F1', line: '#E3DFD3',
  teal: '#0E7C74', green: '#3F8F5F', paperDim: '#F0EDE5',
}

const REASSIGNABLE_STATUSES = new Set(['submitted', 'under_review', 'returned', 'planning', 'pending_safety_check', 'confirmed', 'preparation', 'safety_rejected', 'safety_changes_requested'])

function formatWindow(event) {
  return `${event.start_date} ${event.start_time?.slice(0, 5)} – ${event.end_date} ${event.end_time?.slice(0, 5)}`
}

function formatStatus(status) {
  return status.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())
}

function isActiveCoordinator(coordinator) {
  return coordinator.coordinator_active === undefined || coordinator.coordinator_active === true
}

export default function EventCoordinatorLeadDashboard({ role }) {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const access = getRoleAccess(role)
  const [state, setState] = useState({ status: 'loading', events: [], coordinatorGroups: [], invalidAssignments: [], coordinators: [], error: null })
  const [choices, setChoices] = useState({})
  const [assigning, setAssigning] = useState(null)
  const [notice, setNotice] = useState('')
  const [requests, setRequests] = useState({ status: 'loading', rows: [] })
  const [selectedCoordinator, setSelectedCoordinator] = useState('')
  const selectedCoordinatorRef = useRef('')
  const [inventory, setInventory] = useState({ status: 'idle', events: [] })
  const inventoryRequest = useRef(0)

  function loadInventory(coordinatorId) {
    const requestId = ++inventoryRequest.current
    if (!coordinatorId) {
      setInventory({ status: 'idle', events: [] })
      return
    }
    setInventory({ status: 'loading', events: [] })
    listCoordinatorActiveEvents(coordinatorId)
      .then((data) => { if (requestId === inventoryRequest.current) setInventory({ status: 'ready', ...data }) })
      .catch((error) => { if (requestId === inventoryRequest.current) setInventory({ status: 'error', events: [], error: overviewErrorMessage(error) }) })
  }

  function loadRequests() {
    setRequests({ status: 'loading', rows: [] })
    listLeadReassignmentRequests()
      .then((rows) => setRequests({ status: 'ready', rows }))
      .catch((error) => setRequests({ status: 'error', rows: [], error: reassignmentRequestError(error) }))
  }

  useEffect(() => {
    let active = true
    listLeadReassignmentRequests()
      .then((rows) => { if (active) setRequests({ status: 'ready', rows }) })
      .catch((error) => { if (active) setRequests({ status: 'error', rows: [], error: reassignmentRequestError(error) }) })
    return () => { active = false }
  }, [])

  function load() {
    setState((current) => ({ ...current, status: 'loading', error: null }))
    Promise.all([listUnassignedEventRequests(), listCoordinatorOverview(), listAssignmentCoordinators()])
      .then(([events, overview, coordinators]) => setState({ status: 'ready', events, coordinatorGroups: overview.coordinators, invalidAssignments: overview.invalid_assignments ?? [], coordinators, error: null }))
      .catch((error) => setState({ status: 'error', events: [], coordinatorGroups: [], invalidAssignments: [], coordinators: [], error: overviewErrorMessage(error) }))
  }

  useEffect(() => {
    let active = true
    Promise.all([listUnassignedEventRequests(), listCoordinatorOverview(), listAssignmentCoordinators()])
      .then(([events, overview, coordinators]) => {
        if (active) setState({ status: 'ready', events, coordinatorGroups: overview.coordinators, invalidAssignments: overview.invalid_assignments ?? [], coordinators, error: null })
      })
      .catch((error) => {
        if (active) setState({ status: 'error', events: [], coordinatorGroups: [], invalidAssignments: [], coordinators: [], error: overviewErrorMessage(error) })
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
        coordinatorGroups: moveAssignmentInOverview(
          current.coordinatorGroups,
          updated,
          coordinator,
        ),
      }))
      setChoices((current) => ({ ...current, [choiceKey]: '' }))
      setNotice(`${event.name} was reassigned to ${coordinator?.name || 'the selected coordinator'}.`)
      loadRequests()
      if (selectedCoordinatorRef.current) loadInventory(selectedCoordinatorRef.current)
    } catch (error) {
      setNotice(reassignmentErrorMessage(error))
      load()
      if (selectedCoordinatorRef.current) loadInventory(selectedCoordinatorRef.current)
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
        {state.status === 'error' && <div role="alert" className="font-ui text-sm mb-5" style={{ color: C.inkFaint }}><p>{state.error}</p><button type="button" onClick={load} className="underline mt-2">Try again</button></div>}
        <section className="border rounded-sm p-7 sm:p-8" style={{ borderColor: C.line }}>
          <h2 className="font-display text-2xl mb-6" style={{ color: C.ink }}>Unassigned event requests</h2>
          {state.status === 'loading' && <p className="font-ui text-sm flex gap-2" style={{ color: C.inkFaint }}><Loader2 size={16} className="animate-spin" /> Loading queue…</p>}
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
                      {state.coordinators.map((coordinator) => <option key={coordinator.id} value={coordinator.id}>{coordinatorOptionLabel(coordinator)}</option>)}
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
          <h2 className="font-display text-2xl mb-5" style={{ color: C.ink }}>Reassignment requests</h2>
          {requests.status === 'loading' && <p className="font-ui text-sm">Loading reassignment requests…</p>}
          {requests.status === 'error' && <p role="alert" className="font-ui text-sm">{requests.error} <button type="button" className="underline" onClick={loadRequests}>Try again</button></p>}
          {requests.status === 'ready' && requests.rows.length === 0 && <p className="font-ui text-sm">No reassignment requests in your scope.</p>}
          {requests.status === 'ready' && requests.rows.length > 0 && (
            <ul className="space-y-3 font-ui text-sm">
              {requests.rows.map((item) => (
                <li key={item.id} className="border rounded-sm p-4" style={{ borderColor: C.line }}>
                  <strong>{item.event_name}</strong> · {item.requester?.name || 'Unknown coordinator'} · {item.status === 'actioned' ? 'Actioned' : 'Pending'}
                  <p className="mt-1" style={{ color: C.inkFaint }}>{item.reason}</p>
                  {item.status === 'pending' && <p className="mt-1" style={{ color: C.teal }}>Use the reassignment control in Coordinator oversight below.</p>}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="border rounded-sm p-7 sm:p-8 mt-8" style={{ borderColor: C.line }}>
          <h2 className="font-display text-2xl mb-2" style={{ color: C.ink }}>Coordinator active events</h2>
          <p className="font-ui text-sm mb-5" style={{ color: C.inkFaint }}>Select a Coordinator to review all active assignments. Events belonging to another Lead are read-only.</p>
          <label htmlFor="coordinator-inventory" className="block font-ui text-sm mb-2">Event Coordinator</label>
          <select id="coordinator-inventory" value={selectedCoordinator} onChange={(event) => { selectedCoordinatorRef.current = event.target.value; setSelectedCoordinator(event.target.value); loadInventory(event.target.value) }} className="border rounded-sm px-3 py-2 font-ui text-sm bg-white" style={{ borderColor: C.line, color: C.ink }}>
            <option value="">Choose an Event Coordinator</option>
            {state.coordinatorGroups.map((group) => <option key={group.coordinator.id} value={group.coordinator.id}>{coordinatorOptionLabel(group.coordinator)}{isActiveCoordinator(group.coordinator) ? '' : ' — inactive'}</option>)}
          </select>
          {inventory.status === 'loading' && <p className="font-ui text-sm mt-4">Loading active events…</p>}
          {inventory.status === 'error' && <p role="alert" className="font-ui text-sm mt-4">{inventory.error} <button type="button" onClick={() => loadInventory(selectedCoordinator)} className="underline">Try again</button></p>}
          {inventory.status === 'ready' && <>
            {!isActiveCoordinator(inventory.coordinator) && inventory.active_assignment_count > 0 && <p role="alert" className="font-ui text-sm mt-4" style={{ color: C.ink }}>Inactive Coordinator has {inventory.active_assignment_count} active {inventory.active_assignment_count === 1 ? 'event' : 'events'} requiring reassignment.</p>}
            <p className="font-ui text-sm mt-4">{inventory.active_assignment_count} active {inventory.active_assignment_count === 1 ? 'event' : 'events'}</p>
            {inventory.events.length === 0 && <p className="font-ui text-sm mt-2">No active events assigned.</p>}
            <ul aria-label="Selected Coordinator active events" className="space-y-3 mt-4">
              {inventory.events.map((event) => <li key={event.id} className="border rounded-sm p-4" style={{ borderColor: C.line }}>
                <h3 className="font-display text-lg">{event.name}</h3>
                <p className="font-ui text-sm">{formatStatus(event.status)} · {formatWindow(event)}</p>
                <p className="font-ui text-sm">Assigned Coordinator: {inventory.coordinator.name}</p>
                {event.scope === 'other_lead' && <p className="font-ui text-sm">Responsible Lead: {event.assigning_lead_id}. Read-only; contact that Lead for reassignment.</p>}
                {event.scope === 'legacy' && <p className="font-ui text-sm">Responsible Lead not recorded. Read-only; controlled provenance review required.</p>}
                {event.actionable && REASSIGNABLE_STATUSES.has(event.status) && <div className="flex flex-col sm:flex-row gap-3 mt-3">
                  <label className="sr-only" htmlFor={`inventory-reassign-${event.id}`}>New Event Coordinator for {event.name}</label>
                  <select id={`inventory-reassign-${event.id}`} value={choices[`reassign:${event.id}`] || ''} onChange={(change) => setChoices((current) => ({ ...current, [`reassign:${event.id}`]: change.target.value }))} className="border rounded-sm px-3 py-2 font-ui text-sm bg-white" style={{ borderColor: C.line, color: C.ink }}>
                    <option value="">Choose a different Event Coordinator</option>
                    {state.coordinators.filter((item) => item.id !== event.assigned_coordinator_id).map((item) => <option key={item.id} value={item.id}>{coordinatorOptionLabel(item)}</option>)}
                  </select>
                  <button type="button" disabled={assigning === event.id} onClick={() => handleReassign(event)} className="rounded-sm px-5 py-2 font-ui text-sm text-white disabled:opacity-60" style={{ backgroundColor: C.teal }}>{assigning === event.id ? 'Reassigning…' : 'Reassign event'}</button>
                </div>}
              </li>)}
            </ul>
          </>}
        </section>

        <section className="border rounded-sm p-7 sm:p-8 mt-8" style={{ borderColor: C.line }}>
          <h2 className="font-display text-2xl mb-2" style={{ color: C.ink }}>Coordinator oversight</h2>
          <p className="font-ui text-sm mb-6" style={{ color: C.inkFaint }}>Active assignments grouped by their current Event Coordinator.</p>
          {state.status === 'ready' && state.invalidAssignments.length > 0 && (
            <div role="alert" className="border rounded-sm p-5 mb-6" style={{ borderColor: C.line, backgroundColor: C.paperDim }}>
              <h3 className="font-ui font-semibold" style={{ color: C.ink }}>Assignment data needs review</h3>
              <p className="font-ui text-sm mt-1" style={{ color: C.inkFaint }}>
                {state.invalidAssignments.length} active {state.invalidAssignments.length === 1 ? 'event is' : 'events are'} assigned to an account with a missing Coordinator identity. These assignments have not been changed.
              </p>
              <ul className="font-ui text-sm mt-3 space-y-1" style={{ color: C.inkFaint }}>
                {state.invalidAssignments.map((item) => (
                  <li key={item.event_id}>{item.name} ({formatStatus(item.status)}) · owner ID {item.assigned_coordinator_id}</li>
                ))}
              </ul>
            </div>
          )}
          {state.status === 'loading' && <p className="font-ui text-sm flex gap-2" style={{ color: C.inkFaint }}><Loader2 size={16} className="animate-spin" /> Loading coordinator overview…</p>}
          {state.status === 'ready' && state.coordinatorGroups.length === 0 && <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No Event Coordinators are available.</p>}
          {state.status === 'ready' && state.coordinatorGroups.length > 0 && (
            <div className="space-y-6">
              {state.coordinatorGroups.map((group) => (
                <article key={group.coordinator.id} aria-label={`${group.coordinator.name} coordinator overview`} className="rounded-sm p-5" style={{ backgroundColor: C.paperDim }}>
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                    <h3 className="font-display text-xl" style={{ color: C.ink }}>{group.coordinator.name}</h3>
                    <p className="font-ui text-sm" style={{ color: C.teal }}>{group.active_assignment_count} active {group.active_assignment_count === 1 ? 'assignment' : 'assignments'}</p>
                  </div>
                  {group.coordinator.email && <p className="font-ui text-xs mt-1" style={{ color: C.inkFaint }}>{group.coordinator.email}</p>}
                  {!isActiveCoordinator(group.coordinator) && group.active_assignment_count > 0 && <p role="alert" className="font-ui text-sm mt-2">Inactive Coordinator: {group.active_assignment_count} active {group.active_assignment_count === 1 ? 'event needs' : 'events need'} reassignment.</p>}
                  {group.events.length === 0 && <p className="font-ui text-sm mt-5" style={{ color: C.inkFaint }}>No active events assigned.</p>}
                  {group.events.length > 0 && (
                    <ul aria-label={`${group.coordinator.name} active events`} className="space-y-4 mt-5">
                      {group.events.map((event) => {
                        const choiceKey = `reassign:${event.id}`
                        return (
                          <li key={event.id} className="border rounded-sm p-4 bg-white" style={{ borderColor: C.line }}>
                            <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                              <h4 className="font-display text-lg" style={{ color: C.ink }}>{event.name}</h4>
                              <span className="font-ui text-xs" style={{ color: C.green }}>{formatStatus(event.status)}</span>
                            </div>
                            <p className="font-ui text-sm mt-2" style={{ color: C.inkFaint }}>{formatWindow(event)}</p>
                            <p className="font-ui text-sm mt-1" style={{ color: C.inkFaint }}>Organiser: {event.organiser?.name || event.organiser_id}</p>
                            <p className="font-ui text-sm mt-1" style={{ color: C.inkFaint }}>Current Coordinator: {event.coordinator?.name || event.assigned_coordinator_id}</p>
                            {REASSIGNABLE_STATUSES.has(event.status) && (
                              <div className="flex flex-col sm:flex-row gap-3 mt-5">
                                <label className="sr-only" htmlFor={`reassign-coordinator-${event.id}`}>New Event Coordinator for {event.name}</label>
                                <select id={`reassign-coordinator-${event.id}`} value={choices[choiceKey] || ''} onChange={(e) => setChoices((current) => ({ ...current, [choiceKey]: e.target.value }))} className="border rounded-sm px-3 py-2 font-ui text-sm bg-white" style={{ borderColor: C.line, color: C.ink }}>
                                  <option value="">Choose a different Event Coordinator</option>
                                  {state.coordinators.filter((coordinator) => coordinator.id !== event.assigned_coordinator_id).map((coordinator) => <option key={coordinator.id} value={coordinator.id}>{coordinatorOptionLabel(coordinator)}</option>)}
                                </select>
                                <button type="button" disabled={assigning === event.id} onClick={() => handleReassign(event)} className="rounded-sm px-5 py-2 font-ui text-sm text-white disabled:opacity-60" style={{ backgroundColor: C.teal }}>
                                  {assigning === event.id ? 'Reassigning…' : 'Reassign event'}
                                </button>
                              </div>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
