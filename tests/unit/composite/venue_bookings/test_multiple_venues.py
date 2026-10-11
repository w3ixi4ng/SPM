"""TC-VENUEBOOKINGS-061..066 -- S-79: one event books several venues.

Booking A (Main Hall, 09:00-17:00, held) is already on the event. Every new
request is checked on its own and never releases or changes A.
"""

from unittest.mock import AsyncMock

from .conftest import EVENT_ID, VENUE_ID, fake_response, requested

MAIN_HALL = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
HELD_A = {
    "id": "11111111-1111-4111-8111-111111111111",
    "event_id": EVENT_ID,
    "venue_id": MAIN_HALL,
    "venue_name": "Main Hall",
    "booking_date": "2026-11-12",
    "start_time": "09:00:00",
    "end_time": "17:00:00",
    "status": "held",
}


def with_booking_a(services, *others):
    services.pending = fake_response(200, [HELD_A, *others])


def booking_writes(services):
    return [call.args[0] for call in services.bookings.post.await_args_list]


def test_a_second_venue_at_the_same_time_is_added_alongside_the_first(client, services):
    """TC-VENUEBOOKINGS-061"""
    with_booking_a(services)

    response = client.post(
        "/venue-bookings", json=requested(start_time="13:00", end_time="15:00", notes=None)
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["event_id"], body["venue_id"]) == (EVENT_ID, VENUE_ID)
    assert (body["start_time"], body["end_time"]) == ("13:00:00", "15:00:00")
    assert booking_writes(services) == ["/bookings"]
    assert services.sent_booking()["event_id"] == EVENT_ID


def test_a_second_slot_at_the_same_venue_on_another_day_is_added(client, services):
    """TC-VENUEBOOKINGS-062"""
    services.set_event(end_date="2026-11-13")
    with_booking_a(services)

    response = client.post(
        "/venue-bookings",
        json=requested(venue_id=MAIN_HALL, booking_date="2026-11-13", start_time="09:00", end_time="12:00"),
    )

    assert response.status_code == 201
    assert booking_writes(services) == ["/bookings"]


def test_each_booking_is_checked_for_suitability_on_its_own(client, services):
    """TC-VENUEBOOKINGS-063"""
    with_booking_a(services)

    services.set_venue(name="Seminar Room", capacity=40)
    too_small = client.post("/venue-bookings", json=requested(start_time="13:00", end_time="15:00"))
    services.set_venue()
    outside = client.post("/venue-bookings", json=requested(start_time="17:00", end_time="19:00"))

    assert too_small.status_code == 422
    assert too_small.json()["errors"]["expected_attendance"] == (
        "Seminar Room holds 40 people; this event expects 120"
    )
    assert outside.status_code == 422
    assert outside.json()["errors"]["booking_date"] == (
        "The booking must fall within the event's date and time"
    )
    services.bookings.post.assert_not_called()


def test_each_booking_is_checked_for_availability_on_its_own(client, services):
    """TC-VENUEBOOKINGS-064"""
    with_booking_a(services)
    detail = "Main Hall is already tentatively held on 12 Nov 2026 from 09:00 to 17:00."
    services.bookings.post = AsyncMock(return_value=fake_response(409, {"detail": detail}))

    response = client.post(
        "/venue-bookings", json=requested(venue_id=MAIN_HALL, start_time="16:00", end_time="18:00")
    )

    assert response.status_code == 409
    assert response.json()["detail"] == detail
    assert booking_writes(services) == ["/bookings"]


def test_an_identical_retry_returns_the_existing_booking(client, services):
    """TC-VENUEBOOKINGS-065"""
    b = {**HELD_A, "id": "22222222-2222-4222-8222-222222222222", "venue_id": VENUE_ID,
         "venue_name": "Studio B", "start_time": "13:00:00", "end_time": "15:00:00", "status": "pending"}
    with_booking_a(services, b)

    response = client.post("/venue-bookings", json=requested(start_time="13:00", end_time="15:00"))

    assert response.status_code == 201
    assert response.json() == b
    services.bookings.post.assert_not_called()


def test_the_coordinator_sees_every_booking_for_the_event_with_its_status(client, services):
    """TC-VENUEBOOKINGS-066"""
    rows = [
        HELD_A,
        {**HELD_A, "id": "22222222-2222-4222-8222-222222222222", "venue_id": VENUE_ID,
         "venue_name": "Studio B", "start_time": "13:00:00", "end_time": "15:00:00", "status": "pending"},
        {**HELD_A, "id": "33333333-3333-4333-8333-333333333333", "venue_name": "Seminar Room",
         "status": "rejected", "decision_reason": "Too small"},
        {**HELD_A, "id": "55555555-5555-4555-8555-555555555555", "booking_date": "2026-11-13",
         "status": "confirmed"},
    ]
    services.pending = fake_response(200, rows)
    # Clash lookups (S-75) read each venue; none of these clash.
    services.set_venue(setup_minutes=0, turnaround_minutes=0)

    response = client.get(f"/venue-bookings?event_id={EVENT_ID}")

    assert response.status_code == 200
    listed = response.json()
    assert [row["id"] for row in listed] == [row["id"] for row in rows]
    assert [row["status"] for row in listed] == ["held", "pending", "rejected", "confirmed"]
    assert {row["event_id"] for row in listed} == {EVENT_ID}
    assert listed[2]["decision_reason"] == "Too small"
    services.bookings.post.assert_not_called()
    services.events.post.assert_not_called()
    services.events.patch.assert_not_called()
