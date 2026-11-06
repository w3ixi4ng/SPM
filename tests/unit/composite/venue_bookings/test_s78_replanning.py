"""S-78 revision: approving a replacement venue returns a confirmed event, or
one waiting for its safety check, to planning. TC-VENUEBOOKINGS-402..408.

The composite asks the events service to replan *before* it records the
approval, and tells the Coordinator and Organiser when the event moved.
Every service is a path-answering fake that records the order of calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import fake_response

COOKIE = {"sb_access_token": "token"}
STAFF = "abababab-abab-4bab-8bab-abababababab"
K = "22222222-0000-4000-8000-000000000002"
G = "33333333-0000-4000-8000-000000000003"
E = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
O_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
R_ID = "11111111-1111-4111-8111-111111111111"
HALL_V = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
HALL_W = "cccccccc-0000-4000-8000-000000000000"
REPLAN = f"/internal/events/{E}/venue-replanning"
DECISION = f"/bookings/{R_ID}/decision"
COORDINATOR_NOTICE = (
    "Showcase is back in planning: Hall W replaced Hall V. Submit it for a fresh "
    "Operational Safety Check once its arrangements are ready."
)
ORGANISER_NOTICE = (
    "Showcase is back in planning because its venue changed to Hall W. It will be "
    "confirmed again after a fresh Operational Safety Check."
)


def booking(id_, venue, name, status, **changes):
    return {
        "id": id_, "event_id": E, "venue_id": venue, "venue_name": name, "status": status,
        "booking_date": "2026-11-12", "start_time": "18:00:00", "end_time": "21:00:00",
        "event_name": "Showcase", "replaces_booking_id": None, **changes,
    }


O = booking(O_ID, HALL_V, "Hall V", "confirmed")
R = booking(R_ID, HALL_W, "Hall W", "pending", replaces_booking_id=O_ID)


class Fakes:
    def __init__(self):
        self.calls: list[str] = []
        self.replacement = dict(R)
        self.replanned = True
        self.replan_status = 200
        self.decided = fake_response(200, {**R, "status": "confirmed", "decided_at": "2026-11-04T01:00:00Z"})
        self.users = MagicMock(get=AsyncMock(return_value=fake_response(200, {
            "id": STAFF, "name": "Vera Venues", "email": "v@example.com", "role": "venue_staff",
        })))
        self.events = MagicMock(get=AsyncMock(side_effect=self._events_get),
                                post=AsyncMock(side_effect=self._events_post))
        self.venues = MagicMock(get=AsyncMock(return_value=fake_response(200, {
            "id": HALL_W, "name": "Hall W", "setup_minutes": 0, "turnaround_minutes": 0,
        })))
        self.bookings = MagicMock(get=AsyncMock(side_effect=self._bookings_get),
                                  post=AsyncMock(side_effect=self._bookings_post))
        self.notifications = MagicMock(post=AsyncMock(
            side_effect=lambda path, **kw: fake_response(201, kw["json"]["notifications"])
        ))

    async def _events_get(self, path, **kwargs):
        assert path == f"/internal/events/{E}/notification-scope", path
        return fake_response(200, {"id": E, "organiser_id": G, "name": "Showcase",
                                   "status": "planning", "assigned_coordinator_id": K})

    async def _events_post(self, path, **kwargs):
        self.calls.append(path)
        if path == REPLAN:
            if self.replan_status != 200:
                return fake_response(self.replan_status, {"detail": "private diagnostic"})
            return fake_response(200, {"replanned": self.replanned, "status": "planning"})
        return fake_response(201, {})  # the composite's history entries

    async def _bookings_get(self, path, **kwargs):
        if path == f"/bookings/{R_ID}":
            return fake_response(200, self.replacement)
        if path == f"/bookings/{O_ID}":
            return fake_response(200, dict(O))
        raise AssertionError(f"unexpected bookings.get({path!r})")

    async def _bookings_post(self, path, **kwargs):
        self.calls.append(path)
        assert path == DECISION, path
        return self.decided

    def replans(self):
        return [call for call in self.events.post.call_args_list if call.args[0] == REPLAN]

    def notices(self):
        return [row for call in self.notifications.post.call_args_list
                for row in call.kwargs["json"]["notifications"]]

    def replanned_notices(self):
        return [row for row in self.notices() if "is back in planning" in row["message"]]


@pytest.fixture
def services():
    return Fakes()


@pytest.fixture(autouse=True)
def service_secret(monkeypatch):
    monkeypatch.setenv("ASSIGNMENT_SERVICE_SECRET", "unit-assignment-secret")


def _decide(client, **body):
    return client.post(f"/venue-bookings/{R_ID}/decision",
                       json={"decision": "approved", **body}, cookies=COOKIE)


# --- TC-VENUEBOOKINGS-402 / 403 ----------------------------------------------
# The events service decides confirmed vs pending_safety_check (TC-EVENTS-412,
# 413); either way it answers "replanned", which is all the composite sees.
@pytest.mark.parametrize("event_status", ["confirmed", "pending_safety_check"])
def test_approving_a_replacement_replans_first_and_tells_coordinator_and_organiser(
    client, services, event_status
):
    response = _decide(client)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    [call] = services.replans()
    assert call.kwargs["headers"] == {"X-Assignment-Service-Token": "unit-assignment-secret"}
    assert call.kwargs["json"] == {
        "actor_id": STAFF, "booking_id": R_ID, "venue_name": "Hall W", "replaced_venue_name": "Hall V",
    }
    # Replanned before the approval is recorded.
    assert services.calls.index(REPLAN) < services.calls.index(DECISION)
    rows = services.replanned_notices()
    assert {(row["recipient_id"], row["message"]) for row in rows} == {
        (K, COORDINATOR_NOTICE), (G, ORGANISER_NOTICE),
    }
    assert all(row["kind"] == "venue_booking_decision" for row in rows)
    # Only the Coordinator and Organiser are ever told -- never an Attendee.
    assert {row["recipient_id"] for row in services.notices()} <= {K, G}


# --- TC-VENUEBOOKINGS-404 ----------------------------------------------------
def test_an_event_already_in_planning_gets_no_back_in_planning_notice(client, services):
    services.replanned = False

    response = _decide(client)

    assert response.status_code == 200
    assert len(services.replans()) == 1
    assert services.replanned_notices() == []
    assert len(services.notices()) == 1  # the existing decision notice only


# --- TC-VENUEBOOKINGS-405 ----------------------------------------------------
def test_approving_a_booking_that_replaces_nothing_never_replans(client, services):
    services.replacement = {**R, "replaces_booking_id": None}

    response = _decide(client)

    assert response.status_code == 200
    assert services.replans() == []
    assert services.replanned_notices() == []


# --- TC-VENUEBOOKINGS-406 ----------------------------------------------------
def test_rejecting_a_replacement_never_replans(client, services):
    services.decided = fake_response(200, {**R, "status": "rejected", "decided_at": "2026-11-04T01:00:00Z"})

    response = _decide(client, decision="rejected", reason="Hall W is being repainted")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert services.replans() == []
    assert services.replanned_notices() == []


# --- TC-VENUEBOOKINGS-407 ----------------------------------------------------
@pytest.mark.parametrize("failure", ["events down", "secret missing"])
def test_if_events_cannot_replan_nothing_is_decided(client, services, monkeypatch, failure):
    if failure == "events down":
        services.replan_status = 503
    else:
        monkeypatch.delenv("ASSIGNMENT_SERVICE_SECRET")

    response = _decide(client)

    assert response.status_code == 502
    assert response.json()["detail"] == "Events service unavailable"
    assert "private diagnostic" not in response.text
    assert DECISION not in services.calls
    services.notifications.post.assert_not_called()


# --- TC-VENUEBOOKINGS-408 ----------------------------------------------------
def test_a_refused_approval_leaves_the_event_replanned_and_tells_nobody(client, services):
    services.decided = fake_response(409, {"detail": "already decided"})

    response = _decide(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "This booking request has already been decided"
    assert len(services.replans()) == 1
    services.notifications.post.assert_not_called()


@pytest.mark.parametrize("changes,detail", [
    ({"status": "held", "hold_confirmed_at": None},
     "This hold can't be approved until the Event Coordinator confirms it."),
    ({"status": "pending", "hold_release_reason": "expired"},
     "This booking request has already been decided"),
])
def test_an_unapprovable_replacement_does_not_replan_the_event(client, services, changes, detail):
    services.replacement = {**R, **changes}

    response = _decide(client)

    assert response.status_code == 409
    assert response.json()["detail"] == detail
    assert services.replans() == []
    assert DECISION not in services.calls
    services.notifications.post.assert_not_called()
