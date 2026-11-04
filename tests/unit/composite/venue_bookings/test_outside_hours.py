"""S-28 reopened: bookings outside edited opening hours are flagged, never
changed. TC-VENUEBOOKINGS-460 to 463."""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from .conftest import EVENT_ID, VENUE, VENUE_ID, app_module, fake_response, me

TODAY = date(2026, 11, 4)
HOURS = {"operating_hours": [{"day": "thu", "open": "10:00:00", "close": "16:00:00"}],
         "setup_minutes": 30, "turnaround_minutes": 0}


def row(letter, status, day, start, end, event_name=None):
    return {
        "id": f"{letter * 8}-0000-4000-8000-00000000000{letter}", "venue_id": VENUE_ID,
        "event_id": EVENT_ID, "status": status, "booking_date": day,
        "start_time": f"{start}:00", "end_time": f"{end}:00",
        "event_name": event_name or f"Event {letter}", "venue_name": "Studio B",
        "coordinator_name": "Grace Hopper",
    }


A = row("a", "confirmed", "2026-11-12", "09:00", "11:00", "Alumni talk")
B = row("b", "held", "2026-11-12", "11:00", "15:00")
C = row("c", "confirmed", "2026-11-12", "15:00", "16:30")
D = row("d", "confirmed", "2026-11-13", "10:00", "12:00")
E = row("e", "pending", "2026-11-12", "08:00", "09:00")
F = row("f", "confirmed", "2026-10-29", "08:00", "09:00")
ALL = [A, B, C, D, E, F]


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(app_module, "_today", lambda: TODAY)


@pytest.fixture
def venue_v(services):
    services.set_venue(**HOURS)

    async def bookings_get(path, **kwargs):
        params = kwargs.get("params") or {}
        if path == "/blocks":
            return fake_response(200, [])
        if "event_id" in params:
            return fake_response(200, [A, B])
        return fake_response(200, ALL)

    services.bookings.get = AsyncMock(side_effect=bookings_get)
    return services


def flagged(entry):
    return (entry["booking_id"], entry["reason"], entry["open"], entry["close"])


# --- TC-VENUEBOOKINGS-460 --------------------------------------------------
def test_venue_staff_see_which_bookings_fall_outside_the_hours(client, venue_v):
    venue_v.user = me("venue_staff")

    response = client.get("/venue-bookings/clashes", params={"venue_id": VENUE_ID})

    assert response.status_code == 200, response.text
    outside = response.json()["outside_hours"]
    assert [flagged(entry) for entry in outside] == [
        (A["id"], "outside_hours", "10:00", "16:00"),
        (C["id"], "outside_hours", "10:00", "16:00"),
        (D["id"], "closed", None, None),
    ]
    assert set(outside[0]) == {"booking_id", "event_name", "booking_date", "start_time", "end_time",
                               "status", "reason", "open", "close"}
    assert (outside[0]["event_name"], outside[0]["status"]) == ("Alumni talk", "confirmed")
    venue_v.bookings.post.assert_not_called()
    assert not venue_v.bookings.patch.called and not venue_v.bookings.delete.called


# --- TC-VENUEBOOKINGS-461 --------------------------------------------------
def test_the_standing_review_list_includes_them(client, venue_v):
    venue_v.user = me("venue_staff")
    venue_v.venues.get = AsyncMock(return_value=fake_response(200, [
        {**VENUE, **HOURS},
        {**VENUE, "id": "99999999-9999-4999-8999-999999999999", "name": "Quiet Hall"},
    ]))
    # No clashing pairs here: A, D and the pending and past ones overlap nothing.
    venue_v.bookings.get = AsyncMock(return_value=fake_response(200, [A, D, E, F]))

    response = client.get("/venue-bookings/clashes")

    assert response.status_code == 200, response.text
    [entry] = response.json()["venues"]
    assert entry["venue_id"] == VENUE_ID and entry["pairs"] == []
    assert [flagged(e) for e in entry["outside_hours"]] == [
        (A["id"], "outside_hours", "10:00", "16:00"),
        (D["id"], "closed", None, None),
    ]


# --- TC-VENUEBOOKINGS-462 --------------------------------------------------
def test_the_coordinators_booking_rows_carry_the_flag(client, venue_v):
    response = client.get("/venue-bookings", params={"event_id": EVENT_ID})

    assert response.status_code == 200, response.text
    rows = {r["id"]: r for r in response.json()}
    assert rows[A["id"]]["outside_hours"] == {"reason": "outside_hours", "open": "10:00", "close": "16:00"}
    assert rows[B["id"]]["outside_hours"] is None
    assert rows[A["id"]]["start_time"] == A["start_time"] and rows[A["id"]]["status"] == "confirmed"


# --- TC-VENUEBOOKINGS-463 --------------------------------------------------
@pytest.mark.parametrize("staff_list", [True, False])
def test_a_venue_that_cant_be_read_fails_the_list(client, venue_v, staff_list):
    venue_v.venue = fake_response(500, {"detail": "boom"})
    if staff_list:
        venue_v.user = me("venue_staff")
        response = client.get("/venue-bookings/clashes", params={"venue_id": VENUE_ID})
    else:
        response = client.get("/venue-bookings", params={"event_id": EVENT_ID})

    assert response.status_code == 502
