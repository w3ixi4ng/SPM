import { listEquipmentRequirements } from './equipmentRequirements.js'
import { listVenueBookingsForEvent } from './venueBookings.js'

const unavailable = (id, label) => ({
  id,
  label,
  state: 'unavailable',
  detail: 'This area has not been developed yet',
})

export function buildEventReadiness(event, bookings, requirements) {
  const venueComplete = bookings.some((booking) => booking.status === 'confirmed')
  const equipmentComplete = requirements.length > 0
  const supportComplete = event.equipment_preparation_status === 'ready'

  const areas = [
    {
      id: 'venue',
      label: 'Venue',
      state: venueComplete ? 'complete' : 'outstanding',
      detail: venueComplete ? 'Confirmed booking recorded' : 'A confirmed venue is still required',
    },
    {
      id: 'equipment',
      label: 'Equipment',
      state: equipmentComplete ? 'complete' : 'outstanding',
      detail: equipmentComplete ? 'Requirements recorded' : 'Equipment requirements are still required',
    },
    {
      id: 'technical_support',
      label: 'Technical support',
      state: supportComplete ? 'complete' : 'outstanding',
      detail: supportComplete
        ? 'Equipment preparation is Ready'
        : `Equipment preparation is ${event.equipment_preparation_status === 'in_progress' ? 'In Progress' : 'Not Started'}`,
    },
    unavailable('programme', 'Programme'),
    unavailable('registration', 'Registration'),
  ]
  const implemented = areas.filter(({ state }) => state !== 'unavailable')
  const complete = implemented.filter(({ state }) => state === 'complete').length
  return {
    areas,
    summary: {
      complete,
      available: implemented.length,
      ready: complete === implemented.length,
    },
  }
}

export async function loadEventReadiness(eventId, event) {
  const [bookings, requirements] = await Promise.all([
    listVenueBookingsForEvent(eventId),
    listEquipmentRequirements(eventId),
  ])
  return buildEventReadiness(event, bookings, requirements)
}
