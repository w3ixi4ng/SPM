import { useEffect, useState } from 'react'
import { ArrowLeft, PackagePlus } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import {
  createEquipment,
  EQUIPMENT_OPERATIONAL_STATUSES,
  emptyEquipmentForm,
  equipmentErrorMessage,
  equipmentFieldErrorsToForm,
  equipmentReadToForm,
  getEquipment,
  updateEquipment,
  validateEquipmentForm,
} from '../lib/equipment.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
  rose: '#B25547',
}

function FieldError({ id, message }) {
  if (!message) return null
  return <p id={id} role="alert" className="font-ui text-xs mt-1.5" style={{ color: C.rose }}>{message}</p>
}

export default function EquipmentForm() {
  const navigate = useNavigate()
  const { id } = useParams()
  const editing = Boolean(id)
  const [form, setForm] = useState(emptyEquipmentForm)
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(editing)

  useEffect(() => {
    if (!editing) return undefined
    let active = true
    getEquipment(id)
      .then((item) => {
        if (active) setForm(equipmentReadToForm(item))
      })
      .catch((error) => {
        if (active) setFormError(equipmentErrorMessage(error))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [editing, id])

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
    const errorField = field === 'totalQuantity'
      ? 'total_quantity'
      : field === 'operationalStatus' ? 'operational_status' : field
    if (errors[errorField]) setErrors((current) => ({ ...current, [errorField]: undefined }))
    if (formError) setFormError(null)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const found = validateEquipmentForm(form, { editing })
    setErrors(found)
    if (Object.keys(found).length) {
      setFormError('Complete the highlighted fields before saving.')
      const target = found.type
        ? '#equipment-type'
        : found.total_quantity ? '#equipment-quantity' : '#equipment-status'
      document.querySelector(target)?.focus()
      return
    }

    setSaving(true)
    setFormError(null)
    try {
      const item = editing ? await updateEquipment(id, form) : await createEquipment(form)
      navigate('/dashboard/technical-support', {
        replace: true,
        state: {
          notice: editing
            ? `${item.type} was updated in the equipment catalogue.`
            : `${item.type} was added to the equipment catalogue.`,
        },
      })
    } catch (error) {
      setErrors(equipmentFieldErrorsToForm(error.fieldErrors))
      setFormError(equipmentErrorMessage(error))
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <div className="w-full max-w-2xl mx-auto">
        <header className="flex items-center justify-between gap-6 mb-12">
          <Logo />
          <Link to="/dashboard/technical-support" className="inline-flex items-center gap-2 font-ui text-sm" style={{ color: C.ink }}>
            <ArrowLeft size={15} aria-hidden="true" />
            Back to equipment
          </Link>
        </header>

        <div className="flex items-center gap-3 mb-3">
          <PackagePlus size={22} aria-hidden="true" style={{ color: C.teal }} />
          <p className="font-ui text-xs uppercase tracking-widest" style={{ color: C.teal }}>Equipment catalogue</p>
        </div>
        <h1 className="font-display text-4xl sm:text-5xl mb-3" style={{ color: C.ink }}>
          {editing ? 'Edit equipment item' : 'Add equipment item'}
        </h1>
        <p className="font-ui text-sm mb-10" style={{ color: C.inkFaint }}>
          {editing
            ? 'Update the catalogue details and current operational status.'
            : 'Add one equipment type or pool and the total number currently held.'}
        </p>

        {formError && <p role="alert" className="font-ui text-sm mb-6" style={{ color: C.rose }}>{formError}</p>}

        {loading && <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading equipment item…</p>}

        {!loading && <form onSubmit={handleSubmit} noValidate className="space-y-7">
          <div>
            <label htmlFor="equipment-type" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
              Type or name (required)
            </label>
            <input
              id="equipment-type"
              value={form.type}
              onChange={(event) => update('type', event.target.value)}
              aria-invalid={Boolean(errors.type)}
              aria-describedby={errors.type ? 'equipment-type-error' : undefined}
              className="w-full rounded-sm border px-4 py-3 font-ui text-sm"
              style={{ borderColor: errors.type ? C.rose : C.line, backgroundColor: C.paper, color: C.ink }}
            />
            <FieldError id="equipment-type-error" message={errors.type} />
          </div>

          <div>
            <label htmlFor="equipment-description" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
              Description (optional)
            </label>
            <textarea
              id="equipment-description"
              rows={4}
              value={form.description}
              onChange={(event) => update('description', event.target.value)}
              className="w-full rounded-sm border px-4 py-3 font-ui text-sm"
              style={{ borderColor: C.line, backgroundColor: C.paper, color: C.ink }}
            />
          </div>

          <div>
            <label htmlFor="equipment-quantity" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
              Total quantity (required)
            </label>
            <input
              id="equipment-quantity"
              type="number"
              min="1"
              step="1"
              inputMode="numeric"
              value={form.totalQuantity}
              onChange={(event) => update('totalQuantity', event.target.value)}
              aria-invalid={Boolean(errors.total_quantity)}
              aria-describedby={errors.total_quantity ? 'equipment-quantity-error' : undefined}
              className="w-full rounded-sm border px-4 py-3 font-ui text-sm"
              style={{ borderColor: errors.total_quantity ? C.rose : C.line, backgroundColor: C.paper, color: C.ink }}
            />
            <FieldError id="equipment-quantity-error" message={errors.total_quantity} />
          </div>

          {editing && (
            <div>
              <label htmlFor="equipment-status" className="block font-ui text-sm font-medium mb-1.5" style={{ color: C.ink }}>
                Operational status (required)
              </label>
              <select
                id="equipment-status"
                value={form.operationalStatus}
                onChange={(event) => update('operationalStatus', event.target.value)}
                aria-invalid={Boolean(errors.operational_status)}
                aria-describedby={errors.operational_status ? 'equipment-status-error' : undefined}
                className="w-full rounded-sm border px-4 py-3 font-ui text-sm"
                style={{ borderColor: errors.operational_status ? C.rose : C.line, backgroundColor: C.paper, color: C.ink }}
              >
                {EQUIPMENT_OPERATIONAL_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status[0].toUpperCase() + status.slice(1)}
                  </option>
                ))}
              </select>
              <FieldError id="equipment-status-error" message={errors.operational_status} />
            </div>
          )}

          <button
            type="submit"
            disabled={saving}
            className="px-5 py-3 rounded-sm font-ui font-medium disabled:opacity-60"
            style={{ backgroundColor: C.teal, color: C.paper }}
          >
            {saving ? 'Saving…' : editing ? 'Save changes' : 'Add equipment'}
          </button>
        </form>}
      </div>
    </div>
  )
}
