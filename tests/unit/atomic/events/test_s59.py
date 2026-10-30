"""S-59 request persistence and scope with fake Events storage."""

from types import SimpleNamespace

import pytest

from .conftest import (
    COORDINATOR_A, EVENT_ID, ORGANISER_ID, authenticate, event_row,
    fake_user, on_insert, on_owned_select,
)

HEADERS = {"X-Assignment-Service-Token": "unit-assignment-secret"}
ACCEPTED = {
    "start_date": "2026-11-18", "start_time": "09:00:00",
    "end_date": "2026-11-18", "end_time": "12:00:00",
    "expected_attendance": 120, "venue": "Main Hall",
    "special_requirements": None, "room_layout": "theatre",
    "required_facilities": ["projector"], "required_accessibility": [],
}


def event(status="confirmed", coordinator=COORDINATOR_A):
    return event_row(
        status=status, assigned_coordinator_id=coordinator,
        name="Autumn Forum", purpose="Meet alumni", **ACCEPTED,
    )


def payload(**changes):
    return {
        "expected_event_updated_at": "2026-09-14T00:00:00Z",
        "proposed_values": {**ACCEPTED, "expected_attendance": 150, **changes},
        "accepted_equipment": [], "proposed_equipment": [],
    }


def request_row(**changes):
    return {
        "id": "44444444-4444-4444-8444-444444444444",
        "event_id": EVENT_ID, "requested_by": ORGANISER_ID,
        "submitted_at": "2026-10-27T09:15:00Z", "status": "pending",
        "expected_event_updated_at": "2026-09-14T00:00:00Z",
        "accepted_values": ACCEPTED,
        "proposed_values": {**ACCEPTED, "expected_attendance": 150},
        "accepted_equipment": [], "proposed_equipment": [],
        "resolved_at": None,
        **changes,
    }


@pytest.mark.parametrize("status", [
    "submitted", "under_review", "returned", "planning",
    "pending_safety_check", "confirmed", "preparation",
])
def test_all_seven_states_allow_a_request_including_unassigned_submitted(client, db, auth, status):
    authenticate(client, auth)
    on_owned_select(db, [event(status, None if status == "submitted" else COORDINATOR_A)])
    on_insert(db, [request_row()])
    response = client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload(), headers=HEADERS)
    assert response.status_code == 201, response.json()
    inserted = db.schema.return_value.table.return_value.insert.call_args.args[0]
    assert inserted["requested_by"] == ORGANISER_ID
    assert inserted["proposed_values"]["expected_attendance"] == 150
    assert inserted["accepted_values"]["expected_attendance"] == 120
    assert not db.schema.return_value.table.return_value.update.called


@pytest.mark.parametrize("status", ["draft", "cancelled", "rejected", "safety_rejected"])
def test_ineligible_state_cannot_create_a_request(client, db, auth, status):
    authenticate(client, auth)
    on_owned_select(db, [event(status)])
    response = client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload(), headers=HEADERS)
    assert response.status_code == 409
    assert not db.schema.return_value.table.return_value.insert.called


def test_direct_caller_needs_trusted_service_credential(client, db, auth):
    authenticate(client, auth)
    client.headers.pop("X-Assignment-Service-Token", None)
    assert client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload()).status_code == 403
    assert client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload(), headers={"X-Assignment-Service-Token": "forged"}).status_code == 403
    assert not db.schema.return_value.table.return_value.insert.called


def test_noop_and_bad_window_do_not_insert(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event()])
    assert client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload(expected_attendance=120), headers=HEADERS).status_code == 422
    assert client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload(end_time="08:00"), headers=HEADERS).status_code == 422
    assert not db.schema.return_value.table.return_value.insert.called


