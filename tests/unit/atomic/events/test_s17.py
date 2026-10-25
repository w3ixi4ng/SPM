"""S-17: submission for the Operational Safety Check and Technical Support sign-off."""

from types import SimpleNamespace

import pytest

from .conftest import (
    COORDINATOR_A,
    COORDINATOR_B,
    EVENT_ID,
    ORGANISER_ID,
    EventRead,
    authenticate,
    event_row,
    fake_user,
    on_owned_select,
)

SUPPORT_A = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
SUPPORT_B = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
OFFICER_ID = "50000000-0000-4000-8000-000000000001"


def planning_event(**changes):
    values = dict(
        status="planning",
        name="Safety Forum",
        purpose="Operational safety review",
        start_date="2026-11-20",
        start_time="09:00:00",
        end_date="2026-11-20",
        end_time="17:00:00",
        expected_attendance=120,
        submitted_at="2026-10-09T00:00:00Z",
        decision="approved",
        decided_at="2026-10-10T00:00:00Z",
        assigned_coordinator_id=COORDINATOR_A,
        technical_support_required=True,
        assigned_technical_support_id=SUPPORT_A,
        technical_support_assigned_at="2026-10-10T01:00:00Z",
    )
    values.update(changes)
    return event_row(**values)


def table(db):
    return db.schema.return_value.table.return_value


def assigned_select(db, rows):
    # _get_assigned_event: .select().eq(id).eq(assigned_coordinator_id)
    operation = table(db).select.return_value.eq.return_value.eq.return_value
    operation.execute.return_value = SimpleNamespace(data=rows)


def support_select(db, rows):
    # _get_support_assigned_event: .select().eq(id).eq(support).in_(status)
    operation = table(db).select.return_value.eq.return_value.eq.return_value.in_.return_value
    operation.execute.return_value = SimpleNamespace(data=rows)


