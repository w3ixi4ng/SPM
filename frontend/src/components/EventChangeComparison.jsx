import { CHANGE_FIELDS, changedFields, durationMinutes } from '../lib/eventChangeRequests.js'

function display(value) {
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'None'
  return value === null || value === undefined || value === '' ? 'None' : String(value)
}

function equipmentText(items, names) {
  if (!items?.length) return 'None'
  return items.map((item) => `${names[item.equipment_item_id] ?? item.equipment_item_id}: ${item.required_quantity}`).join(', ')
}

export default function EventChangeComparison({ event, request, equipment = [], equipmentOptions = [] }) {
  const names = Object.fromEntries([
    ...equipment.map((item) => [item.equipment_item_id, item.equipment?.type]),
    ...equipmentOptions.map((item) => [item.id, item.type]),
  ])
  const changed = changedFields(
    request.accepted_values, request.proposed_values,
    request.accepted_equipment, request.proposed_equipment,
  )
  const currentDiffersFromBaseline = changedFields(
    request.accepted_values, event,
    request.accepted_equipment,
    equipment.map((item) => ({ equipment_item_id: item.equipment_item_id, required_quantity: item.required_quantity })),
  ).length > 0

  return (
    <section aria-label="Event change request" className="border rounded-sm p-5 my-6" style={{ borderColor: '#E3DFD3' }}>
      <h2 className="font-display text-xl mb-2">Change request: {request.status}</h2>
      <p className="font-ui text-sm mb-3">Submitted {new Date(request.submitted_at).toLocaleString()} by {request.requested_by}.</p>
      {currentDiffersFromBaseline && <p role="status" className="font-ui text-sm mb-3">Accepted event details have changed since this request was submitted. Review the current values below.</p>}
      <p className="font-ui text-sm mb-4">Existing venue, equipment, Technical Support and attendee arrangements apply to the accepted event details. They have not yet been validated for this proposal.</p>
      <div className="overflow-x-auto">
        <table className="w-full font-ui text-sm">
          <thead><tr><th className="text-left pb-2">Changed field</th><th className="text-left pb-2">Currently accepted</th><th className="text-left pb-2">Proposed</th></tr></thead>
          <tbody>
            {CHANGE_FIELDS.map(([field, label]) => (
              <tr key={field}><th scope="row" className="text-left py-2 pr-3">{label}{changed.includes(field) && ' (changed)'}</th><td className="py-2 pr-3">{display(event[field])}</td><td className="py-2">{display(request.proposed_values[field])}</td></tr>
            ))}
            <tr><th scope="row" className="text-left py-2 pr-3">Duration{durationMinutes(event) !== durationMinutes(request.proposed_values) && ' (changed)'}</th><td className="py-2 pr-3">{durationMinutes(event)} minutes</td><td className="py-2">{durationMinutes(request.proposed_values)} minutes</td></tr>
            <tr><th scope="row" className="text-left py-2 pr-3">Equipment requirements{changed.includes('equipment') && ' (changed)'}</th><td className="py-2 pr-3">{equipmentText(equipment.map((item) => ({ equipment_item_id: item.equipment_item_id, required_quantity: item.required_quantity })), names)}</td><td className="py-2">{equipmentText(request.proposed_equipment, names)}</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  )
}
