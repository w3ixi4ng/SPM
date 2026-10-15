"""S-80: the assigned Coordinator changes or cancels one booking.

TC-VENUEBOOKINGS-093..072. The fakes hold booking B of event E; any write
the composite makes is recorded, so a write to another booking would show.
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from .conftest import BOOKING_ID, EVENT_ID, VENUE_ID, fake_response, me

URL = f"/venue-bookings/{BOOKING_ID}"
STUDIO_C = "dddddddd-dddd-4ddd-8ddd-000000000002"
CHANGE = {
    "venue_id": STUDIO_C,
    "booking_date": "2026-11-12",
    "start_time": "14:00",
    "end_time": "16:00",
    "notes": "Move to Studio C",
}
NOT_IN_PLANNING = "A venue can only be requested for an event in planning"


@pytest.fixture
def writes(services):
    """Every bookings write, recorded. Change answers with B pending at the
    new time; cancel with 204."""
    services.set_venue(id=STUDIO_C, name="Studio C", setup_minutes=15, turnaround_minutes=30)
    services.bookings.patch = AsyncMock(return_value=fake_response(200, {
        "id": BOOKING_ID, "event_id": EVENT_ID, "venue_id": STUDIO_C, "venue_name": "Studio C",
        "status": "pending", "booking_date": "2026-11-12", "start_time": "14:00:00", "end_time": "16:00:00",
    }))
    services.bookings.delete = AsyncMock(return_value=fake_response(204))
    return services


def _booking(services, **changes):
    services.booking = fake_response(200, {
        "id": BOOKING_ID, "venue_id": VENUE_ID, "event_id": EVENT_ID, "status": "held",
        "booking_date": "2026-11-12", "start_time": "13:00:00", "end_time": "15:00:00", **changes,
    })


def _no_writes(services):
    services.bookings.patch.assert_not_called()
    services.bookings.delete.assert_not_called()
    services.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-093 ----------------------------------------------------
def test_the_assigned_coordinator_changes_one_booking(client, writes):
    _booking(writes)

    response = client.patch(URL, json=CHANGE, cookies={"sb_access_token": "k"})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"
    event_reads = [call.args[0] for call in writes.events.get.await_args_list]
    assert f"/events/assigned/{EVENT_ID}" in event_reads
    writes.bookings.patch.assert_awaited_once()
    call = writes.bookings.patch.await_args
    assert call.args == (f"/bookings/{BOOKING_ID}",)
    assert call.kwargs["json"] == {**CHANGE, "start_time": "14:00:00", "end_time": "16:00:00", "venue_name": "Studio C"}
    assert call.kwargs["params"] == {"setup_minutes": 15, "turnaround_minutes": 30}
    assert call.kwargs["cookies"] == {"sb_access_token": "k"}
    writes.bookings.delete.assert_not_called()
    writes.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-094 ----------------------------------------------------
def test_an_unsuitable_change_is_refused_before_anything_is_written(client, writes):
    _booking(writes)
    writes.set_venue(id=STUDIO_C, name="Studio C", capacity=40)
    too_small = client.patch(URL, json=CHANGE)

    writes.set_venue(id=STUDIO_C, name="Studio C")
    outside = client.patch(URL, json={**CHANGE, "start_time": "17:00", "end_time": "19:00"})

    assert too_small.status_code == 422
    assert "expected_attendance" in too_small.json()["errors"]
    assert outside.status_code == 422
    assert "booking_date" in outside.json()["errors"]
    _no_writes(writes)


# --- TC-VENUEBOOKINGS-095 ----------------------------------------------------
@pytest.mark.parametrize(
    ("setup", "expected_status", "expected_detail"),
    [
        (lambda s: setattr(s, "user", me("venue_staff")), 403, "Permission denied"),
        (lambda s: setattr(s, "event", fake_response(404, {"detail": "Event not found"})), 404, "Event not found"),
        (lambda s: s.set_event(status="confirmed"), 409, NOT_IN_PLANNING),
        (lambda s: _booking(s, status="rejected"), 409, "Only a pending, held or confirmed booking can be changed"),
        (lambda s: setattr(s, "booking", fake_response(404, {"detail": "Booking not found"})), 404, "Booking not found"),
    ],
    ids=["not-coordinator", "not-assigned", "not-planning", "rejected", "missing"],
)
def test_a_change_that_isnt_allowed_is_refused(client, writes, setup, expected_status, expected_detail):
    _booking(writes)
    setup(writes)

    response = client.patch(URL, json=CHANGE)

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    _no_writes(writes)


def test_a_conflicting_change_keeps_the_bookings_services_wording(client, writes):
    _booking(writes)
    detail = "Studio C is already confirmed on 12 Nov 2026 from 13:00 to 15:00."
    writes.bookings.patch = AsyncMock(return_value=fake_response(409, {"detail": detail}))

    response = client.patch(URL, json=CHANGE)

    assert response.status_code == 409
    assert response.json()["detail"] == detail


# --- TC-VENUEBOOKINGS-096 ----------------------------------------------------
def test_the_assigned_coordinator_cancels_one_booking(client, writes):
    _booking(writes, status="confirmed")

    response = client.delete(URL, cookies={"sb_access_token": "k"})

    assert response.status_code == 204
    writes.bookings.delete.assert_awaited_once()
    call = writes.bookings.delete.await_args
    assert call.args == (f"/bookings/{BOOKING_ID}",)
    assert call.kwargs["cookies"] == {"sb_access_token": "k"}
    writes.bookings.patch.assert_not_called()
    writes.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-097 ----------------------------------------------------
@pytest.mark.parametrize(
    ("setup", "expected_status", "expected_detail"),
    [
        (lambda s: setattr(s, "user", me("event_organiser")), 403, "Permission denied"),
        (lambda s: setattr(s, "event", fake_response(404, {"detail": "Event not found"})), 404, "Event not found"),
        (lambda s: s.set_event(status="cancelled"), 409, NOT_IN_PLANNING),
        (lambda s: _booking(s, status="rejected"), 409, "Only a pending, held or confirmed booking can be cancelled"),
        (lambda s: setattr(s, "booking", fake_response(404, {"detail": "Booking not found"})), 404, "Booking not found"),
    ],
    ids=["not-coordinator", "not-assigned", "not-planning", "rejected", "missing"],
)
def test_a_cancellation_that_isnt_allowed_is_refused(client, writes, setup, expected_status, expected_detail):
    _booking(writes)
    setup(writes)

    response = client.delete(URL)

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    _no_writes(writes)


# --- TC-VENUEBOOKINGS-098 ----------------------------------------------------
def test_a_failed_write_never_reports_success(client, writes):
    _booking(writes)
    writes.bookings.patch = AsyncMock(return_value=fake_response(500, {"detail": "Booking storage unavailable"}))
    writes.bookings.delete = AsyncMock(return_value=fake_response(500, {"detail": "Booking storage unavailable"}))

    assert client.patch(URL, json=CHANGE).status_code == 502
    assert client.delete(URL).status_code == 502


@pytest.mark.parametrize("service", ["events", "venues"])
def test_an_unreachable_service_never_reports_success(client, writes, service):
    _booking(writes)
    getattr(writes, service).get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    assert client.patch(URL, json=CHANGE).status_code == 502
    if service == "events":
        assert client.delete(URL).status_code == 502
    _no_writes(writes)