def submission_update(db, rows):
    # .update().eq(id).eq(status).eq(coordinator).is_(safety_decision)
    operation = (
        table(db).update.return_value.eq.return_value.eq.return_value.eq.return_value.is_.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def signoff_update(db, rows):
    # .update().eq(id).eq(support).eq(status)
    operation = table(db).update.return_value.eq.return_value.eq.return_value.eq.return_value
    operation.execute.return_value = SimpleNamespace(data=rows)
    return operation


def submit(client, coordinator=COORDINATOR_A):
    return client.post(
        f"/internal/events/{EVENT_ID}/safety-submission",
        json={"coordinator_id": coordinator},
    )


def sign_off(client, **body):
    return client.put(
        f"/internal/events/{EVENT_ID}/technical-signoff",
        json={"technical_support_id": SUPPORT_A, **body},
    )


# --- TC-EVENTS-135 --------------------------------------------------------
def test_pending_safety_check_is_a_valid_status():
    event = EventRead(**planning_event(status="pending_safety_check"))
    assert event.status.value == "pending_safety_check"


# --- TC-EVENTS-136 --------------------------------------------------------
def test_planning_event_moves_to_pending_safety_check(client, db):
    assigned_select(db, [planning_event()])
    submission_update(db, [planning_event(status="pending_safety_check")])

    response = submit(client)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending_safety_check"
    update = table(db).update
    update.assert_called_once_with({
        "status": "pending_safety_check",
        "safety_recheck_required": False,
    })
    first = update.return_value.eq
    first.assert_called_once_with("id", EVENT_ID)
    first.return_value.eq.assert_called_once_with("status", "planning")
    first.return_value.eq.return_value.eq.assert_called_once_with(
        "assigned_coordinator_id", COORDINATOR_A
    )
    first.return_value.eq.return_value.eq.return_value.is_.assert_called_once_with(
        "safety_decision", "null"
    )


# --- TC-EVENTS-137 --------------------------------------------------------
@pytest.mark.parametrize(
    "event_status",
    ["submitted", "pending_safety_check", "confirmed", "safety_rejected", "rejected"],
)
def test_only_planning_events_can_be_submitted(client, db, event_status):
    assigned_select(db, [planning_event(status=event_status)])

    response = submit(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "This event is not in planning"
    table(db).update.assert_not_called()


def test_only_assigned_planning_event_can_be_submitted(client, db):
    assigned_select(db, [])
    assert submit(client, COORDINATOR_B).status_code == 404
    table(db).update.assert_not_called()

    assigned_select(db, [planning_event()])
    operation = submission_update(db, [])
    response = submit(client)
    assert response.status_code == 409
    assert operation.execute.call_count == 1


def test_safety_returned_event_is_resubmitted_not_submitted(client, db):
    assigned_select(db, [planning_event(safety_decision="changes_requested")])

    response = submit(client)

    assert response.status_code == 409
    assert "Resubmit" in response.json()["detail"]
    table(db).update.assert_not_called()


# --- TC-EVENTS-138 and -139 are in test_s86.py, updated for S-17 -----------
# --- TC-EVENTS-140 is test_s87.py's resubmit test, updated for S-17 --------


# --- TC-EVENTS-141 --------------------------------------------------------
def test_assigned_support_records_signoff(client, db):
    support_select(db, [planning_event()])
    operation = signoff_update(db, [planning_event(technical_signoff_decision="approved")])

    assert sign_off(client, decision="approved").status_code == 200
    values = table(db).update.call_args.args[0]
    assert values["technical_signoff_decision"] == "approved"
    assert values["technical_signoff_by"] == SUPPORT_A
    assert values["technical_signoff_at"]
    assert values["technical_signoff_reason"] is None
    assert values["technical_signoff_override_comment"] is None
    first = table(db).update.return_value.eq
    first.return_value.eq.assert_called_with("assigned_technical_support_id", SUPPORT_A)
    first.return_value.eq.return_value.eq.assert_called_with("status", "planning")

    sign_off(
        client,
        decision="approved",
        override_comment="  Borrowing 2 projectors from Library ",
    )
    values = table(db).update.call_args.args[0]
    assert values["technical_signoff_override_comment"] == "Borrowing 2 projectors from Library"

    sign_off(client, decision="declined", reason="Only one sound desk exists")
    values = table(db).update.call_args.args[0]
    assert values["technical_signoff_decision"] == "declined"
    assert values["technical_signoff_reason"] == "Only one sound desk exists"
    assert values["technical_signoff_override_comment"] is None
    assert operation.execute.call_count == 3


def test_coordinator_reads_the_signoff(client, db, auth):
    signed = planning_event(
        technical_signoff_decision="declined",
        technical_signoff_reason="Only one sound desk exists",
        technical_signoff_by=SUPPORT_A,
        technical_signoff_at="2026-10-19T09:00:00Z",
    )
    assigned_select(db, [signed])
    authenticate(client, auth, fake_user(user_id=COORDINATOR_A, role="event_coordinator"))

    response = client.get(f"/events/assigned/{EVENT_ID}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["technical_signoff_decision"] == "declined"
    assert body["technical_signoff_reason"] == "Only one sound desk exists"
    assert body["technical_signoff_override_comment"] is None
    assert body["technical_signoff_by"] == SUPPORT_A
    assert body["technical_signoff_at"].startswith("2026-10-19T09:00:00")


# --- TC-EVENTS-142 --------------------------------------------------------
@pytest.mark.parametrize(
    "body",
    [
        {"decision": "declined"},
        {"decision": "declined", "reason": "   "},
        {"decision": "approved", "reason": "x"},
        {"decision": "declined", "reason": "x", "override_comment": "y"},
        {"decision": "approved", "override_comment": "  "},
        {"decision": "declined", "reason": "x" * 501},
        {"decision": "maybe"},
    ],
)
def test_signoff_payload_rules(client, db, body):
    support_select(db, [planning_event()])

    response = sign_off(client, **body)

    assert response.status_code == 422
    table(db).update.assert_not_called()


# --- TC-EVENTS-143 --------------------------------------------------------
def test_signoff_limited_to_assigned_support_in_planning(client, db):
    support_select(db, [])
    response = client.put(
        f"/internal/events/{EVENT_ID}/technical-signoff",
        json={"technical_support_id": SUPPORT_B, "decision": "approved"},
    )
    assert response.status_code == 404

    for event_status in ("pending_safety_check", "confirmed"):
        support_select(db, [planning_event(status=event_status)])
        response = sign_off(client, decision="approved")
        assert response.status_code == 409
        assert response.json()["detail"] == (
            "Technical Support sign-off can only change while the event is in planning"
        )
    table(db).update.assert_not_called()


# --- TC-EVENTS-144 --------------------------------------------------------
@pytest.mark.parametrize(
    "signoff",
    [
        dict(
            technical_signoff_decision="approved",
            technical_signoff_override_comment="Borrowing 2 projectors from Library",
            technical_signoff_by=SUPPORT_A,
            technical_signoff_at="2026-10-19T09:00:00Z",
        ),
        dict(
            technical_signoff_decision="declined",
            technical_signoff_reason="Only one sound desk exists",
            technical_signoff_by=SUPPORT_A,
            technical_signoff_at="2026-10-19T09:00:00Z",
        ),
        {},
    ],
)
def test_clear_signoff_returns_to_awaiting(client, db, signoff):
    operation = table(db).update.return_value.eq.return_value
    operation.execute.return_value = SimpleNamespace(data=[planning_event()])

    response = client.post(f"/internal/events/{EVENT_ID}/technical-signoff/clear")

    assert response.status_code == 200, response.text
    table(db).update.assert_called_once_with({
        "technical_signoff_decision": None,
        "technical_signoff_reason": None,
        "technical_signoff_override_comment": None,
        "technical_signoff_by": None,
        "technical_signoff_at": None,
    })
    body = response.json()
    assert all(body[field] is None for field in (
        "technical_signoff_decision",
        "technical_signoff_reason",
        "technical_signoff_override_comment",
        "technical_signoff_by",
        "technical_signoff_at",
    ))


# --- TC-EVENTS-145 --------------------------------------------------------
@pytest.mark.parametrize("event_status", ["pending_safety_check", "confirmed"])
def test_organiser_reads_pending_and_confirmed(client, db, auth, event_status):
    on_owned_select(db, [planning_event(status=event_status, organiser_id=ORGANISER_ID)])
    authenticate(client, auth)

    response = client.get(f"/events/{EVENT_ID}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == event_status


# --- TC-EVENTS-146 --------------------------------------------------------
def test_pending_safety_check_is_open_everywhere_confirmed_is(client, db, auth):
    # 1. Coordinator active assignments
    authenticate(client, auth, fake_user(user_id=SUPPORT_A, role="event_coordinator_lead"))
    client.get("/internal/events/assigned-active")
    statuses = table(db).select.return_value.in_.call_args.args[1]
    assert "pending_safety_check" in statuses and "confirmed" in statuses

    # 2. Technical Support's assigned list
    authenticate(client, auth, fake_user(user_id=SUPPORT_A, role="technical_support"))
    client.get("/events/support-assigned")
    statuses = table(db).select.return_value.eq.return_value.in_.call_args.args[1]
    assert "pending_safety_check" in statuses and "confirmed" in statuses

    # 3. S-26 equipment preparation update
    pending = planning_event(status="pending_safety_check")
    support_select(db, [pending])
    preparation = table(db).update.return_value.eq.return_value.eq.return_value.in_.return_value
    preparation.execute.return_value = SimpleNamespace(data=[pending])
    response = client.put(
        f"/events/support-assigned/{EVENT_ID}/equipment-preparation",
        json={"status": "ready"},
    )
    assert response.status_code == 200, response.text

    # 4. S-62 cancellation request -- parametrised over every eligible status,
    # pending_safety_check included, in test_s62.py.
