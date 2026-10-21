"""S-17: a booking Venue Staff rejected can be replaced through S-78's flow,
so the rejection stops blocking the event's Operational Safety Check."""

from .test_replacement_venue import (  # noqa: F401 -- fixtures
    A_ID,
    HALL_C,
    HALL_H,
    R1_ID,
    STUDIO_B,
    World,
    booking,
    replace,
    search,
    today,
    world,
)

REJECTED = booking(A_ID, STUDIO_B, 'rejected', decision_reason='Double-booked')


def rejected_world(world, *others):
    world.one = {A_ID: dict(REJECTED)}
    world.by_event = [dict(REJECTED), *others]
    # A rejected booking reserves nothing and is never flagged, so no period.
    world.blocks = {}


# --- TC-VENUEBOOKINGS-099 --------------------------------------------------
def test_rejected_booking_can_be_replaced(client, world):
    rejected_world(world)

    found = search(client)
    assert found.status_code == 200, found.text
    assert 'Hall C' in [row['name'] for row in found.json()['venues']]

    response = replace(client, {'venue_id': HALL_C})

    assert response.status_code == 201, response.text
    [call] = world.posts('/bookings')
    body = call.kwargs['json']
    assert body['replaces_booking_id'] == A_ID
    assert body['venue_id'] == HALL_C
    assert (body['booking_date'], body['start_time'], body['end_time']) == (
        REJECTED['booking_date'], REJECTED['start_time'], REJECTED['end_time']
    )


# --- TC-VENUEBOOKINGS-115 --------------------------------------------------
def test_unflagged_live_booking_still_refused(client, world):
    for status in ('confirmed', 'pending'):
        unflagged = booking(A_ID, STUDIO_B, status)
        world.one = {A_ID: unflagged}
        world.by_event = [unflagged]
        world.blocks = {}

        response = replace(client, {'venue_id': HALL_C})

        assert (response.status_code, response.json()) == (
            409, {'detail': "This booking doesn't need a replacement venue"}
        )
    assert not world.posts('/bookings')


# --- TC-VENUEBOOKINGS-116 --------------------------------------------------
def test_one_waiting_replacement_for_rejected_booking(client, world):
    waiting = booking(R1_ID, HALL_C, 'pending', replaces_booking_id=A_ID)
    rejected_world(world, waiting)

    retry = replace(client, {'venue_id': HALL_C})
    assert retry.status_code == 201
    assert retry.json() == waiting

    other = replace(client, {'venue_id': HALL_H})
    assert (other.status_code, other.json()) == (
        409, {'detail': 'A replacement request for this booking is already with Venue Staff'}
    )
    assert not world.posts('/bookings')
