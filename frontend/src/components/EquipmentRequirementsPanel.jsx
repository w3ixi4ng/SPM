import { useCallback, useEffect, useState } from 'react'
import { Loader2, Package, Trash2 } from 'lucide-react'
import { listEquipmentSelection } from '../lib/equipment.js'
import {
  listEquipmentRequirements,
  removeEquipmentRequirement,
  requirementErrorMessage,
  saveEquipmentRequirement,
  validateRequirementQuantity,
} from '../lib/equipmentRequirements.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
  rose: '#B25547',
  green: '#3F8F5F',
}

export default function EquipmentRequirementsPanel({ eventId, status, editable = false }) {
  const canEdit = editable && status === 'planning'
  const [state, setState] = useState({ status: 'loading', requirements: [], items: [], error: null })
  const [quantities, setQuantities] = useState({})
  const [errors, setErrors] = useState({})
  const [busyId, setBusyId] = useState(null)
  const [notice, setNotice] = useState(null)

  const load = useCallback(async () => {
    try {
      const [requirements, items] = await Promise.all([
        listEquipmentRequirements(eventId),
        canEdit ? listEquipmentSelection() : Promise.resolve([]),
      ])
      setState({ status: 'ready', requirements, items, error: null })
      setQuantities(Object.fromEntries(
        requirements.map((requirement) => [
          requirement.equipment_item_id,
          String(requirement.required_quantity),
        ]),
      ))
    } catch (error) {
      setState({ status: 'error', requirements: [], items: [], error: requirementErrorMessage(error) })
    }
  }, [canEdit, eventId])

  // Loading remote requirement/catalogue state is the synchronization this
  // effect owns; state changes only after those requests settle.
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { void load() }, [load])

  async function save(itemId) {
    const error = validateRequirementQuantity(quantities[itemId])
    if (error) {
      setErrors((current) => ({ ...current, [itemId]: error }))
      return
    }
    setBusyId(itemId)
    setNotice(null)
    try {
      await saveEquipmentRequirement(eventId, itemId, quantities[itemId])
      setErrors((current) => ({ ...current, [itemId]: undefined }))
      setNotice('Equipment requirement saved.')
      await load()
    } catch (caught) {
      setErrors((current) => ({ ...current, [itemId]: requirementErrorMessage(caught) }))
    } finally {
      setBusyId(null)
    }
  }

  async function remove(itemId) {
    setBusyId(itemId)
    setNotice(null)
    try {
      await removeEquipmentRequirement(eventId, itemId)
      setNotice('Equipment requirement removed.')
      await load()
    } catch (caught) {
      setErrors((current) => ({ ...current, [itemId]: requirementErrorMessage(caught) }))
    } finally {
      setBusyId(null)
    }
  }

  if (state.status === 'loading') {
    return <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading equipment requirements…</p>
  }
  if (state.status === 'error') {
    return (
      <div className="font-ui text-sm" style={{ color: C.inkFaint }}>
        <p role="alert">{state.error}</p>
        <button type="button" onClick={load} className="underline mt-1" style={{ color: C.teal }}>Try again</button>
      </div>
    )
  }

  if (!canEdit) {
    return state.requirements.length === 0 ? (
      <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No equipment requirements recorded.</p>
    ) : (
      <ul className="divide-y" style={{ borderColor: C.line }} aria-label="Equipment requirements">
        {state.requirements.map((requirement) => (
          <li key={requirement.id} className="py-3 first:pt-0 last:pb-0 flex justify-between gap-4 font-ui text-sm">
            <span style={{ color: C.ink }}>
              {requirement.equipment.type}
              {!eventId && (
                <span className="block text-xs mt-0.5" style={{ color: C.inkFaint }}>
                  Event {requirement.event_id}
                </span>
              )}
            </span>
            <span style={{ color: C.inkFaint }}>×{requirement.required_quantity}</span>
          </li>
        ))}
      </ul>
    )
  }

  const recorded = new Map(state.requirements.map((requirement) => [requirement.equipment_item_id, requirement]))
  return (
    <div>
      {notice && <p role="status" className="font-ui text-sm mb-4" style={{ color: C.green }}>{notice}</p>}
      {state.items.length === 0 ? (
        <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No active equipment is available.</p>
      ) : (
        <ul className="space-y-4" aria-label="Equipment requirements editor">
          {state.items.map((item) => {
            const existing = recorded.get(item.id)
            const error = errors[item.id]
            return (
              <li key={item.id} className="border rounded-sm p-4" style={{ borderColor: C.line }}>
                <div className="flex items-start gap-3 mb-3">
                  <Package size={18} aria-hidden="true" style={{ color: C.teal }} />
                  <div className="min-w-0">
                    <p className="font-ui text-sm font-medium" style={{ color: C.ink }}>{item.type}</p>
                    <p className="font-ui text-xs" style={{ color: C.inkFaint }}>{item.total_quantity} in catalogue</p>
                  </div>
                </div>
                <div className="flex flex-wrap items-start gap-2">
                  <div>
                    <label htmlFor={`requirement-${item.id}`} className="sr-only">{item.type} quantity</label>
                    <input
                      id={`requirement-${item.id}`}
                      type="number"
                      min="1"
                      value={quantities[item.id] ?? ''}
                      onChange={(event) => {
                        setQuantities((current) => ({ ...current, [item.id]: event.target.value }))
                        setErrors((current) => ({ ...current, [item.id]: undefined }))
                      }}
                      aria-invalid={Boolean(error)}
                      aria-describedby={error ? `requirement-${item.id}-error` : undefined}
                      className="csp-input w-28 rounded-sm px-3 py-2 font-ui text-sm"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => save(item.id)}
                    disabled={busyId === item.id}
                    className="px-4 py-2 rounded-sm font-ui text-sm font-medium disabled:opacity-60"
                    style={{ backgroundColor: C.teal, color: C.paper }}
                  >
                    {busyId === item.id ? <Loader2 size={16} className="animate-spin" aria-label="Saving" /> : 'Save'}
                  </button>
                  {existing && (
                    <button
                      type="button"
                      onClick={() => remove(item.id)}
                      disabled={busyId === item.id}
                      aria-label={`Remove ${item.type} requirement`}
                      className="p-2 rounded-sm border disabled:opacity-60"
                      style={{ borderColor: C.rose, color: C.rose }}
                    >
                      <Trash2 size={17} aria-hidden="true" />
                    </button>
                  )}
                </div>
                {error && <p id={`requirement-${item.id}-error`} role="alert" className="font-ui text-xs mt-2" style={{ color: C.rose }}>{error}</p>}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
