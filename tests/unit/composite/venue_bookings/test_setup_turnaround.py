"""S-75: setup/turnaround and clash warnings, TC-VENUEBOOKINGS-050 to 058."""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from .conftest import (
    BOOKING_ID,
    EVENT_ID,
    VENUE_ID,
    app_module,
    fake_response,
    me,
    requested,
)

TODAY = date(2026, 11, 10)
GAP = {"setup_minutes": 30, "turnaround_minutes": 45}
DAY = "2026-11-12"  # a Thursday


def row(booking_id, status, start, end, event_name, day=DAY, event_id=None):
    return {
        "id": booking_id, "venue_id": VENUE_ID, "event_id": event_id or f"e-{booking_id}",
        "status": status, "booking_date": day, "start_time": f"{start}:00", "end_time": f"{end}:00",
        "event_name": event_name, "coordinator_name": f"{event_name} coordinator", "venue_name": "Studio B",
    }


A = row("aaaaaaaa-0000-4000-8000-00000000000a", "confirmed", "10:00", "12:00", "Alumni talk")
B = row("bbbbbbbb-0000-4000-8000-00000000000b", "held", "12:30", "14:00", "Board lunch", event_id=EVENT_ID)
C = row("cccccccc-0000-4000-8000-00000000000c", "confirmed", "16:00", "17:00", "Careers fair")
D = row("dddddddd-0000-4000-8000-00000000000d", "pending", "12:15", "12:45", "Debate night")
SAME_DAY = [A, B, C, D]


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(app_module, "_today", lambda: TODAY)


@pytest.fixture
def studio_b(services):
    """Studio B with 30 min setup and 45 min turnaround; GET /bookings by venue
    and day answers SAME_DAY, by event answers B."""
    services.set_venue(**GAP)

    async def bookings_get(path, **kwargs):
        params = kwargs.get("params") or {}
        if path.startswith("/bookings/"):
            booking_id = path.rsplit("/", 1)[-1]
            match = [r for r in SAME_DAY if r["id"] == booking_id]
            return fake_response(200, match[0]) if match else fake_response(404, {"detail": "Booking not found"})
        if "venue_id" in params:
            return fake_response(200, SAME_DAY)
        if "event_id" in params:
            return fake_response(200, [B])
        if params.get("status") == "actionable":
            return fake_response(200, [B, D])
        raise AssertionError(f"unexpected bookings.get({path!r}, {params!r})")

    services.bookings.get = AsyncMock(side_effect=bookings_get)
    return services


# --- TC-VENUEBOOKINGS-050 --------------------------------------------------
@pytest.mark.parametrize("start, end, refused", [
    ("08:00", "10:00", True), ("08:30", "10:00", False), ("18:00", "19:15", False), ("18:00", "19:30", True),
])
def test_the_opening_hours_check_covers_setup_and_turnaround(client, services, start, end, refused):
    services.set_venue(**GAP)
    services.set_event(start_time="08:00:00", end_time="20:00:00")

    response = client.post("/venue-bookings", json=requested(start_time=start, end_time=end))

    if refused:
        assert response.status_code == 422
        assert response.json()["errors"]["operating_hours"] == (
            "Studio B is open 08:00–20:00 on Thursdays; with 30 min setup and 45 min "
            "turnaround a booking must run within 08:30–19:15"
        )
        services.bookings.post.assert_not_called()
    else:
        assert response.status_code == 201, response.text


def test_without_setup_and_turnaround_the_whole_day_is_bookable(client, services):
    services.set_event(start_time="08:00:00", end_time="20:00:00")

    response = client.post("/venue-bookings", json=requested(start_time="08:00", end_time="20:00"))

    assert response.status_code == 201, response.text


# --- TC-VENUEBOOKINGS-051 --------------------------------------------------
def test_a_request_passes_the_venues_current_times(client, services):
    services.set_venue(**GAP)

    assert client.post("/venue-bookings", json=requested(start_time="09:00", end_time="12:00")).status_code == 201

    assert services.bookings.post.call_args.kwargs["params"] == GAP


