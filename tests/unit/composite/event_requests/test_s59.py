"""S-59 composite orchestration: no accepted Events or Equipment writes."""

import pytest
import httpx

from .conftest import (
    COORDINATOR_A, EVENT_ID, ORGANISER_ID, event_response,
    fake_response, organiser_me_response,
)

PROJECTOR = "22222222-2222-4222-8222-222222222222"
MICROPHONE = "33333333-3333-4333-8333-333333333333"
BASE = {
    "start_date": "2026-11-18", "start_time": "09:00",
    "end_date": "2026-11-18", "end_time": "12:00",
    "expected_attendance": 120, "venue": "Main Hall",
    "special_requirements": None, "room_layout": "theatre",
    "required_facilities": ["projector"], "required_accessibility": [],
}


def current(status="confirmed", coordinator=COORDINATOR_A):
    return event_response(
        200, status=status, assigned_coordinator_id=coordinator,
        updated_at="2026-10-27T09:00:00Z", **BASE,
    ).json()


def submission(**changes):
    return {"values": {**BASE, "expected_attendance": 150, **changes}, "equipment": [{"equipment_item_id": PROJECTOR, "required_quantity": 2}]}


def configure(users, events, equipment, *, status="confirmed", role="event_organiser", coordinator=COORDINATOR_A):
    users.get.return_value = organiser_me_response(role=role)
    event = current(status, coordinator)

    async def event_get(path, **kwargs):
        if path in {f"/events/{EVENT_ID}", f"/events/assigned/{EVENT_ID}"}:
            return fake_response(200, event)
        if path == f"/events/{EVENT_ID}/change-requests":
            return fake_response(200, [])
        raise AssertionError(path)

    async def equipment_get(path, **kwargs):
        if path == "/internal/equipment-requirements":
            return fake_response(200, [{"equipment_item_id": PROJECTOR, "required_quantity": 2, "equipment": {"type": "Projector"}}])
        if path == "/equipment/selection":
            return fake_response(200, [{"id": PROJECTOR, "type": "Projector"}])
        raise AssertionError(path)

    events.get.side_effect = event_get
    equipment.get.side_effect = equipment_get
    events.post.return_value = fake_response(201, {"id": "44444444-4444-4444-8444-444444444444", "status": "pending"})


@pytest.mark.parametrize("status", [
    "submitted", "under_review", "returned", "planning",
    "pending_safety_check", "confirmed", "preparation",
])
def test_seven_states_submit_without_mutating_accepted_services(client, users, events, equipment, status):
    configure(users, events, equipment, status=status, coordinator=None if status == "submitted" else COORDINATOR_A)
    response = client.post(f"/event-requests/{EVENT_ID}/change-requests", json=submission())
    assert response.status_code == 201, response.json()
    body = events.post.call_args.kwargs["json"]
    assert body["proposed_values"]["expected_attendance"] == 150
    assert body["accepted_equipment"] == [{"equipment_item_id": PROJECTOR, "required_quantity": 2}]
    assert body["expected_event_updated_at"] == "2026-10-27T09:00:00Z"
    assert events.post.call_args.kwargs["headers"]["X-Assignment-Service-Token"]
    assert not equipment.put.called and not equipment.delete.called
    assert not events.patch.called


@pytest.mark.parametrize("role,expected", [
    ("event_coordinator", 403), ("event_coordinator_lead", 403), ("attendee", 403),
])
def test_other_roles_cannot_submit(client, users, events, equipment, role, expected):
    configure(users, events, equipment, role=role)
    response = client.post(f"/event-requests/{EVENT_ID}/change-requests", json=submission())
    assert response.status_code == expected
    assert not events.post.called


def test_unrelated_organiser_receives_scoped_404(client, users, events, equipment):
    configure(users, events, equipment)
    events.get.side_effect = None
    events.get.return_value = fake_response(404, {"detail": "Event not found"})
    response = client.post(f"/event-requests/{EVENT_ID}/change-requests", json=submission())
    assert response.status_code == 404
    assert not events.post.called


