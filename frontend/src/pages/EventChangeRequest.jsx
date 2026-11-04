import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import EventChangeComparison from '../components/EventChangeComparison.jsx'
import { getEventOptions } from '../lib/eventRequests.js'
import {
  CHANGE_FIELDS, CHANGE_REQUEST_STATUSES, changeValues, changedFields,
  durationMinutes, endFromDuration, equipmentSnapshot,
  getEventChangeRequests, submitEventChangeRequest,
} from '../lib/eventChangeRequests.js'

const labels = Object.fromEntries(CHANGE_FIELDS)

export default function EventChangeRequest() {
  const { id } = useParams()
  const [state, setState] = useState({ status: 'loading', data: null, options: null, error: '' })
  const [form, setForm] = useState(null)
  const [equipment, setEquipment] = useState([])
  const [sending, setSending] = useState(false)
  const submitting = useRef(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  async function load() {
    setState({ status: 'loading', data: null, options: null, error: '' })
    try {
      const [data, options] = await Promise.all([getEventChangeRequests(id), getEventOptions()])
      setState({ status: 'ready', data, options, error: '' })
      setForm(changeValues(data.event))
      setEquipment(equipmentSnapshot(data.equipment))
    } catch (failure) {
      setState({ status: 'error', data: null, options: null, error: failure.message || 'Could not load the change request.' })
    }
  }

  useEffect(() => {
    let active = true
    Promise.all([getEventChangeRequests(id), getEventOptions()])
      .then(([data, options]) => {
        if (!active) return
        setState({ status: 'ready', data, options, error: '' })
        setForm(changeValues(data.event))
        setEquipment(equipmentSnapshot(data.equipment))
      })
      .catch((failure) => {
        if (active) setState({ status: 'error', data: null, options: null, error: failure.message || 'Could not load the change request.' })
      })
    return () => { active = false }
  }, [id])

  if (state.status === 'loading') return <main className="max-w-3xl mx-auto p-6"><p>Loading change request…</p></main>
  if (state.status === 'error') return <main className="max-w-3xl mx-auto p-6"><p role="alert">{state.error}</p><button type="button" onClick={load}>Try again</button></main>

  const { event, requests, equipment: acceptedEquipment, equipment_options: catalogue } = state.data
  const pending = requests.find((request) => request.status === 'pending')
  const eligible = CHANGE_REQUEST_STATUSES.has(event.status)
  const changed = form ? changedFields(event, form, acceptedEquipment, equipment) : []
  const duration = form ? durationMinutes(form) : 0
  const availableEquipment = new Map(catalogue.map((item) => [item.id, item]))
  const choices = [
    ...catalogue,
    ...acceptedEquipment.filter((item) => !availableEquipment.has(item.equipment_item_id))
      .map((item) => ({ id: item.equipment_item_id, type: item.equipment?.type || item.equipment_item_id, unavailable: true })),
  ]

  function setField(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
    setError('')
  }

  function toggleList(field, value) {
    setForm((current) => ({
      ...current,
      [field]: current[field].includes(value)
        ? current[field].filter((item) => item !== value)
        : [...current[field], value],
    }))
  }

  function toggleEquipment(id) {
    setEquipment((items) => items.some((item) => item.equipment_item_id === id)
      ? items.filter((item) => item.equipment_item_id !== id)
      : [...items, { equipment_item_id: id, required_quantity: 1 }])
  }

  async function submit(eventData) {
    eventData.preventDefault()
    if (submitting.current || !changed.length) return
    if (duration <= 0 || !Number.isInteger(Number(form.expected_attendance)) || Number(form.expected_attendance) <= 0) {
      setError('Enter a valid event window and a positive expected attendance.')
      return
    }
    submitting.current = true
    setSending(true)
    setError('')
    try {
      const saved = await submitEventChangeRequest(id, changeValues(form), equipment)
      setState((current) => ({ ...current, data: { ...current.data, requests: [saved, ...current.data.requests] } }))
      setNotice('Change request submitted. Accepted event details remain unchanged.')
      try {
        const refreshed = await getEventChangeRequests(id)
        setState((current) => ({ ...current, data: refreshed }))
      } catch {
        setError('Your request was submitted, but the latest comparison could not be loaded. Reload to see it.')
      }
    } catch (failure) {
      setError(failure.status === 409
        ? 'A request is already pending or the event changed. Reload to see the latest details.'
        : failure.message || 'The change request could not be sent. Accepted event details are unchanged.')
    } finally {
      submitting.current = false
      setSending(false)
    }
  }

  return (
    <main className="max-w-3xl mx-auto p-6 font-ui">
      <Link to={`/events/${id}`} className="underline">← Back to event</Link>
      <h1 className="font-display text-3xl my-5">Request Changes</h1>
      <p className="mb-5">Your accepted event details and existing arrangements stay in place until this proposal is reviewed.</p>
      {notice && <p role="status" className="mb-4">{notice}</p>}
      {error && <p role="alert" className="mb-4">{error}</p>}
      {pending && <EventChangeComparison event={event} request={pending} equipment={acceptedEquipment} equipmentOptions={catalogue} />}
      {!pending && eligible && form && (
        <form onSubmit={submit} className="space-y-5" aria-label="Request event changes">
          <p>Changed fields: {changed.length ? changed.map((field) => labels[field] || 'Equipment requirements').join(', ') : 'None yet'}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              ['start_date', 'Start date', 'date'], ['start_time', 'Start time', 'time'],
              ['end_date', 'End date', 'date'], ['end_time', 'End time', 'time'],
              ['expected_attendance', 'Expected attendance', 'number'],
              ['venue', 'Venue preference', 'text'],
              ['special_requirements', 'Special requirements', 'text'],
            ].map(([field, label, type]) => (
              <label key={field} className="block">{label}{changed.includes(field) && ' (changed)'}
                <input className="block w-full border rounded p-2 mt-1" type={type} min={type === 'number' ? 1 : undefined} value={form[field] ?? ''} onChange={(e) => setField(field, e.target.value)} />
              </label>
            ))}
            <label className="block">Duration in minutes
              <input className="block w-full border rounded p-2 mt-1" type="number" min="1" value={duration || ''} onChange={(e) => {
                const end = endFromDuration(form, Number(e.target.value))
                if (end) setForm((current) => ({ ...current, ...end }))
              }} />
            </label>
            <label className="block">Room layout
              <select className="block w-full border rounded p-2 mt-1" value={form.room_layout ?? ''} onChange={(e) => setField('room_layout', e.target.value || null)}>
                <option value="">None</option>
                {state.options.room_layouts.map((value) => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}
              </select>
            </label>
          </div>
          {[
            ['required_facilities', 'Facilities', state.options.facilities],
            ['required_accessibility', 'Accessibility', state.options.accessibility],
          ].map(([field, label, options]) => (
            <fieldset key={field} className="border rounded p-4"><legend>{label}</legend>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">{options.map((value) => (
                <label key={value}><input type="checkbox" checked={form[field].includes(value)} onChange={() => toggleList(field, value)} /> {value.replaceAll('_', ' ')}</label>
              ))}</div>
            </fieldset>
          ))}
          <fieldset className="border rounded p-4"><legend>Equipment requirements</legend>
            {choices.map((item) => {
              const selected = equipment.find((entry) => entry.equipment_item_id === item.id)
              return <div key={item.id} className="flex items-center gap-3 my-2">
                <label><input type="checkbox" checked={Boolean(selected)} disabled={item.unavailable && !selected} onChange={() => toggleEquipment(item.id)} /> {item.type}{item.unavailable && ' (unavailable for new requests)'}</label>
                {selected && <input aria-label={`${item.type} quantity`} className="w-20 border rounded p-1" type="number" min="1" disabled={item.unavailable} value={selected.required_quantity} onChange={(e) => setEquipment((items) => items.map((entry) => entry.equipment_item_id === item.id ? { ...entry, required_quantity: Number(e.target.value) } : entry))} />}
              </div>
            })}
          </fieldset>
          <p>Existing venue, equipment, Technical Support and attendee arrangements have not been validated for these proposed changes.</p>
          <button type="submit" disabled={sending || !changed.length} className="border rounded px-5 py-2 disabled:opacity-50">{sending ? 'Submitting…' : 'Submit change request'}</button>
        </form>
      )}
      {!pending && !eligible && <p role="status">This event cannot receive a change request in its current state.</p>}
      {requests.filter((request) => request.status !== 'pending').length > 0 && (
        <section className="mt-8" aria-label="Past change requests"><h2 className="font-display text-xl">Past requests</h2>
          {requests.filter((request) => request.status !== 'pending').map((request) => <EventChangeComparison key={request.id} event={event} request={request} equipment={acceptedEquipment} equipmentOptions={catalogue} />)}
        </section>
      )}
    </main>
  )
}