@pytest.mark.parametrize("action, body", [("hold", None), ("decision", {"decision": "approved"})])
def test_holds_and_decisions_pass_the_bookings_venues_current_times(client, studio_b, action, body):
    studio_b.user = me("venue_staff")
    studio_b.bookings.post = AsyncMock(return_value=fake_response(200, {**B, "status": "confirmed"}))

    response = client.post(f"/venue-bookings/{B['id']}/{action}", json=body)

    assert response.status_code == 200, response.text
    assert studio_b.bookings.post.call_args.kwargs["params"] == GAP
    assert studio_b.venues.get.await_args.args[0] == f"/venues/{VENUE_ID}"

    studio_b.set_venue(setup_minutes=0, turnaround_minutes=0)
    client.post(f"/venue-bookings/{B['id']}/{action}", json=body)
    assert studio_b.bookings.post.call_args.kwargs["params"] == {"setup_minutes": 0, "turnaround_minutes": 0}


def test_an_unknown_booking_is_a_404_before_any_write(client, studio_b):
    studio_b.user = me("venue_staff")

    response = client.post("/venue-bookings/99999999-0000-4000-8000-000000000009/hold")

    assert response.status_code == 404
    assert response.json() == {"detail": "Booking not found"}
    studio_b.bookings.post.assert_not_called()


# --- TC-VENUEBOOKINGS-052 --------------------------------------------------
def test_a_refusal_explains_the_setup_and_turnaround(client, services):
    detail = ("Studio B is already confirmed on 12 Nov 2026 from 10:00 to 12:00. "
              "With 30 min setup and 45 min turnaround it is in use until 12:45.")
    services.bookings.post = AsyncMock(return_value=fake_response(409, {"detail": detail}))

    response = client.post("/venue-bookings", json=requested(start_time="12:30", end_time="13:00"))

    assert response.status_code == 409
    assert response.json() == {"detail": detail}


# --- TC-VENUEBOOKINGS-053 --------------------------------------------------
def test_a_coordinators_clashing_booking_carries_a_warning(client, studio_b):
    response = client.get("/venue-bookings", params={"event_id": EVENT_ID})

    assert response.status_code == 200, response.text
    [b] = response.json()
    assert b["clashes"] == [{
        "booking_date": DAY, "start_time": "10:00:00", "end_time": "12:00:00",
        "occupied_start": "09:30", "occupied_end": "12:45", "status": "confirmed",
    }]
    assert (b["setup_minutes"], b["turnaround_minutes"]) == (30, 45)
    assert "Alumni talk" not in response.text and A["id"] not in response.text


@pytest.mark.parametrize("changes", [
    {"status": "pending"}, {"status": "rejected"}, {"booking_date": "2026-11-09"},
    {"start_time": "18:15:00", "end_time": "19:00:00"},  # occupied from 17:45, as C ends
])
def test_other_requests_carry_no_warning(client, studio_b, changes):
    other = {**B, **changes}

    async def bookings_get(path, **kwargs):
        params = kwargs.get("params") or {}
        if "venue_id" in params:
            return fake_response(200, [A, other, C])
        return fake_response(200, [other])

    studio_b.bookings.get = AsyncMock(side_effect=bookings_get)

    [b] = client.get("/venue-bookings", params={"event_id": EVENT_ID}).json()

    assert b["clashes"] == []


# --- TC-VENUEBOOKINGS-054 --------------------------------------------------
def test_venue_staff_list_a_venues_clashing_bookings(client, studio_b):
    studio_b.user = me("venue_staff")

    response = client.get("/venue-bookings/clashes", params={"venue_id": VENUE_ID})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["setup_minutes"], body["turnaround_minutes"]) == (30, 45)
    assert len(body["pairs"]) == 1
    first, second = body["pairs"][0]["first"], body["pairs"][0]["second"]
    assert (first["event_name"], first["status"], first["occupied_end"]) == ("Alumni talk", "confirmed", "12:45")
    assert (second["event_name"], second["status"], second["occupied_start"]) == ("Board lunch", "held", "12:00")
    assert first["coordinator_name"] == "Alumni talk coordinator"
    params = studio_b.bookings.get.await_args.kwargs["params"]
    assert params["venue_id"] == VENUE_ID and params["from"] == "2026-11-10"


@pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "technical_support"])
def test_only_venue_staff_list_clashes(client, studio_b, role):
    studio_b.user = me(role)

    assert client.get("/venue-bookings/clashes", params={"venue_id": VENUE_ID}).status_code == 403
    studio_b.bookings.get.assert_not_called()


def test_clashes_for_an_unknown_venue_is_a_404(client, studio_b):
    studio_b.user = me("venue_staff")
    studio_b.venue = fake_response(404, {"detail": "Venue not found"})

    response = client.get("/venue-bookings/clashes", params={"venue_id": VENUE_ID})

    assert response.status_code == 404
    assert response.json() == {"detail": "Venue not found"}


# --- TC-VENUEBOOKINGS-055 --------------------------------------------------
def test_held_requests_in_the_staff_list_show_their_clashes(client, studio_b):
    studio_b.user = me("venue_staff")

    body = client.get("/venue-bookings/pending").json()

    by_id = {item["id"]: item for item in body}
    assert [c["start_time"] for c in by_id[B["id"]]["clashes"]] == ["10:00:00"]
    assert by_id[D["id"]]["clashes"] == []


# --- TC-VENUEBOOKINGS-056 --------------------------------------------------
def test_the_calendar_reports_the_venues_times(client, studio_b):
    async def bookings_get(path, **kwargs):
        return fake_response(200, [])

    studio_b.bookings.get = AsyncMock(side_effect=bookings_get)

    body = client.get("/venue-bookings/availability",
                      params={"venue_id": VENUE_ID, "from": "2026-11-11", "to": "2026-11-30"}).json()

    assert (body["setup_minutes"], body["turnaround_minutes"]) == (30, 45)


# --- TC-VENUEBOOKINGS-057 --------------------------------------------------
def test_clashes_never_change_or_remove_a_booking(client, studio_b):
    client.get("/venue-bookings", params={"event_id": EVENT_ID})
    studio_b.user = me("venue_staff")
    client.get("/venue-bookings/clashes", params={"venue_id": VENUE_ID})
    client.get("/venue-bookings/pending")

    studio_b.bookings.post.assert_not_called()
    assert not getattr(studio_b.bookings, "patch").called
    assert not getattr(studio_b.bookings, "delete").called


# --- TC-VENUEBOOKINGS-058 --------------------------------------------------
def test_venue_staff_read_one_request_by_id(client, studio_b):
    studio_b.user = me("venue_staff")

    found = client.get(f"/venue-bookings/{B['id']}")
    missing = client.get("/venue-bookings/99999999-0000-4000-8000-000000000009")

    assert found.status_code == 200, found.text
    assert found.json()["id"] == B["id"]
    assert [c["start_time"] for c in found.json()["clashes"]] == ["10:00:00"]
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Booking not found"}


def test_a_decided_request_is_returned_with_its_status(client, studio_b):
    studio_b.user = me("venue_staff")

    response = client.get(f"/venue-bookings/{A['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_only_venue_staff_read_a_request(client, studio_b):
    studio_b.user = me("event_coordinator")

    assert client.get(f"/venue-bookings/{B['id']}").status_code == 403


def test_the_fixed_paths_are_not_read_as_ids(client, studio_b):
    studio_b.user = me("venue_staff")

    assert client.get("/venue-bookings/pending").status_code == 200
    assert client.get("/venue-bookings/clashes", params={"venue_id": VENUE_ID}).status_code == 200


def test_a_rejection_never_depends_on_reading_the_venue(client, studio_b):
    studio_b.user = me("venue_staff")
    studio_b.venue = fake_response(404, {"detail": "Venue not found"})
    studio_b.bookings.post = AsyncMock(return_value=fake_response(200, {**B, "status": "rejected"}))

    response = client.post(f"/venue-bookings/{B['id']}/decision", json={"decision": "rejected", "reason": "Repairs"})

    assert response.status_code == 200, response.text
    studio_b.venues.get.assert_not_called()

