"""S-90: restoring the original booking, TC-VENUEBOOKINGS-131..135.

The composite decides who may ask and when, passes the venue's current setup
and turnaround to the bookings service, and records each step in the event's
history. Every service is a path-answering fake.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from .conftest import fake_response

COOKIE = {"sb_access_token": "token"}
K = "22222222-0000-4000-8000-000000000002"
STAFF = "abababab-abab-4bab-8bab-abababababab"
E = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
O_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
R_ID = "11111111-1111-4111-8111-111111111111"
STUDIO_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
HALL_C = "cccccccc-0000-4000-8000-000000000000"
NOT_OFFERED = "Restore is only possible while a replacement is waiting for Venue Staff."
CLOSED = "This event's venue bookings can no longer be changed"


def booking(id_, venue, name, status, **changes):
    return {
        "id": id_, "event_id": E, "venue_id": venue, "venue_name": name, "status": status,
        "booking_date": "2026-11-12", "start_time": "10:00:00", "end_time": "12:00:00",
        "event_name": "Alumni networking evening", "replaces_booking_id": None, **changes,
    }


O = booking(O_ID, STUDIO_B, "Studio B", "confirmed")
R = booking(R_ID, HALL_C, "Hall C", "pending", replaces_booking_id=O_ID)
REQUESTED = {**O, "restore_requested_at": "2026-11-01T02:00:00Z", "restore_requested_by": K}


class Fakes:
    def __init__(self):
        self.role, self.user_id = "event_coordinator", K
        self.event_status = "confirmed"
        self.assigned = 200
        self.original = dict(O)
        self.event_bookings = [dict(O), dict(R)]
        self.restore_requested = [dict(REQUESTED)]
        self.answer = fake_response(200, dict(REQUESTED))
        self.users = MagicMock(get=AsyncMock(side_effect=self._me))
        self.events = MagicMock(get=AsyncMock(side_effect=self._event),
                                post=AsyncMock(return_value=fake_response(201, {})))
        self.venues = MagicMock(get=AsyncMock(return_value=fake_response(200, {
            "id": STUDIO_B, "name": "Studio B", "setup_minutes": 30, "turnaround_minutes": 45,
        })))
        self.bookings = MagicMock(get=AsyncMock(side_effect=self._bookings_get),
                                  post=AsyncMock(side_effect=lambda path, **kw: self.answer))
        self.notifications = MagicMock(post=AsyncMock())

    async def _me(self, path, **kwargs):
        return fake_response(200, {"id": self.user_id, "name": "Ben Tan", "email": "b@example.com",
                                   "role": self.role})

    async def _event(self, path, **kwargs):
        assert path == f"/events/assigned/{E}", path
        if self.assigned != 200:
            return fake_response(self.assigned, {"detail": "Event not found"})
        return fake_response(200, {"id": E, "status": self.event_status})

    async def _bookings_get(self, path, params=None, **kwargs):
        if path == f"/bookings/{O_ID}":
            return fake_response(200, self.original)
        if params and params.get("restore_requested") == "true":
            return fake_response(200, self.restore_requested)
        if params and params.get("event_id") == E:
            return fake_response(200, self.event_bookings)
        raise AssertionError(f"unexpected bookings.get({path!r}, {params!r})")

    def posts(self, path):
        return [call for call in self.bookings.post.call_args_list if call.args[0] == path]

    def history(self):
        return [call.kwargs["json"] for call in self.events.post.call_args_list]


@pytest.fixture
def services():
    return Fakes()


def _restore(client):
    return client.post(f"/venue-bookings/{O_ID}/restore", cookies=COOKIE)


def _decide(client, decision):
    return client.post(f"/venue-bookings/{O_ID}/restore-decision",
                       json={"decision": decision}, cookies=COOKIE)


# --- TC-VENUEBOOKINGS-131 -------------------------------------------------
def test_the_assigned_coordinator_asks_to_restore_the_original(client, services):
    response = _restore(client)

    assert response.status_code == 200, response.text
    assert response.json()["restore_requested_by"] == K
    [call] = services.posts(f"/bookings/{O_ID}/restore-request")
    assert call.kwargs["params"] == {"setup_minutes": 30, "turnaround_minutes": 45}
    assert call.kwargs["cookies"] == COOKIE
    [entry] = services.history()
    assert entry["action"] == "venue_restore_requested"
    assert entry["details"]["venue_name"] == "Studio B"
    assert entry["details"]["replacement_venue_name"] == "Hall C"


# --- TC-VENUEBOOKINGS-132 -------------------------------------------------
@pytest.mark.parametrize("case, status_code, detail", [
    ("no replacement", 409, NOT_OFFERED),
    ("replacement confirmed", 409, NOT_OFFERED),
    ("replacement rejected", 409, NOT_OFFERED),
    ("event cancelled", 409, CLOSED),
    ("not assigned", 404, "Booking not found"),
    ("venue staff", 403, None),
])
def test_restore_is_offered_only_while_a_replacement_waits(client, services, case, status_code, detail):
    if case == "no replacement":
        services.event_bookings = [dict(O)]
    elif case == "replacement confirmed":
        services.original = {**O, "status": "replaced", "replaced_by_booking_id": R_ID}
        services.event_bookings = [services.original, {**R, "status": "confirmed"}]
    elif case == "replacement rejected":
        services.event_bookings = [dict(O), {**R, "status": "rejected"}]
    elif case == "event cancelled":
        services.event_status = "cancelled"
    elif case == "not assigned":
        services.assigned = 404
    else:
        services.role, services.user_id = "venue_staff", STAFF

    response = _restore(client)

    assert response.status_code == status_code, response.text
    if detail:
        assert response.json()["detail"] == detail
    assert services.posts(f"/bookings/{O_ID}/restore-request") == []
    assert services.history() == []


# --- TC-VENUEBOOKINGS-133 -------------------------------------------------
@pytest.mark.parametrize("detail", [
    "Studio B is unavailable from 12 Nov 2026 12:30 to 12 Nov 2026 14:00.",
    "A restore has already been requested for this booking",
])
def test_the_bookings_services_refusal_reaches_the_coordinator(client, services, detail):
    services.answer = fake_response(409, {"detail": detail})

    response = _restore(client)

    assert (response.status_code, response.json()["detail"]) == (409, detail)
    assert services.history() == []


@pytest.mark.parametrize("failure", [
    fake_response(500, {"detail": "boom"}), httpx.ConnectError("bookings down"),
])
def test_a_bookings_failure_is_a_502(client, services, failure):
    if isinstance(failure, Exception):
        services.bookings.post.side_effect = failure
    else:
        services.answer = failure
    response = _restore(client)
    assert (response.status_code, response.json()["detail"]) == (502, "Bookings service unavailable")


# --- TC-VENUEBOOKINGS-134 -------------------------------------------------
def test_venue_staff_see_each_restore_request_with_the_replacement_it_would_withdraw(client, services):
    services.role, services.user_id = "venue_staff", STAFF

    response = client.get("/venue-bookings/restores", cookies=COOKIE)

    assert response.status_code == 200, response.text
    [row] = response.json()
    assert row["id"] == O_ID
    assert row["replacement"] == {
        "id": R_ID, "venue_name": "Hall C", "booking_date": "2026-11-12",
        "start_time": "10:00:00", "end_time": "12:00:00", "status": "pending",
    }
    services.role, services.user_id = "event_coordinator", K
    assert client.get("/venue-bookings/restores", cookies=COOKIE).status_code == 403


# --- TC-VENUEBOOKINGS-135 -------------------------------------------------
def test_venue_staff_confirm_or_decline_the_restore(client, services):
    services.role, services.user_id = "venue_staff", STAFF
    services.original = dict(REQUESTED)
    resolved = {**O, "alternative_resolution_note": "Restored to the original venue"}
    services.answer = fake_response(200, {"booking": resolved, "withdrawn": [{**R, "status": "withdrawn"}]})

    confirmed = _decide(client, "approved")

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["withdrawn"][0]["status"] == "withdrawn"
    [call] = services.posts(f"/bookings/{O_ID}/restore-decision")
    assert call.kwargs["json"] == {"decision": "approved"}
    assert call.kwargs["params"] == {"setup_minutes": 30, "turnaround_minutes": 45}
    [entry] = services.history()
    assert entry["action"] == "venue_restore_confirmed"
    assert (entry["details"]["venue_name"], entry["details"]["replacement_venue_name"]) == ("Studio B", "Hall C")

    services.answer = fake_response(200, {"booking": dict(O), "withdrawn": []})
    declined = _decide(client, "declined")
    assert declined.status_code == 200
    assert services.history()[-1]["action"] == "venue_restore_declined"

    detail = "Can't restore this booking: it overlaps Careers fair (confirmed), which occupies ..."
    services.answer = fake_response(409, {"detail": detail})
    refused = _decide(client, "approved")
    assert (refused.status_code, refused.json()["detail"]) == (409, detail)
    assert len(services.history()) == 2

    assert _decide(client, "maybe").status_code == 422
    services.role, services.user_id = "event_coordinator", K
    assert _decide(client, "approved").status_code == 403
