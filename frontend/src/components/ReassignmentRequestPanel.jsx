import { useEffect, useState } from 'react'
import {
  listMyReassignmentRequests,
  reassignmentRequestError,
  requestReassignment,
} from '../lib/reassignmentRequests.js'

const ink = '#10192B'
const muted = '#4C5A70'

export function ReassignmentRequestHistory({ eventId = null, refresh = 0 }) {
  const [state, setState] = useState({ status: 'loading', rows: [] })

  useEffect(() => {
    let active = true
    listMyReassignmentRequests()
      .then((rows) => { if (active) setState({ status: 'ready', rows }) })
      .catch((error) => { if (active) setState({ status: 'error', rows: [], error: reassignmentRequestError(error) }) })
    return () => { active = false }
  }, [refresh])

  const rows = eventId ? state.rows.filter((row) => row.event_id === eventId) : state.rows
  return (
    <div className="font-ui text-sm" style={{ color: muted }}>
      {state.status === 'loading' && <p>Loading reassignment requests…</p>}
      {state.status === 'error' && <p role="alert">{state.error}</p>}
      {state.status === 'ready' && rows.length === 0 && <p>No reassignment requests yet.</p>}
      {state.status === 'ready' && rows.length > 0 && (
        <ul className="space-y-3">
          {rows.map((row) => (
            <li key={row.id} className="border rounded-sm p-3">
              <strong style={{ color: ink }}>{row.event_name}</strong>
              <span className="ml-2">{row.status === 'actioned' ? 'Actioned' : 'Pending'}</span>
              <p>{row.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function ReassignmentRequestPanel({ eventId }) {
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [refresh, setRefresh] = useState(0)

  async function submit(event) {
    event.preventDefault()
    if (!reason.trim()) {
      setNotice('Enter a reason for the request.')
      return
    }
    setSaving(true)
    setNotice('')
    try {
      await requestReassignment(eventId, reason)
      setReason('')
      setNotice('Request sent to the responsible Lead.')
      setRefresh((value) => value + 1)
    } catch (error) {
      setNotice(reassignmentRequestError(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="border rounded-sm p-7 sm:p-8 mt-8" style={{ borderColor: '#E3DFD3' }}>
      <h2 className="font-display text-2xl mb-3" style={{ color: ink }}>Request reassignment</h2>
      <p className="font-ui text-sm mb-4" style={{ color: muted }}>Tell the responsible Lead why you can no longer handle this event. The Lead decides whether to reassign it.</p>
      <form onSubmit={submit}>
        <label htmlFor="reassignment-reason" className="block font-ui text-sm mb-2">Reason</label>
        <textarea id="reassignment-reason" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={2000} rows={3} className="w-full border rounded-sm p-3 font-ui text-sm" required />
        <button type="submit" disabled={saving} className="rounded-sm px-5 py-2 mt-3 font-ui text-sm text-white disabled:opacity-60" style={{ backgroundColor: '#0E7C74' }}>
          {saving ? 'Sending…' : 'Send request'}
        </button>
      </form>
      {notice && <p role="status" className="font-ui text-sm mt-3">{notice}</p>}
      <h3 className="font-ui font-semibold mt-6 mb-2" style={{ color: ink }}>Your request history for this event</h3>
      <ReassignmentRequestHistory eventId={eventId} refresh={refresh} />
    </section>
  )
}