def test_date_duration_attendance_and_venue_changes_stay_in_proposal(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event()])
    on_insert(db, [request_row(proposed_values={
        **ACCEPTED, "start_date": "2026-11-19", "end_date": "2026-11-19",
        "end_time": "13:00:00", "expected_attendance": 150, "venue": "North Hall",
        "room_layout": "banquet", "required_facilities": ["projector", "stage"],
    })])
    response = client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload(
        start_date="2026-11-19", end_date="2026-11-19", end_time="13:00",
        venue="North Hall", room_layout="banquet",
        required_facilities=["stage", "projector"],
    ), headers=HEADERS)
    assert response.status_code == 201, response.json()
    inserted = db.schema.return_value.table.return_value.insert.call_args.args[0]
    assert inserted["proposed_values"]["start_date"] == "2026-11-19"
    assert inserted["proposed_values"]["end_time"] == "13:00:00"
    assert inserted["proposed_values"]["required_facilities"] == ["projector", "stage"]
    assert inserted["accepted_values"]["venue"] == "Main Hall"
    assert not db.schema.return_value.table.return_value.update.called


def test_unrelated_organiser_and_coordinator_cannot_submit(client, db, auth):
    authenticate(client, auth, fake_user(COORDINATOR_A, "event_coordinator"))
    assert client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload(), headers=HEADERS).status_code == 403
    authenticate(client, auth, fake_user("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))
    on_owned_select(db, [])
    assert client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload(), headers=HEADERS).status_code == 404
    client.cookies.clear()
    auth.auth.get_user.return_value = SimpleNamespace(user=None)
    assert client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload(), headers=HEADERS).status_code == 401
    assert not db.schema.return_value.table.return_value.insert.called


def test_pending_proposal_blocks_direct_accepted_edit(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event("submitted")])
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[{"id": "pending"}])
    response = client.patch(f"/events/{EVENT_ID}", json={"expected_attendance": 150})
    assert response.status_code == 409
    assert not db.schema.return_value.table.return_value.update.called


@pytest.mark.parametrize("code,expected", [("23505", 409), ("23514", 409), ("42501", 404), ("unexpected", 500)])
def test_storage_conflicts_are_controlled_and_leave_event_untouched(client, db, auth, code, expected):
    authenticate(client, auth)
    on_owned_select(db, [event()])
    failure = RuntimeError("storage error")
    failure.code = code
    on_insert(db, error=failure)
    response = client.post(f"/events/{EVENT_ID}/change-request/internal", json=payload(), headers=HEADERS)
    assert response.status_code == expected
    assert not db.schema.return_value.table.return_value.update.called


def test_read_is_scoped_to_owner_or_current_coordinator(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event()])
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = SimpleNamespace(data=[request_row()])
    response = client.get(f"/events/{EVENT_ID}/change-requests")
    assert response.status_code == 200
    assert response.json()[0]["status"] == "pending"
    authenticate(client, auth, fake_user(COORDINATOR_A, "event_coordinator"))
    assert client.get(f"/events/{EVENT_ID}/change-requests").status_code == 200
    authenticate(client, auth, fake_user("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "event_coordinator"))
    on_owned_select(db, [])
    assert client.get(f"/events/{EVENT_ID}/change-requests").status_code == 404


def test_request_read_follows_current_assignment_after_transfer(client, db, auth):
    coordinator_b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    assigned_query = db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value
    assigned_query.execute.side_effect = [
        SimpleNamespace(data=[event()]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[event(coordinator=coordinator_b)]),
        SimpleNamespace(data=[]),
    ]
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = SimpleNamespace(data=[request_row()])
    authenticate(client, auth, fake_user(COORDINATOR_A, "event_coordinator"))
    assert client.get(f"/events/{EVENT_ID}/change-requests").status_code == 200
    authenticate(client, auth, fake_user(coordinator_b, "event_coordinator"))
    assert client.get(f"/events/{EVENT_ID}/change-requests").status_code == 404
    assert client.get(f"/events/{EVENT_ID}/change-requests").status_code == 200
    authenticate(client, auth, fake_user(COORDINATOR_A, "event_coordinator"))
    assert client.get(f"/events/{EVENT_ID}/change-requests").status_code == 404
