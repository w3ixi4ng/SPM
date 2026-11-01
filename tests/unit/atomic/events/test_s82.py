"""S-82: the events service records each significant action and serves the
event's change history. TC-EVENTS-188 to -202 and -206.

Each table gets its own small fake, so a test reads exactly what was written
to `event_history` without picking it out of the event table's calls.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import authenticate, event_row, fake_user

E = "11111111-1111-4111-8111-111111111111"
O = "22222222-2222-4222-8222-222222222222"
C = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
C2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
L = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
S = "55555555-5555-4555-8555-555555555555"
T = "66666666-6666-4666-8666-666666666666"
MISSING = "99999999-9999-4999-8999-999999999999"

SUBMITTED = {
    "name": "Autumn Forum",
    "purpose": "Bring the faculty together",
    "start_date": "2026-11-18",
    "start_time": "09:00",
    "end_date": "2026-11-18",
    "end_time": "12:00",
    "expected_attendance": 120,
    "venue": "Main auditorium",
}


class Table:
    """A Supabase table: every filter returns itself, and `execute` answers
    with the next response queued for the operation (the last one repeats)."""

    def __init__(self, **responses):
        self.responses = {verb: list(rows) for verb, rows in responses.items()}
        self.calls = []
        self.verb = None
        self.error = None

    def _start(self, verb, payload=None):
        self.verb = verb
        self.calls.append((verb, payload))
        return self

    def select(self, *args, **kwargs):
        if self.verb is None:
            self._start("select")
        return self

    def insert(self, payload):
        return self._start("insert", payload)

    def update(self, payload):
        return self._start("update", payload)

    def delete(self):
        return self._start("delete")

    @property
    def not_(self):
        return self

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def chained(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self

        return chained

    def execute(self):
        verb, self.verb = self.verb, None
        if self.error is not None:
            raise self.error
        queue = self.responses.get(verb) or [[]]
        rows = queue.pop(0) if len(queue) > 1 else queue[0]
        return SimpleNamespace(data=rows)

    def written(self, verb):
        return [call[1] for call in self.calls if call[0] == verb]


@pytest.fixture
def tables():
    return {
        "events": Table(),
        "event_history": Table(insert=[[{"id": 1}]]),
        "reassignment_requests": Table(),
        "change_requests": Table(select=[[]]),
    }


@pytest.fixture
def db(tables):
    db = MagicMock()
    db.schema.return_value.table.side_effect = lambda name: tables[name]
    return db


def events(tables, **responses):
    tables["events"].responses = {verb: list(rows) for verb, rows in responses.items()}


def recorded(tables):
    return tables["event_history"].written("insert")


def entry(actor_id, actor_role, category, action, details):
    return {
        "event_id": E,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "category": category,
        "action": action,
        "details": details,
    }


def row(**changes):
    return event_row(id=E, organiser_id=O, **changes)


def assigned(**changes):
    values = {
        **SUBMITTED, "status": "planning", "assigned_coordinator_id": C,
        "assigning_lead_id": L, "coordinator_assignment_version": 2,
        "submitted_at": "2026-10-01T01:00:00Z",
    }
    values.update(changes)
    return row(**values)


def as_role(client, auth, user_id, role):
    authenticate(client, auth, fake_user(user_id, role))


# --- TC-EVENTS-188 ----------------------------------------------------------
def test_a_submission_is_recorded(client, auth, tables):
    submitted = row(**SUBMITTED, status="submitted", submitted_at="2026-10-01T01:00:00Z")
    events(tables, insert=[[submitted]])
    response = client.post("/events/internal", json={**SUBMITTED, "organiser_id": O})
    assert response.status_code == 201

    as_role(client, auth, O, "event_organiser")
    assert client.post("/events", json=SUBMITTED).status_code == 201

    events(tables, select=[[row(status="draft")]], update=[[submitted]])
    response = client.post(f"/events/{E}/submit/internal", json={**SUBMITTED, "organiser_id": O})
    assert response.status_code == 200

    events(tables, select=[[row(**SUBMITTED, status="returned")]], update=[[submitted]])
    response = client.post(f"/events/{E}/submit/internal", json={**SUBMITTED, "organiser_id": O})
    assert response.status_code == 200

    submission = entry(O, "event_organiser", "submission", "submitted", {})
    assert recorded(tables) == [
        submission,
        submission,
        submission,
        {**submission, "details": {"resubmission": True}},
    ]
    assert all("occurred_at" not in written for written in recorded(tables))


# --- TC-EVENTS-189 ----------------------------------------------------------
@pytest.mark.parametrize(
    ("body", "action", "details"),
    [
        ({"decision": "approved"}, "request_approved", {"reason": None, "comment": None}),
        ({"decision": "rejected", "reason": "Clashes with exams"}, "request_rejected",
         {"reason": "Clashes with exams", "comment": None}),
        ({"decision": "returned", "reason": "Add a contact", "comment": "A phone number is enough"},
         "request_returned", {"reason": "Add a contact", "comment": "A phone number is enough"}),
    ],
)
def test_a_review_decision_is_recorded(client, auth, tables, body, action, details):
    as_role(client, auth, C, "event_coordinator")
    events(tables, select=[[assigned(status="submitted")]], update=[[assigned(decision=body["decision"])]])

    assert client.post(f"/events/{E}/decision", json=body).status_code == 200
    assert recorded(tables) == [entry(C, "event_coordinator", "review", action, details)]


# --- TC-EVENTS-190 ----------------------------------------------------------
def test_cancellation_request_and_decision_are_recorded(client, auth, tables):
    as_role(client, auth, O, "event_organiser")
    events(tables, select=[[assigned()]], update=[[assigned()]])
    response = client.post(f"/events/{E}/cancellation-request", json={"reason": "Speaker withdrew"})
    assert response.status_code == 200

    requested = assigned(cancellation_requested_at="2026-10-02T01:00:00Z", cancellation_requested_by=O)
    as_role(client, auth, C, "event_coordinator")
    events(tables, select=[[requested]], update=[[requested]])
    body = {"decision": "declined", "reason": "Replacement speaker found"}
    assert client.post(f"/events/{E}/cancellation-decision", json=body).status_code == 200
    assert client.post(f"/events/{E}/cancellation-decision", json={"decision": "approved"}).status_code == 200

    assert recorded(tables) == [
        entry(O, "event_organiser", "review", "cancellation_requested", {"reason": "Speaker withdrew"}),
        entry(C, "event_coordinator", "review", "cancellation_declined",
              {"reason": "Replacement speaker found"}),
        entry(C, "event_coordinator", "review", "cancellation_approved", {"reason": None}),
    ]


# --- TC-EVENTS-191 ----------------------------------------------------------
def test_an_assignment_is_recorded_once(client, auth, tables):
    as_role(client, auth, L, "event_coordinator_lead")
    taken = assigned(status="submitted")
    events(tables, update=[[taken], []], select=[[taken]])

    first = client.post(f"/internal/events/{E}/assignment", json={"coordinator_id": C})
    repeat = client.post(f"/internal/events/{E}/assignment", json={"coordinator_id": C})

    assert first.json()["assignment_created"] is True
    assert repeat.json()["assignment_created"] is False
    assert recorded(tables) == [
        entry(L, "event_coordinator_lead", "assignment", "coordinator_assigned", {"coordinator_id": C}),
    ]


# --- TC-EVENTS-192 ----------------------------------------------------------
def test_reassignment_request_and_reassignment_are_recorded_once(client, auth, tables):
    as_role(client, auth, C, "event_coordinator")
    events(tables, select=[[assigned()]])
    tables["reassignment_requests"].responses = {"insert": [[{
        "id": "77777777-7777-4777-8777-777777777777", "event_id": E, "event_name": "Autumn Forum",
        "requester_id": C, "assigning_lead_id": L, "assignment_version": 2,
        "reason": "Leaving the team", "status": "pending",
        "created_at": "2026-10-05T01:00:00Z", "actioned_at": None,
    }]]}
    response = client.post(f"/events/{E}/reassignment-request", json={"reason": "Leaving the team"})
    assert response.status_code == 201

    as_role(client, auth, L, "event_coordinator_lead")
    moved = assigned(assigned_coordinator_id=C2, previous_coordinator_id=C, coordinator_assignment_version=3)
    body = {"coordinator_id": C2, "expected_coordinator_id": C, "expected_assignment_version": 2}
    events(tables, select=[[assigned()]], update=[[moved]])
    assert client.post(f"/internal/events/{E}/reassignment", json=body).json()["reassignment_created"] is True
    events(tables, select=[[moved]])
    assert client.post(f"/internal/events/{E}/reassignment", json=body).json()["reassignment_created"] is False

    assert recorded(tables) == [
        entry(C, "event_coordinator", "assignment", "reassignment_requested", {"reason": "Leaving the team"}),
        entry(L, "event_coordinator_lead", "assignment", "coordinator_reassigned",
              {"from_coordinator_id": C, "to_coordinator_id": C2}),
    ]


# --- TC-EVENTS-193 ----------------------------------------------------------
def test_a_technical_support_assignment_is_recorded(client, tables):
    events(tables, select=[[assigned()]], update=[[assigned(assigned_technical_support_id=T)]])
    body = {"coordinator_id": C, "assigned_technical_support_id": T}

    assert client.put(f"/events/{E}/technical-support/internal", json=body).status_code == 200
    assert recorded(tables) == [
        entry(C, "event_coordinator", "assignment", "technical_support_assigned",
              {"technical_support_id": T, "previous_technical_support_id": None}),
    ]


# --- TC-EVENTS-194 ----------------------------------------------------------
def test_an_edit_is_recorded_with_each_changed_field(client, auth, tables):
    as_role(client, auth, C, "event_coordinator")
    before = assigned(edit_version=3, internal_notes=None, room_layout="theatre")
    events(tables, select=[[before]], update=[[{**before, "edit_version": 4}]])
    body = {
        "expected_version": 3, "impact_accepted": True, "expected_attendance": 150,
        "internal_notes": "Check lift access", "room_layout": "theatre",
    }

    assert client.patch(f"/events/assigned/{E}", json=body).status_code == 200
    assert recorded(tables) == [
        entry(C, "event_coordinator", "edit", "edited", {
            "changes": {
                "expected_attendance": {"before": 120, "after": 150},
                "internal_notes": {"before": None, "after": "Check lift access"},
            },
            "significant": True,
        }),
    ]
    assert len(tables["events"].written("update")[0]["edit_history"]) == 1


# --- TC-EVENTS-195 ----------------------------------------------------------
def test_safety_submissions_and_decisions_are_recorded(client, tables):
    events(tables, select=[[assigned()]], update=[[assigned(status="pending_safety_check")]])
    response = client.post(f"/internal/events/{E}/safety-submission", json={"coordinator_id": C})
    assert response.status_code == 200

    events(tables, select=[[assigned(status="pending_safety_check")]], update=[[assigned()]])
    for decision, reason in (
        ("approved", None), ("changes_requested", "Fire exit blocked"), ("rejected", "Capacity over limit"),
    ):
        body = {"decision": decision, "reason": reason, "safety_officer_id": S,
                "expected_event_updated_at": "2026-09-14T00:00:00Z"}
        assert client.post(f"/internal/events/safety-review/{E}/decision", json=body).status_code == 200

    events(tables, select=[[assigned(safety_decision="changes_requested")]], update=[[assigned()]])
    response = client.post(f"/internal/events/{E}/safety-resubmit", json={"coordinator_id": C})
    assert response.status_code == 200

    assert recorded(tables) == [
        entry(C, "event_coordinator", "safety", "safety_submitted", {}),
        entry(S, "safety_officer", "safety", "safety_approved", {"reason": None}),
        entry(S, "safety_officer", "safety", "safety_changes_requested", {"reason": "Fire exit blocked"}),
        entry(S, "safety_officer", "safety", "safety_rejected", {"reason": "Capacity over limit"}),
        entry(C, "event_coordinator", "safety", "safety_resubmitted", {}),
    ]


# --- TC-EVENTS-196 ----------------------------------------------------------
def test_signoff_and_preparation_are_recorded(client, auth, tables):
    supported = assigned(assigned_technical_support_id=T, equipment_preparation_status="not_started")
    events(tables, select=[[supported]], update=[[supported]])
    declined = {"technical_support_id": T, "decision": "declined", "reason": "Projector unavailable"}
    assert client.put(f"/internal/events/{E}/technical-signoff", json=declined).status_code == 200
    approved = {"technical_support_id": T, "decision": "approved"}
    assert client.put(f"/internal/events/{E}/technical-signoff", json=approved).status_code == 200

    as_role(client, auth, T, "technical_support")
    path = f"/events/support-assigned/{E}/equipment-preparation"
    assert client.put(path, json={"status": "in_progress"}).status_code == 200

    assert recorded(tables) == [
        entry(T, "technical_support", "equipment", "technical_signoff_declined",
              {"reason": "Projector unavailable"}),
        entry(T, "technical_support", "equipment", "technical_signoff_approved", {"reason": None}),
        entry(T, "technical_support", "equipment", "equipment_preparation_changed",
              {"from": "not_started", "to": "in_progress"}),
    ]


# --- TC-EVENTS-197 ----------------------------------------------------------
def test_a_refused_action_records_nothing(client, auth, tables):
    as_role(client, auth, C, "event_coordinator")
    events(tables, select=[[assigned(decision="approved")]])
    assert client.post(f"/events/{E}/decision", json={"decision": "approved"}).status_code == 409

    as_role(client, auth, C2, "event_coordinator")
    events(tables, select=[[]])
    assert client.post(f"/events/{E}/decision", json={"decision": "approved"}).status_code == 404

    as_role(client, auth, C, "event_coordinator")
    events(tables, select=[[assigned(edit_version=3)]])
    stale = {"expected_version": 2, "expected_attendance": 150, "impact_accepted": True}
    assert client.patch(f"/events/assigned/{E}", json=stale).status_code == 409
    unchanged = {"expected_version": 3, "expected_attendance": 120}
    assert client.patch(f"/events/assigned/{E}", json=unchanged).status_code == 200

    as_role(client, auth, L, "event_coordinator_lead")
    events(tables, update=[[]], select=[[assigned(status="submitted", assigned_coordinator_id=C2)]])
    assert client.post(f"/internal/events/{E}/assignment", json={"coordinator_id": C}).status_code == 409

    assert recorded(tables) == []


# --- TC-EVENTS-198 ----------------------------------------------------------
def test_a_failed_history_write_does_not_undo_the_action(client, auth, tables, caplog):
    as_role(client, auth, C, "event_coordinator")
    events(tables, select=[[assigned(status="submitted")]], update=[[assigned(decision="approved")]])
    tables["event_history"].error = RuntimeError("history unavailable")

    with caplog.at_level(logging.ERROR):
        response = client.post(f"/events/{E}/decision", json={"decision": "approved"})

    assert response.status_code == 200
    assert response.json()["decision"] == "approved"
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert E in errors[0] and "request_approved" in errors[0]


# --- TC-EVENTS-199 ----------------------------------------------------------
VENUE_ENTRY = {
    "actor_id": C,
    "actor_role": "event_coordinator",
    "action": "venue_requested",
    "details": {"booking_id": MISSING, "venue_name": "Hall One"},
}


def test_composites_append_through_the_internal_route(client, tables):
    stored = {**VENUE_ENTRY, "id": 7, "event_id": E, "category": "venue",
              "occurred_at": "2026-10-27T06:05:00Z"}
    events(tables, select=[[{"id": E}]])
    tables["event_history"].responses = {"insert": [[stored]]}

    response = client.post(f"/internal/events/{E}/history", json=VENUE_ENTRY)
    assert response.status_code == 201
    assert response.json() == {**stored, "occurred_at": "2026-10-27T06:05:00Z"}
    assert recorded(tables) == [{**VENUE_ENTRY, "event_id": E, "category": "venue"}]

    for refused in (
        {**VENUE_ENTRY, "action": "made_up"},
        {**VENUE_ENTRY, "action": "request_approved"},
        {**VENUE_ENTRY, "occurred_at": "2020-01-01T00:00:00Z"},
        {**VENUE_ENTRY, "category": "safety"},
    ):
        assert client.post(f"/internal/events/{E}/history", json=refused).status_code == 422

    events(tables, select=[[]])
    response = client.post(f"/internal/events/{MISSING}/history", json=VENUE_ENTRY)
    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    assert len(recorded(tables)) == 1


# --- TC-EVENTS-200 ----------------------------------------------------------
def history_row(entry_id, action, category, occurred_at, details=None, event_id=E):
    return {
        "id": entry_id, "event_id": event_id, "actor_id": C, "actor_role": "event_coordinator",
        "category": category, "action": action, "details": details or {}, "occurred_at": occurred_at,
    }


def test_the_full_history_reads_newest_first(client, tables):
    rows = [
        history_row(3, "edited", "edit", "2026-10-03T01:00:00Z"),
        history_row(2, "coordinator_assigned", "assignment", "2026-10-02T01:00:00Z"),
        history_row(1, "submitted", "submission", "2026-10-01T01:00:00Z"),
    ]
    events(tables, select=[[{"id": E}]])
    tables["event_history"].responses = {"select": [rows]}

    response = client.get(f"/internal/events/{E}/history")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [3, 2, 1]
    assert set(response.json()[0]) == {
        "id", "event_id", "actor_id", "actor_role", "category", "action", "details", "occurred_at",
    }
    calls = tables["event_history"].calls
    assert ("eq", ("event_id", E), {}) in calls
    assert ("order", ("occurred_at",), {"desc": True}) in calls

    events(tables, select=[[]])
    response = client.get(f"/internal/events/{MISSING}/history")
    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"


# --- TC-EVENTS-201 ----------------------------------------------------------
def test_the_safety_view_keeps_only_what_the_review_needs(client, tables):
    rows = [
        history_row(8, "request_approved", "review", "2026-10-08T01:00:00Z"),
        history_row(7, "safety_changes_requested", "safety", "2026-10-07T01:00:00Z",
                    {"reason": "Fire exit blocked"}),
        history_row(6, "equipment_requirement_set", "equipment", "2026-10-06T01:00:00Z"),
        history_row(5, "venue_confirmed", "venue", "2026-10-05T01:00:00Z"),
        history_row(4, "edited", "edit", "2026-10-04T01:00:00Z",
                    {"changes": {"contact_phone": {"before": None, "after": "91234567"}}}),
        history_row(3, "edited", "edit", "2026-10-03T01:00:00Z", {
            "changes": {
                "expected_attendance": {"before": 120, "after": 150},
                "internal_notes": {"before": None, "after": "Call Ada"},
            },
            "significant": True,
        }),
        history_row(2, "coordinator_assigned", "assignment", "2026-10-02T01:00:00Z"),
        history_row(1, "submitted", "submission", "2026-10-01T01:00:00Z"),
    ]
    events(tables, select=[[{"id": E}]])
    tables["event_history"].responses = {"select": [rows]}

    response = client.get(f"/internal/events/{E}/history", params={"scope": "safety"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [7, 6, 5, 3]
    assert response.json()[3]["details"] == {
        "changes": {"expected_attendance": {"before": 120, "after": 150}},
        "significant": True,
    }
    assert client.get(f"/internal/events/{E}/history", params={"scope": "other"}).status_code == 422


# --- TC-EVENTS-202 ----------------------------------------------------------
def test_no_route_changes_or_removes_an_entry(client, tables):
    events(tables, select=[[{"id": E}]])
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(f"/internal/events/{E}/history").status_code == 405
        assert getattr(client, method)(f"/internal/events/{E}/history/7").status_code in (404, 405)

    verbs = {call[0] for call in tables["event_history"].calls}
    assert not verbs & {"update", "delete"}


# --- TC-EVENTS-206 ----------------------------------------------------------
def test_an_organisers_edit_after_submission_is_recorded(client, auth, tables):
    as_role(client, auth, O, "event_organiser")
    submitted = row(**SUBMITTED, status="submitted", submitted_at="2026-10-01T01:00:00Z")
    events(tables, select=[[submitted]], update=[[{**submitted, "expected_attendance": 150}]])
    assert client.patch(f"/events/{E}", json={"expected_attendance": 150}).status_code == 200

    events(tables, select=[[row(status="draft")]], update=[[row(status="draft", name="Draft")]])
    assert client.patch(f"/events/{E}", json={"name": "Draft"}).status_code == 200

    assert recorded(tables) == [
        entry(O, "event_organiser", "edit", "edited", {
            "changes": {"expected_attendance": {"before": 120, "after": 150}},
            "significant": True,
        }),
    ]


# --- TC-EVENTS-207 ----------------------------------------------------------
def test_the_history_scope_says_who_may_read_it(client, tables):
    reviewed = {
        "id": E, "name": "Autumn Forum", "status": "planning", "assigned_coordinator_id": C,
        "safety_review_history": [{"review_number": 1}], "organiser_id": O, "internal_notes": "x",
    }
    events(tables, select=[[reviewed]])

    response = client.get(f"/internal/events/{E}/history-scope")

    assert response.status_code == 200
    assert response.json() == {
        "id": E, "name": "Autumn Forum", "status": "planning",
        "assigned_coordinator_id": C, "safety_reviewed": True,
    }
    events(tables, select=[[{**reviewed, "safety_review_history": []}]])
    assert client.get(f"/internal/events/{E}/history-scope").json()["safety_reviewed"] is False
    events(tables, select=[[]])
    assert client.get(f"/internal/events/{MISSING}/history-scope").status_code == 404
