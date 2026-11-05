import { listEquipmentRequirements } from './equipmentRequirements.js'
import { listVenueBookingsForEvent } from './venueBookings.js'
import { venuePreparationLabel } from './venueBookings.js'

const unavailable = (id, label) => ({
  id,
  label,
  state: 'unavailable',
  detail: 'This area has not been developed yet',
})

export function buildEventReadiness(event, bookings, requirements) {
  const confirmedVenues = bookings.filter((booking) => booking.status === 'confirmed')
  const readyVenues = confirmedVenues.filter((booking) => booking.venue_preparation_status === 'ready')
  const venueComplete = confirmedVenues.length > 0 && readyVenues.length === confirmedVenues.length
  const equipmentComplete = requirements.length > 0
  // S-26 AC2: preparation only opens after the Safety Officer's approval, so
  // before it Technical support is complete once the arrangements are signed
  // off; after it, preparation must also be Ready.
  const signedOff = event.technical_signoff_decision === 'approved'
  const approved = ['confirmed', 'preparation'].includes(event.status)
  const preparationLabel = event.equipment_preparation_status === 'ready'
    ? 'Ready'
    : event.equipment_preparation_status === 'in_progress' ? 'In Progress' : 'Not Started'
  const supportComplete = signedOff && (!approved || event.equipment_preparation_status === 'ready')
  const supportDetail = !signedOff
    ? 'Technical Support has not approved the equipment arrangements'
    : !approved
      ? 'Equipment preparation starts after the safety check'
      : `Equipment preparation is ${preparationLabel}`

  const areas = [
    {
      id: 'venue',
      label: 'Venue',
      state: venueComplete ? 'complete' : 'outstanding',
      detail: confirmedVenues.length === 0
        ? 'A confirmed venue is still required'
        : `${readyVenues.length} of ${confirmedVenues.length} confirmed venues Ready`,
      items: confirmedVenues.map((booking) => ({
        id: booking.id,
        label: booking.venue_name,
        status: venuePreparationLabel(booking.venue_preparation_status),
      })),
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
      detail: supportDetail,
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
