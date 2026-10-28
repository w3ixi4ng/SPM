"""S-93 limited inventory, lifecycle, and direct-port assignment protection."""

from types import SimpleNamespace

import pytest

from .conftest import COORDINATOR_A, COORDINATOR_B, EVENT_ID, ORGANISER_ID, authenticate, fake_user, on_owned_select
from .test_s84 import ACTIVE, LEAD_ID, assigned_row, payload, reassignment_write


@pytest.fixture(autouse=True)
def lead_session(client, auth):
    authenticate(client, auth, fake_user(LEAD_ID, "event_coordinator_lead"))


def test_selected_coordinator_inventory_uses_all_open_states_and_limited_fields(client, db):
    operation = (db.schema.return_value.table.return_value.select.return_value
                 .eq.return_value.in_.return_value.order.return_value)
    operation.execute.return_value = SimpleNamespace(data=[{
        "id": EVENT_ID, "name": "Autumn Forum", "status": "preparation",
        "start_date": "2026-11-18", "start_time": "09:00:00",
        "end_date": "2026-11-18", "end_time": "12:00:00",
        "assigned_coordinator_id": COORDINATOR_A, "assigning_lead_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        "coordinator_assignment_version": 2,
    }])

    response = client.get(f"/internal/events/coordinators/{COORDINATOR_A}/active-summary")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Autumn Forum"
    db.schema.return_value.table.return_value.select.assert_called_once_with(
        "id,name,status,start_date,start_time,end_date,end_time,assigned_coordinator_id,assigning_lead_id,coordinator_assignment_version"
    )
    db.schema.return_value.table.return_value.select.return_value.eq.assert_called_once_with(
        "assigned_coordinator_id", COORDINATOR_A
    )
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.in_.assert_called_once_with(
        "status", ACTIVE
    )


def test_selected_inventory_denies_non_leads_and_anonymous_callers(client, db, auth):
    authenticate(client, auth, fake_user(COORDINATOR_A, "event_coordinator"))
    denied = client.get(f"/internal/events/coordinators/{COORDINATOR_A}/active-summary")
    assert denied.status_code == 403
    client.cookies.clear()
    anonymous = client.get(f"/internal/events/coordinators/{COORDINATOR_A}/active-summary")
    assert anonymous.status_code == 401
    db.schema.assert_not_called()


@pytest.mark.parametrize("path,body", [
    ("assignment", {"coordinator_id": COORDINATOR_B}),
    ("reassignment", payload()),
])
@pytest.mark.parametrize("token", [None, "forged"])
def test_direct_assignment_writes_require_service_credential(client, db, path, body, token):
    client.headers.pop("X-Assignment-Service-Token", None)
    if token:
        client.headers.update({"X-Assignment-Service-Token": token})
    response = client.post(f"/internal/events/{EVENT_ID}/{path}", json=body)
    assert response.status_code == 403
    db.schema.assert_not_called()


@pytest.mark.parametrize("event_status", ["under_review", "preparation", "safety_rejected", "safety_changes_requested"])
def test_reassignment_accepts_open_lifecycle_with_version_guard(client, db, event_status):
    current = assigned_row(version=2, status=event_status)
    changed = assigned_row(owner=COORDINATOR_B, previous=COORDINATOR_A, version=3, status=event_status)
    db.schema.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[current])
    reassignment_write(db, [changed])
    response = client.post(f"/internal/events/{EVENT_ID}/reassignment", json=payload(version=2))
    assert response.status_code == 200
    assert response.json()["assigned_coordinator_id"] == COORDINATOR_B
    assert response.json()["coordinator_assignment_version"] == 3


def test_older_internal_routes_cannot_change_coordinator_assignment(client, db):
    submitted = {
        "name": "Autumn Forum", "purpose": "S-93 direct-port check",
        "start_date": "2026-11-18", "start_time": "09:00",
        "end_date": "2026-11-18", "end_time": "12:00",
        "expected_attendance": 40, "organiser_id": ORGANISER_ID,
    }
    created = client.post("/events/internal", json={
        **submitted, "assigned_coordinator_id": COORDINATOR_B,
    })
    assert created.status_code == 422
    db.schema.assert_not_called()

    on_owned_select(db, [assigned_row(owner=COORDINATOR_A, status="returned")])
    resubmitted = client.post(f"/events/{EVENT_ID}/submit/internal", json={
        **submitted, "assigned_coordinator_id": COORDINATOR_B,
    })
    assert resubmitted.status_code == 409
    assert db.schema.return_value.table.return_value.update.call_count == 0

    patched = client.patch(f"/events/{EVENT_ID}/internal", json={
        "organiser_id": ORGANISER_ID, "assigned_coordinator_id": COORDINATOR_B,
    })
    assert patched.status_code == 409
    assert db.schema.return_value.table.return_value.update.call_count == 0
