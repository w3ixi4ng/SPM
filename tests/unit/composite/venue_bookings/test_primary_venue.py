"""S-91: assigned Coordinators designate a primary venue."""

from unittest.mock import AsyncMock

import pytest

from .conftest import BOOKING_ID, EVENT_ID, fake_response, me

URL = f"/venue-bookings/{BOOKING_ID}/primary"


def confirmed(**changes):
    return {
        "id": BOOKING_ID,
        "event_id": EVENT_ID,
        "venue_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        "venue_name": "Studio B",
        "status": "confirmed",
        "is_primary": False,
        **changes,
    }


def test_assigned_coordinator_selects_the_primary_venue(client, services):
    services.booking = fake_response(200, confirmed())
    services.bookings.put = AsyncMock(return_value=fake_response(200, confirmed(is_primary=True)))

    response = client.put(URL, cookies={"sb_access_token": "token"})

    assert response.status_code == 200, response.text
    assert response.json()["is_primary"] is True
    event_call = services.events.get.await_args
    assert event_call.args == (f"/events/assigned/{EVENT_ID}",)
    assert event_call.kwargs["cookies"] == {"sb_access_token": "token"}
    services.bookings.put.assert_awaited_once_with(
        f"/bookings/{BOOKING_ID}/primary", cookies={"sb_access_token": "token"}
    )


@pytest.mark.parametrize("role", ["venue_staff", "event_organiser", "attendee"])
def test_other_roles_cannot_select_a_primary(client, services, role):
    services.user = me(role)
    response = client.put(URL)
    assert response.status_code == 403
    services.bookings.put.assert_not_awaited()


def test_an_unassigned_coordinator_cannot_select_a_primary(client, services):
    services.booking = fake_response(200, confirmed())
    services.event = fake_response(404, {"detail": "Event not found"})

    response = client.put(URL)

    assert response.status_code == 404
    services.bookings.put.assert_not_awaited()


@pytest.mark.parametrize("downstream", [404, 409])
def test_identified_booking_selection_failures_are_preserved(client, services, downstream):
    services.booking = fake_response(200, confirmed())
    services.bookings.put = AsyncMock(return_value=fake_response(downstream, {"detail": "refused"}))

    response = client.put(URL)

    assert response.status_code == downstream
    assert response.json()["detail"] == "refused"


def test_the_organiser_lists_every_venue_with_the_primary_marker(client, services):
    rows = [confirmed(is_primary=True), confirmed(id="55555555-5555-4555-8555-555555555555",
                                                  venue_name="Studio C")]
    services.user = me("event_organiser")
    services.pending = fake_response(200, rows)

    response = client.get(f"/venue-bookings?event_id={EVENT_ID}", cookies={"sb_access_token": "token"})

    assert response.status_code == 200, response.text
    assert response.json() == rows
    event_call = services.events.get.await_args
    assert event_call.args == (f"/events/{EVENT_ID}",)
    assert event_call.kwargs["cookies"] == {"sb_access_token": "token"}
    services.venues.get.assert_not_awaited()
