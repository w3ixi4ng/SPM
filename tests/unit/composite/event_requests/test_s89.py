"""S-89: the assigned Coordinator cancels an event venue unavailability left
without an alternative.

TC-EVENTREQUESTS-400..418. Every downstream service is a fake built by
`World`: it answers from small in-memory state and records each call in
order, so a case states only what differs from the shared scenario. The
S-77 flag comes from venue_bookings, which owns the rule (its own suites
prove the rule); here it is the `flagged` set the fake reports.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from .conftest import COORDINATOR_A, EVENT_ID, ORGANISER_ID, app, clients_module, fake_response

URL = f"/event-requests/{EVENT_ID}/venue-cancellation"
COOKIE = {"sb_access_token": "coordinator-token"}
REASON = "Hall A is closed for structural repairs on the event date"
ALTERNATIVES = "Discussed Hall B and Seminar Room 3 with the Organiser on 30 Oct; neither fits 180 guests"
BODY = {"reason": REASON, "alternatives_considered": ALTERNATIVES, "expected_version": 7}
OTHER_OPERATION = "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f"

V1, V2, V3 = (f"{n}{n}{n}{n}{n}{n}{n}{n}-0000-4000-8000-000000000000" for n in "123")
B1 = "b1b1b1b1-b1b1-4b1b-8b1b-b1b1b1b1b1b1"
B2 = "b2b2b2b2-b2b2-4b2b-8b2b-b2b2b2b2b2b2"
H1 = "a1a1a1a1-a1a1-4a1a-8a1a-a1a1a1a1a1a1"
R1 = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
J1 = "d1d1d1d1-d1d1-4d1d-8d1d-d1d1d1d1d1d1"
A1 = "a0000000-0000-4000-8000-0000000000a1"
A2 = "a0000000-0000-4000-8000-0000000000a2"
W1 = "a0000000-0000-4000-8000-0000000000b1"

ORGANISER_MESSAGE = (
    "Event cancelled: Alumni networking evening, 20 Nov 2026, 9:00 am – 9:00 pm. "
    "Your Event Coordinator cancelled it because no alternative venue could be found. "
    f"Reason: {REASON}"
)
ATTENDEE_MESSAGE = (
    "Event cancelled: Alumni networking evening, 20 Nov 2026, 9:00 am – 9:00 pm. "
    "It will not take place."
)
NOT_AFFECTED = (
    "None of this event's venue bookings is affected by an unavailable venue, "
    "so it can't be cancelled here."
)
NOT_CANCELLED = "The event could not be cancelled. Nothing was changed. Try again."
STILL_LOCKED = "The event was not cancelled, but its venue bookings could not be unlocked. Try again."
OUTCOME_UNKNOWN = (
    "We couldn't confirm whether the event was cancelled, so its venue bookings stay "
    "locked for now. Reload the event in a few minutes: if it shows as cancelled, "
    "cancel again to finish; if not, you can try again."
)
HISTORY_NOT_RECORDED = (
    "The event is cancelled, but the cancellation was not recorded in its history. "
    "Cancel again to finish."
)
NOT_RELEASED = "The event is cancelled, but its venue bookings were not released. Cancel again to finish."
ORGANISER_NOT_NOTIFIED = (
    "The event is cancelled and its venue bookings released, but the Organiser "
    "was not notified. Cancel again to finish."
)
ATTENDEES_NOT_NOTIFIED = "The event is cancelled, but its attendees were not notified. Cancel again to notify them."
NOT_COMPLETED = "Everyone was notified, but the cancellation could not be marked complete. Cancel again to finish."


def _booking(booking_id, venue_id, status, start, end, **extra):
    return {
        "id": booking_id, "event_id": EVENT_ID, "venue_id": venue_id, "status": status,
        "booking_date": "2026-11-20", "start_time": f"{start}:00", "end_time": f"{end}:00",
        "venue_name": f"Venue {venue_id[0]}", **extra,
    }


def _event(**changes):
    event = {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "assigned_coordinator_id": COORDINATOR_A,
        "status": "confirmed", "name": "Alumni networking evening",
        "start_date": "2026-11-20", "start_time": "09:00:00",
        "end_date": "2026-11-20", "end_time": "21:00:00", "edit_version": 7,
    }
    event.update(changes)
    return event


def _cancelled(**changes):
    return _event(**{
        "status": "cancelled", "edit_version": 8, "venue_cancellation_reason": REASON,
        "venue_cancellation_alternatives": ALTERNATIVES, "venue_cancellation_booking_ids": [B1],
        "venue_cancelled_by": COORDINATOR_A, "venue_cancelled_at": "2026-11-01T03:00:00+00:00",
        "venue_cancellation_previous_status": "confirmed",
        **changes,
    })


class World:
    """The shared scenario, as the services would answer it."""

    def __init__(self, users, events, bookings, venue_bookings, registrations, notifications):
        self.calls: list[tuple] = []
        self.role = "event_coordinator"
        self.event = _event()
        self.assigned_status = 200
        self.bookings = [
            _booking(B1, V1, "confirmed", "18:00", "21:00"),
            _booking(B2, V2, "confirmed", "09:00", "12:00"),
            _booking(H1, V2, "held", "13:00", "15:00"),
            _booking(R1, V3, "pending", "18:00", "21:00", replaces_booking_id=B1),
            _booking(J1, V2, "rejected", "15:00", "17:00"),
        ]
        # What venue_bookings reports as S-77-flagged.
        self.flagged = {B1}
        self.venue_bookings_status = 200
        self.closure: dict | None = None
        self.history_recorded = False
        self.places = [A1, A2]
        self.waiting = [W1]
        self.failures: dict[str, object] = {}
        self.cancel_answer = None
        self.cancel_lands_anyway = False
        self.slip_in: list[str] = []
        self.notified: list[dict] = []

        users.get.side_effect = self._users_get
        events.get.side_effect = self._events_get
        events.post.side_effect = self._events_post
        bookings.get = AsyncMock(side_effect=self._bookings_get)
        bookings.post = AsyncMock(side_effect=self._bookings_post)
        venue_bookings.get.side_effect = self._venue_bookings_get
        registrations.get.side_effect = self._registrations_get
        notifications.post.side_effect = self._notifications_post

    def _fail(self, key):
        failure = self.failures.get(key)
        if isinstance(failure, list):
            failure = failure.pop(0) if failure else None
        if isinstance(failure, Exception):
            raise failure
        return failure

    async def _users_get(self, path, **kwargs):
        self.calls.append(("users.get", path))
        return fake_response(200, {"id": COORDINATOR_A, "name": "C", "email": "c@example.com", "role": self.role})

    async def _events_get(self, path, **kwargs):
        self.calls.append(("events.get", path))
        failure = self._fail("assigned")
        if failure is not None:
            return fake_response(failure, {"detail": "boom"})
        if self.assigned_status != 200:
            return fake_response(self.assigned_status, {"detail": "Event not found"})
        return fake_response(200, self.event)

    async def _venue_bookings_get(self, path, **kwargs):
        self.calls.append(("venue_bookings.get", path, kwargs.get("params"), kwargs.get("cookies")))
        failure = self._fail("venue_bookings")
        if failure is not None:
            return fake_response(failure, {"detail": "boom"})
        if self.venue_bookings_status != 200:
            return fake_response(self.venue_bookings_status, {"detail": "Event not found"})
        return fake_response(200, [
            {**row, "requires_alternative_arrangements": row["id"] in self.flagged}
            for row in self.bookings
        ])

    async def _events_post(self, path, **kwargs):
        self.calls.append(("events.post", path, kwargs))
        assert kwargs["headers"] == {"X-Assignment-Service-Token": "unit-assignment-secret"}
        assert kwargs["cookies"] == COOKIE
        if path.endswith("/history"):
            failure = self._fail("history")
            if failure is not None:
                return fake_response(failure, {"detail": "boom"})
            self.history_recorded = True
            return fake_response(200, {"recorded": True})
        if path.endswith("/complete"):
            failure = self._fail("complete")
            if failure is not None:
                return fake_response(failure, {"detail": "boom"})
            assert self.history_recorded, "completed before the history entry"
            self.event = {**self.event, "venue_cancellation_completed_at": "2026-11-01T03:01:00+00:00"}
            return fake_response(200, self.event)
        # The cancellation itself: the bookings must already be closed.
        if not self.event.get("venue_cancelled_at"):
            assert self.closure is not None, "the event was cancelled before its bookings were closed"
        failure = self.failures.get("cancel")
        if isinstance(failure, Exception):
            if self.cancel_lands_anyway:
                self._land(kwargs)
            raise failure
        if failure is not None:
            return fake_response(failure, {"detail": "boom"})
        if self.cancel_answer is not None:
            return fake_response(*self.cancel_answer)
        self._land(kwargs)
        return fake_response(200, self.event)

    def _land(self, kwargs):
        if not self.event.get("venue_cancelled_at"):
            self.event = _cancelled(venue_cancellation_booking_ids=kwargs["json"]["affected_booking_ids"])

    async def _bookings_get(self, path, **kwargs):
        self.calls.append(("bookings.get", path, dict(kwargs.get("params") or {})))
        failure = self._fail("bookings.get")
        if failure is not None:
            return fake_response(failure, {"detail": "boom"})
        return fake_response(200, [dict(row) for row in self.bookings])

    async def _bookings_post(self, path, **kwargs):
        body = kwargs.get("json")
        self.calls.append(("bookings.post", path, body))
        base = f"/internal/events/{EVENT_ID}/bookings"
        if path == f"{base}/closure":
            failure = self._fail("closure")
            if failure is not None:
                return fake_response(failure, {"detail": "boom"})
            if self.closure is None:
                self.closure = {"operation_id": body["operation_id"], "state": "closing"}
            return fake_response(200, {"event_id": EVENT_ID, **self.closure})
        if path == f"{base}/closure/reopen":
            failure = self._fail("reopen")
            if failure is not None:
                return fake_response(failure, {"detail": "boom"})
            mine = bool(self.closure) and self.closure["state"] == "closing" \
                and self.closure["operation_id"] == body["operation_id"]
            if mine:
                self.closure = None
            return fake_response(200, {"reopened": mine})
        assert path == f"{base}/release"
        assert body["reason"] == "event_cancelled" and body["operation_id"]
        failure = self._fail("release")
        if failure is not None:
            return fake_response(failure, {"detail": "boom"})
        self.closure = {"operation_id": body["operation_id"], "state": "closed"}
        released = []
        for row in self.bookings:
            if row["status"] in ("pending", "held", "confirmed"):
                row["status"] = "released"
                released.append(row["id"])
        if self.slip_in:
            booking_id = self.slip_in.pop(0)
            next(row for row in self.bookings if row["id"] == booking_id)["status"] = "confirmed"
        return fake_response(200, {"released": released, "count": len(released)})

    async def _registrations_get(self, path, **kwargs):
        self.calls.append(("registrations.get", path))
        failure = self._fail("registrations")
        if failure is not None:
            return fake_response(failure, {"detail": "boom"})
        ids = self.places if path == f"/registrations/events/{EVENT_ID}" else self.waiting
        return fake_response(200, [{"id": f"r-{i}", "event_id": EVENT_ID, "attendee_id": i} for i in ids])

    async def _notifications_post(self, path, **kwargs):
        rows = kwargs["json"]["notifications"]
        self.calls.append(("notifications.post", path, [row["recipient_id"] for row in rows]))
        organiser = any(row["recipient_id"] == ORGANISER_ID for row in rows)
        failure = self._fail("notify organiser" if organiser else "notify attendees")
        if failure is not None:
            return fake_response(failure, {"detail": "boom"})
        keys = {row["deduplication_key"] for row in self.notified}
        self.notified.extend(row for row in rows if row["deduplication_key"] not in keys)
        return fake_response(201, rows)

    def called(self, prefix):
        return [call for call in self.calls if call[0].startswith(prefix)]

    def paths(self, prefix):
        return [call[1] for call in self.called(prefix)]

    def writes(self):
        return [call for call in self.calls if call[0] in ("events.post", "bookings.post", "notifications.post")]

    def event_writes(self):
        return self.paths("events.post")


@pytest.fixture
def venue_bookings():
    return MagicMock(get=AsyncMock())


@pytest.fixture
def world(users, events, bookings, venue_bookings, registrations, notifications, client):
    app.dependency_overrides[clients_module.get_venue_bookings_client] = lambda: venue_bookings
    return World(users, events, bookings, venue_bookings, registrations, notifications)


def _cancel(client, body=BODY):
    return client.post(URL, json=body, cookies=COOKIE)


CANCEL_PATH = f"/internal/events/{EVENT_ID}/venue-cancellation"
CLOSURE_PATH = f"/internal/events/{EVENT_ID}/bookings/closure"
REOPEN_PATH = f"{CLOSURE_PATH}/reopen"
RELEASE_PATH = f"/internal/events/{EVENT_ID}/bookings/release"


# --- TC-EVENTREQUESTS-400 ----------------------------------------------------
def test_an_affected_multi_venue_event_is_cancelled_released_and_announced(client, world):
    response = _cancel(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["released_bookings"] == 4
    assert body["organiser_notified"] is True
    assert body["notified_attendees"] == 3
    assert body["cancellation_completed"] is True
    assert body["venue_cancellation_completed_at"]

    steps = [f"{call[0]} {call[1]}" for call in world.calls]
    expected_order = [
        "users.get /users/me",
        f"events.get /events/assigned/{EVENT_ID}",
        "venue_bookings.get /venue-bookings",
        f"bookings.post {CLOSURE_PATH}",
        f"events.post {CANCEL_PATH}",
        f"events.post {CANCEL_PATH}/history",
        f"bookings.post {RELEASE_PATH}",
        "bookings.get /bookings",
    ]
    assert steps[:len(expected_order)] == expected_order
    assert steps[-1] == f"events.post {CANCEL_PATH}/complete"
    assert next(i for i, step in enumerate(steps) if step.startswith("notifications")) > steps.index(
        f"bookings.post {RELEASE_PATH}"
    )

    sent = next(call for call in world.called("events.post") if call[1] == CANCEL_PATH)[2]["json"]
    assert sent == {**BODY, "affected_booking_ids": [B1]}
    closure_op = next(call for call in world.called("bookings.post") if call[1] == CLOSURE_PATH)[2]["operation_id"]
    release_op = next(call for call in world.called("bookings.post") if call[1] == RELEASE_PATH)[2]["operation_id"]
    assert closure_op == release_op
    assert world.closure["state"] == "closed"
    assert {row["id"]: row["status"] for row in world.bookings} == {
        B1: "released", B2: "released", H1: "released", R1: "released", J1: "rejected",
    }


# --- TC-EVENTREQUESTS-401 ----------------------------------------------------
def test_without_a_session_nothing_is_read_or_written(client, world, users):
    users.get.side_effect = None
    users.get.return_value = fake_response(401, {"detail": "Not authenticated"})

    response = _cancel(client)

    assert response.status_code == 401
    assert world.writes() == [] and world.called("venue_bookings") == []


@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "event_coordinator_lead"])
def test_other_roles_are_refused(client, world, role):
    world.role = role

    response = _cancel(client)

    assert response.status_code == 403
    assert world.writes() == [] and world.called("venue_bookings") == [] and world.called("events") == []


def test_a_coordinator_not_assigned_is_refused(client, world):
    world.assigned_status = 404

    response = _cancel(client)

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found or not assigned to you"
    assert world.writes() == [] and world.called("venue_bookings") == []


# --- TC-EVENTREQUESTS-402 ----------------------------------------------------
@pytest.mark.parametrize("case", ["nothing flagged", "no bookings"])
def test_an_event_not_affected_by_unavailability_cannot_be_cancelled_here(client, world, case):
    if case == "nothing flagged":
        world.flagged = set()
    else:
        world.bookings = []

    response = _cancel(client)

    assert response.status_code == 409
    assert response.json()["detail"] == NOT_AFFECTED
    assert world.event_writes() == []
    # Only an abandoned attempt's closure is withdrawn; nothing is closed.
    assert world.paths("bookings.post") == [REOPEN_PATH]
    assert world.closure is None


# --- TC-EVENTREQUESTS-403 ----------------------------------------------------
def test_eligibility_is_exactly_the_venue_bookings_flag(client, world):
    world.flagged = {B1, H1}

    response = _cancel(client)

    assert response.status_code == 200
    [read] = world.called("venue_bookings")
    assert read[2] == {"event_id": EVENT_ID}
    assert read[3] == COOKIE  # venue_bookings checks this Coordinator's assignment itself
    sent = next(call for call in world.called("events.post") if call[1] == CANCEL_PATH)[2]["json"]
    assert sent["affected_booking_ids"] == [B1, H1]


@pytest.mark.parametrize("answer, expected", [(404, 404), (401, 401)])
def test_venue_bookings_refusals_are_passed_on(client, world, answer, expected):
    world.venue_bookings_status = answer

    response = _cancel(client)

    assert response.status_code == expected
    assert world.writes() == []


# --- TC-EVENTREQUESTS-404 ----------------------------------------------------
@pytest.mark.parametrize(
    "answer",
    [
        (409, {"detail": "This event can't be cancelled from its current status."}),
        (409, {"detail": "The Organiser has asked to cancel this event. Approve their request instead."}),
        (409, {"detail": "This event changed since you opened it. Reload and try again."}),
        (422, {"detail": "Please check the details you entered", "errors": {"reason": "required"}}),
    ],
)
def test_a_refused_cancellation_withdraws_the_closure_and_releases_nothing(client, world, answer):
    world.cancel_answer = answer

    response = _cancel(client)

    assert (response.status_code, response.json()) == answer
    assert world.paths("bookings.post") == [CLOSURE_PATH, REOPEN_PATH]
    closure_op = world.called("bookings.post")[0][2]["operation_id"]
    assert world.called("bookings.post")[1][2] == {"operation_id": closure_op}
    assert world.closure is None
    assert world.called("notifications") == []
    assert world.event_writes() == [CANCEL_PATH]


def test_if_the_closure_cannot_be_withdrawn_that_is_said(client, world):
    world.cancel_answer = (409, {"detail": "This event changed since you opened it. Reload and try again."})
    world.failures["reopen"] = 500

    response = _cancel(client)

    assert response.status_code == 502
    assert response.json()["detail"] == STILL_LOCKED


# --- TC-EVENTREQUESTS-405 ----------------------------------------------------
@pytest.mark.parametrize(
    "key, failure, detail",
    [
        ("venue_bookings", httpx.ConnectError("down"), "Venue bookings service unavailable"),
        ("venue_bookings", 500, "Venue bookings service unavailable"),
        ("assigned", 500, "Events service unavailable"),
    ],
)
def test_a_failed_verification_read_changes_nothing(client, world, key, failure, detail):
    world.failures[key] = failure

    response = _cancel(client)

    assert response.status_code == 502
    assert response.json()["detail"] == detail
    assert world.writes() == []


# --- TC-EVENTREQUESTS-406 ----------------------------------------------------
def test_a_failed_closure_cancels_nothing(client, world):
    world.failures["closure"] = [httpx.ConnectError("down")]

    response = _cancel(client)

    assert response.status_code == 502
    assert response.json()["detail"] == NOT_CANCELLED
    assert world.event_writes() == []
    assert world.paths("bookings.post") == [CLOSURE_PATH, REOPEN_PATH]


def test_an_events_error_answer_withdraws_the_closure(client, world):
    world.failures["cancel"] = 500

    response = _cancel(client)

    assert response.status_code == 502
    assert response.json()["detail"] == NOT_CANCELLED
    assert world.closure is None
    assert world.called("notifications") == []


def test_no_answer_and_not_cancelled_keeps_the_bookings_closed(client, world):
    world.failures["cancel"] = httpx.ReadTimeout("slow")

    response = _cancel(client)

    assert response.status_code == 502
    assert response.json()["detail"] == OUTCOME_UNKNOWN
    assert world.closure["state"] == "closing"
    assert REOPEN_PATH not in world.paths("bookings.post")
    assert world.called("notifications") == []


def test_no_answer_but_cancelled_after_all_carries_on(client, world):
    world.failures["cancel"] = httpx.ReadTimeout("slow")
    world.cancel_lands_anyway = True

    response = _cancel(client)

    assert response.status_code == 200, response.text
    assert response.json()["cancellation_completed"] is True
    assert REOPEN_PATH not in world.paths("bookings.post")


def test_no_answer_and_no_reread_keeps_the_bookings_closed(client, world):
    world.failures["cancel"] = httpx.ReadTimeout("slow")
    world.failures["assigned"] = [None, 500]

    response = _cancel(client)

    assert response.status_code == 502
    assert response.json()["detail"] == OUTCOME_UNKNOWN
    assert world.closure["state"] == "closing"


# --- TC-EVENTREQUESTS-407 ----------------------------------------------------
def test_a_failed_release_is_reported_and_cancelling_again_finishes_it(client, world):
    world.failures["release"] = [500]

    first = _cancel(client)

    assert first.status_code == 502
    assert first.json()["detail"] == NOT_RELEASED
    assert world.called("notifications") == []
    assert f"{CANCEL_PATH}/complete" not in world.event_writes()
    assert world.closure["state"] == "closing"  # still closed to new active bookings

    world.calls.clear()
    world.flagged = set()  # A resumed cancellation must not depend on the flag.
    second = _cancel(client, {**BODY, "reason": "Typed again differently"})

    assert second.status_code == 200, second.text
    assert second.json()["released_bookings"] == 4
    assert second.json()["cancellation_completed"] is True
    assert world.called("venue_bookings") == []
    assert CLOSURE_PATH not in world.paths("bookings.post")
    assert CANCEL_PATH not in world.event_writes()
    assert [row["recipient_id"] for row in world.notified].count(ORGANISER_ID) == 1


# --- TC-EVENTREQUESTS-408 ----------------------------------------------------
def test_a_booking_that_slips_in_during_the_release_is_caught(client, world):
    world.slip_in = [R1]

    response = _cancel(client)

    assert response.status_code == 200
    assert response.json()["released_bookings"] == 4
    assert world.paths("bookings.post").count(RELEASE_PATH) == 2


def test_a_booking_that_stays_active_is_a_failure(client, world):
    world.slip_in = [R1, R1]

    response = _cancel(client)

    assert response.status_code == 502
    assert response.json()["detail"] == NOT_RELEASED
    assert world.called("notifications") == []
    assert f"{CANCEL_PATH}/complete" not in world.event_writes()


# --- TC-EVENTREQUESTS-409 ----------------------------------------------------
def test_the_organiser_is_told_why_with_the_recorded_reason(client, world):
    _cancel(client)

    organiser_rows = [row for row in world.notified if row["recipient_id"] == ORGANISER_ID]
    assert organiser_rows == [{
        "recipient_id": ORGANISER_ID,
        "event_id": EVENT_ID,
        "event_name": "Alumni networking evening",
        "kind": "event_cancelled",
        "message": ORGANISER_MESSAGE,
        "deduplication_key": f"event_cancelled:{EVENT_ID}:{ORGANISER_ID}",
    }]


# --- TC-EVENTREQUESTS-410 ----------------------------------------------------
def test_attendees_get_the_s69_notification_unchanged(client, world):
    world.waiting = [W1, A1]  # A1 holds a place too: still one notification.

    response = _cancel(client)

    assert response.json()["notified_attendees"] == 3
    attendee_rows = [row for row in world.notified if row["recipient_id"] != ORGANISER_ID]
    assert {row["recipient_id"] for row in attendee_rows} == {A1, A2, W1}
    for row in attendee_rows:
        assert row["message"] == ATTENDEE_MESSAGE
        assert row["kind"] == "event_cancelled"
        assert row["deduplication_key"] == f"event_cancelled:{EVENT_ID}:{row['recipient_id']}"
    assert world.called("notifications.post")[0][2] == [ORGANISER_ID]


def test_large_events_are_notified_in_batches_of_20(client, world):
    world.places = [f"a0000000-0000-4000-8000-{index:012d}" for index in range(23)]
    world.waiting = [f"b0000000-0000-4000-8000-{index:012d}" for index in range(2)]

    response = _cancel(client)

    assert response.json()["notified_attendees"] == 25
    assert [len(call[2]) for call in world.called("notifications.post")][1:] == [20, 5]


# --- TC-EVENTREQUESTS-411 ----------------------------------------------------
@pytest.mark.parametrize(
    "key, failure, detail",
    [
        ("notify organiser", 500, ORGANISER_NOT_NOTIFIED),
        ("registrations", httpx.ConnectError("down"), ATTENDEES_NOT_NOTIFIED),
        ("notify attendees", [None, 500], ATTENDEES_NOT_NOTIFIED),
    ],
)
def test_a_failed_notification_is_never_reported_as_finished(client, world, key, failure, detail):
    if key == "notify attendees":
        world.places = [f"a0000000-0000-4000-8000-{index:012d}" for index in range(23)]
    world.failures[key] = failure

    first = _cancel(client)

    assert first.status_code == 502
    assert first.json()["detail"] == detail
    assert f"{CANCEL_PATH}/complete" not in world.event_writes()

    world.failures.clear()
    second = _cancel(client)

    assert second.status_code == 200
    assert second.json()["cancellation_completed"] is True
    keys = [row["deduplication_key"] for row in world.notified]
    assert len(keys) == len(set(keys))


# --- TC-EVENTREQUESTS-412 ----------------------------------------------------
def test_the_completion_marker_is_the_last_step(client, world):
    world.failures["complete"] = [500]

    first = _cancel(client)
    second = _cancel(client)

    assert first.status_code == 502
    assert first.json()["detail"] == NOT_COMPLETED
    assert second.status_code == 200
    assert second.json()["cancellation_completed"] is True


# --- TC-EVENTREQUESTS-413 ----------------------------------------------------
def test_an_event_cancelled_another_way_is_not_cancelled_again(client, world):
    world.event = _event(
        status="cancelled", cancellation_decision="approved",
        cancellation_requested_at="2026-10-30T00:00:00Z",
    )

    response = _cancel(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "This event is already cancelled."
    assert world.writes() == []


# --- TC-EVENTREQUESTS-414 ----------------------------------------------------
@pytest.mark.parametrize(
    "changes, field",
    [
        ({"reason": "  "}, "reason"),
        ({"alternatives_considered": None}, "alternatives_considered"),
        ({"expected_version": "x"}, "expected_version"),
    ],
)
def test_validation_happens_before_any_downstream_call(client, world, changes, field):
    body = {key: value for key, value in {**BODY, **changes}.items() if value is not None}

    response = _cancel(client, body)

    assert response.status_code == 422
    assert response.json()["detail"] == "Please check the details you entered"
    assert field in response.json()["errors"]
    assert world.calls == []


# --- TC-EVENTREQUESTS-416 ----------------------------------------------------
def test_a_missing_history_entry_stops_the_operation_and_is_retried(client, world):
    world.failures["history"] = [500]

    first = _cancel(client)

    assert first.status_code == 502
    assert first.json()["detail"] == HISTORY_NOT_RECORDED
    assert RELEASE_PATH not in world.paths("bookings.post")
    assert world.called("notifications") == []
    assert f"{CANCEL_PATH}/complete" not in world.event_writes()

    second = _cancel(client)

    assert second.status_code == 200
    assert world.event_writes().count(f"{CANCEL_PATH}/history") == 2
    assert world.history_recorded


# --- TC-EVENTREQUESTS-417 ----------------------------------------------------
def test_a_losing_concurrent_attempt_never_unlocks_the_winners_closure(client, world):
    # Another attempt (another tab) closed the bookings first and is cancelling.
    world.closure = {"operation_id": OTHER_OPERATION, "state": "closing"}
    world.cancel_answer = (409, {"detail": "This event changed since you opened it. Reload and try again."})

    response = _cancel(client)

    assert response.status_code == 409
    assert world.closure == {"operation_id": OTHER_OPERATION, "state": "closing"}
    reopen = next(call for call in world.called("bookings.post") if call[1] == REOPEN_PATH)
    assert reopen[2]["operation_id"] != OTHER_OPERATION


# --- TC-EVENTREQUESTS-418 ----------------------------------------------------
def test_the_bookings_are_closed_before_the_event_is_cancelled(client, world):
    # The events fake refuses to cancel while no closure exists, so every
    # successful case above also proves the order.
    response = _cancel(client)

    assert response.status_code == 200
    steps = [call[1] for call in world.writes()]
    assert steps.index(CLOSURE_PATH) < steps.index(CANCEL_PATH)


def test_the_events_write_carries_the_callers_own_session(client, world):
    _cancel(client)

    cancel = next(call for call in world.called("events.post") if call[1] == CANCEL_PATH)
    assert cancel[2]["cookies"] == COOKIE