def test_noop_and_invalid_equipment_are_refused(client, users, events, equipment):
    configure(users, events, equipment)
    assert client.post(f"/event-requests/{EVENT_ID}/change-requests", json=submission(expected_attendance=120)).status_code == 422
    bad = submission()
    bad["equipment"] = [{"equipment_item_id": "ffffffff-ffff-4fff-8fff-ffffffffffff", "required_quantity": 1}]
    assert client.post(f"/event-requests/{EVENT_ID}/change-requests", json=bad).status_code == 422
    assert not events.post.called


def test_equipment_change_is_only_a_snapshot(client, users, events, equipment):
    configure(users, events, equipment)
    request = submission(expected_attendance=120)
    request["equipment"][0]["required_quantity"] = 3
    response = client.post(f"/event-requests/{EVENT_ID}/change-requests", json=request)
    assert response.status_code == 201
    body = events.post.call_args.kwargs["json"]
    assert body["accepted_equipment"][0]["required_quantity"] == 2
    assert body["proposed_equipment"][0]["required_quantity"] == 3
    assert not equipment.put.called and not equipment.delete.called


def test_retired_existing_equipment_may_be_removed_without_a_write(client, users, events, equipment):
    configure(users, events, equipment)

    async def equipment_get(path, **kwargs):
        if path == "/internal/equipment-requirements":
            return fake_response(200, [
                {"equipment_item_id": PROJECTOR, "required_quantity": 2},
                {"equipment_item_id": MICROPHONE, "required_quantity": 4},
            ])
        if path == "/equipment/selection":
            return fake_response(200, [{"id": PROJECTOR, "type": "Projector"}])
        raise AssertionError(path)

    equipment.get.side_effect = equipment_get
    response = client.post(f"/event-requests/{EVENT_ID}/change-requests", json=submission(expected_attendance=120))
    assert response.status_code == 201
    body = events.post.call_args.kwargs["json"]
    assert len(body["accepted_equipment"]) == 2
    assert body["proposed_equipment"] == [{"equipment_item_id": PROJECTOR, "required_quantity": 2}]
    assert not equipment.delete.called


def test_duplicate_equipment_item_ids_are_rejected(client, users, events, equipment):
    configure(users, events, equipment)
    request = submission()
    request["equipment"].append(request["equipment"][0].copy())
    assert client.post(f"/event-requests/{EVENT_ID}/change-requests", json=request).status_code == 422
    assert not events.post.called


def test_coordinator_read_uses_assigned_event_and_unrelated_gets_404(client, users, events, equipment):
    configure(users, events, equipment, role="event_coordinator")
    response = client.get(f"/event-requests/{EVENT_ID}/change-requests")
    assert response.status_code == 200
    assert events.get.call_args_list[0].args[0] == f"/events/assigned/{EVENT_ID}"
    events.get.side_effect = None
    events.get.return_value = fake_response(404, {"detail": "Event not found"})
    assert client.get(f"/event-requests/{EVENT_ID}/change-requests").status_code == 404


def test_duplicate_and_downstream_failure_are_not_reported_as_success(client, users, events, equipment):
    configure(users, events, equipment)
    events.post.return_value = fake_response(409, {"detail": "A change request is already pending"})
    assert client.post(f"/event-requests/{EVENT_ID}/change-requests", json=submission()).status_code == 409
    equipment.get.side_effect = httpx.TimeoutException("down")
    assert client.post(f"/event-requests/{EVENT_ID}/change-requests", json=submission()).status_code == 502


def test_observed_equipment_race_returns_stale_conflict(client, users, events, equipment):
    configure(users, events, equipment)
    reads = 0

    async def equipment_get(path, **kwargs):
        nonlocal reads
        assert path == "/internal/equipment-requirements"
        reads += 1
        return fake_response(200, [{
            "equipment_item_id": PROJECTOR,
            "required_quantity": 2 if reads == 1 else 3,
        }])

    equipment.get.side_effect = equipment_get
    response = client.post(f"/event-requests/{EVENT_ID}/change-requests", json=submission())
    assert response.status_code == 409
    assert reads == 2
    assert not events.post.called
