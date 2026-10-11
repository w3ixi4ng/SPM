"""S-76: TC-VENUEBOOKINGS-059 and 060, booking conflicts for Venue Staff."""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from .conftest import BOOKING_ID, VENUE, VENUE_ID, app_module, fake_response, me

TODAY = date(2026, 11, 10)
DAY = "2026-11-12"
HALL_C_ID = "c0c0c0c0-0000-4000-8000-0000000000c0"
STUDIO_D_ID = "d0d0d0d0-0000-4000-8000-0000000000d0"
GONE_ID = "90909090-0000-4000-8000-000000000090"

STUDIO_B = {**VENUE, "setup_minutes": 30, "turnaround_minutes": 45}
HALL_C = {**VENUE, "id": HALL_C_ID, "name": "Hall C", "setup_minutes": 15, "turnaround_minutes": 15}
STUDIO_D = {**VENUE, "id": STUDIO_D_ID, "name": "Studio D", "setup_minutes": 0, "turnaround_minutes": 0}

REFUSED = ("Can't confirm this booking: it overlaps Alumni talk (confirmed), which occupies Studio B "
           "on 12 Nov 2026 from 09:30 to 12:45 (event 10:00–12:00, 30 min setup, 45 min turnaround).")


def row(booking_id, venue_id, status, start, end, event_name):
    return {
        "id": booking_id, "venue_id": venue_id, "event_id": f"e-{booking_id}", "status": status,
        "booking_date": DAY, "start_time": f"{start}:00", "end_time": f"{end}:00",
        "event_name": event_name, "coordinator_name": f"{event_name} coordinator", "venue_name": "x",
    }


A = row("aaaaaaaa-0000-4000-8000-00000000000a", VENUE_ID, "confirmed", "10:00", "12:00", "Alumni talk")
B = row("bbbbbbbb-0000-4000-8000-00000000000b", VENUE_ID, "held", "12:30", "14:00", "Board lunch")
F = row("ffffffff-0000-4000-8000-00000000000f", HALL_C_ID, "confirmed", "09:00", "10:00", "Morning yoga")
G = row("abcdabcd-0000-4000-8000-00000000000a", HALL_C_ID, "confirmed", "10:15", "11:00", "Book club")
LOST = row("12121212-0000-4000-8000-000000000012", GONE_ID, "confirmed", "10:00", "11:00", "Orphan")


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(app_module, "_today", lambda: TODAY)


@pytest.fixture
def staff(services):
    services.user = me("venue_staff")
    services.venues.get = AsyncMock(return_value=fake_response(200, [STUDIO_B, STUDIO_D, HALL_C]))
    services.bookings.get = AsyncMock(return_value=fake_response(200, [A, B, F, G, LOST]))
    return services


# --- TC-VENUEBOOKINGS-059 --------------------------------------------------
@pytest.mark.parametrize("action, body, detail", [
    ("decision", {"decision": "approved"}, REFUSED),
    ("hold", None, REFUSED.replace("Can't confirm", "Can't hold")),
])
def test_a_refused_approval_reaches_venue_staff_unchanged(client, services, action, body, detail):
    services.user = me("venue_staff")
    services.bookings.post = AsyncMock(return_value=fake_response(409, {"detail": detail}))

    response = client.post(f"/venue-bookings/{BOOKING_ID}/{action}", json=body)

    assert response.status_code == 409
    assert response.json() == {"detail": detail}


def test_an_already_decided_request_still_says_so(client, services):
    services.user = me("venue_staff")
    services.bookings.post = AsyncMock(return_value=fake_response(
        409, {"detail": "This booking request has already been decided"}))

    response = client.post(f"/venue-bookings/{BOOKING_ID}/decision", json={"decision": "approved"})

    assert response.json() == {"detail": "This booking request has already been decided"}


# --- TC-VENUEBOOKINGS-060 --------------------------------------------------
def test_venue_staff_list_every_clash_to_review(client, staff):
    response = client.get("/venue-bookings/clashes")

    assert response.status_code == 200, response.text
    flagged = response.json()["venues"]
    assert [venue["venue_name"] for venue in flagged] == ["Hall C", "Studio B"]
    hall_c, studio_b = flagged
    assert (hall_c["setup_minutes"], hall_c["turnaround_minutes"]) == (15, 15)
    assert (studio_b["setup_minutes"], studio_b["turnaround_minutes"]) == (30, 45)
    [[first, second]] = [[pair["first"], pair["second"]] for pair in hall_c["pairs"]]
    assert (first["event_name"], first["status"], first["occupied_end"]) == ("Morning yoga", "confirmed", "10:15")
    assert (second["event_name"], second["status"], second["occupied_start"]) == ("Book club", "confirmed", "10:00")
    assert first["coordinator_name"] == "Morning yoga coordinator"
    assert [(p["first"]["event_name"], p["second"]["event_name"]) for p in studio_b["pairs"]] == [
        ("Alumni talk", "Board lunch")]
    staff.bookings.get.assert_awaited_once()
    assert staff.bookings.get.await_args.kwargs["params"] == {"status": "live", "from": "2026-11-10"}


def test_reviewing_clashes_changes_nothing(client, staff):
    client.get("/venue-bookings/clashes")

    staff.bookings.post.assert_not_called()
    assert not staff.bookings.patch.called
    assert not staff.bookings.delete.called


@pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "technical_support"])
def test_only_venue_staff_review_clashes(client, staff, role):
    staff.user = me(role)

    assert client.get("/venue-bookings/clashes").status_code == 403
    staff.bookings.get.assert_not_called()


@pytest.mark.parametrize("failing", ["venues", "bookings"])
def test_a_failing_service_is_a_502_never_an_empty_list(client, staff, failing):
    getattr(staff, failing).get = AsyncMock(return_value=fake_response(500, {"detail": "boom"}))

    response = client.get("/venue-bookings/clashes")

    assert response.status_code == 502


def test_one_venue_is_still_listed_as_before(client, staff):
    staff.venues.get = AsyncMock(return_value=fake_response(200, STUDIO_B))
    staff.bookings.get = AsyncMock(return_value=fake_response(200, [A, B]))

    response = client.get("/venue-bookings/clashes", params={"venue_id": VENUE_ID})

    assert response.status_code == 200
    assert "pairs" in response.json() and "venues" not in response.json()
