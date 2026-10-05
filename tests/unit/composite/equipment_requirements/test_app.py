"""Confirmed S-40 orchestration cases."""

import httpx
import pytest

from .conftest import (
    COORDINATOR_ID,
    EVENT_ID,
    ITEM_ID,
    NEW_COORDINATOR_ID,
    SECOND_EVENT_ID,
    SUPPORT_ID,
    event,
    fake_response,
    requirement,
    user,
)


def paths():
    return f"/equipment-requirements/{EVENT_ID}/{ITEM_ID}"


def assert_no_mutation(services):
    services.equipment.put.assert_not_called()
    services.equipment.delete.assert_not_called()


# --- TC-EQUIPMENTREQUIREMENTS-001 ---------------------------------------
def test_health_needs_no_downstream_service(client, services):
    for path in ("/health", "/equipment-requirements/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    services.users.get.assert_not_called()


# --- TC-EQUIPMENTREQUIREMENTS-002 / 003 ---------------------------------
def test_assigned_coordinator_saves_a_planning_requirement_with_verified_audit(client, services):
    response = client.put(paths(), json={"required_quantity": 6})

    assert response.status_code == 200
    services.events.get.assert_awaited_once_with(
        f"/events/assigned/{EVENT_ID}", cookies=client.cookies
    )
    services.equipment.put.assert_awaited_once()
    call = services.equipment.put.call_args
    assert call.args[0].endswith(f"/{EVENT_ID}/{ITEM_ID}")
    assert call.kwargs["json"] == {
        "required_quantity": 6,
        "recorded_by_coordinator_id": COORDINATOR_ID,
    }


def test_edit_returns_the_same_relationship_with_new_quantity(client, services):
    services.saved = fake_response(200, requirement(quantity=9))

    response = client.put(paths(), json={"required_quantity": 9})

    assert response.status_code == 200
    assert response.json()["id"] == requirement()["id"]
    assert response.json()["required_quantity"] == 9


# --- TC-EQUIPMENTREQUIREMENTS-004 ---------------------------------------
@pytest.mark.parametrize(
    "event_status",
    [
        "draft",
        "submitted",
        "returned",
        "rejected",
        "confirmed",
        "completed",
        "cancelled",
        "made_up_status",
    ],
)
@pytest.mark.parametrize("method", ["put", "delete"])
def test_every_non_planning_status_is_immutable(client, services, event_status, method):
    services.assigned_event = fake_response(200, event(status=event_status))

    response = (
        client.put(paths(), json={"required_quantity": 6})
        if method == "put"
        else client.delete(paths())
    )

    assert response.status_code == 409
    assert "only be edited" in response.json()["detail"]
    assert_no_mutation(services)


# --- TC-EQUIPMENTREQUIREMENTS-005 ---------------------------------------
def test_reassignment_uses_current_event_assignment_not_recorded_by(client, services):
    # Former Coordinator: the events service refuses the assigned-event read.
    services.assigned_event = fake_response(404, {"detail": "Event not found"})
    refused = client.put(paths(), json={"required_quantity": 9})
    assert refused.status_code == 404
    assert_no_mutation(services)

    # Newly assigned Coordinator: historical audit still names the former
    # user, but the new write is authorized by Events and refreshes the audit.
    services.me = fake_response(200, user(user_id=NEW_COORDINATOR_ID))
    services.assigned_event = fake_response(
        200, event(coordinator_id=NEW_COORDINATOR_ID)
    )
    services.saved = fake_response(
        200, requirement(quantity=9, recorded_by=NEW_COORDINATOR_ID)
    )
    accepted = client.put(paths(), json={"required_quantity": 9})

    assert accepted.status_code == 200
    assert services.equipment.put.call_args.kwargs["json"][
        "recorded_by_coordinator_id"
    ] == NEW_COORDINATOR_ID


# --- TC-EQUIPMENTREQUIREMENTS-006 ---------------------------------------
@pytest.mark.parametrize(
    "role", ["event_organiser", "technical_support", "venue_staff", "attendee", None, "admin"]
)
@pytest.mark.parametrize("method", ["put", "delete"])
def test_only_coordinator_mutates(client, services, role, method):
    services.me = fake_response(200, user(role=role))

    response = (
        client.put(paths(), json={"required_quantity": 6})
        if method == "put"
        else client.delete(paths())
    )

    assert response.status_code == 403
    services.events.get.assert_not_called()
    assert_no_mutation(services)


# --- TC-EQUIPMENTREQUIREMENTS-007 ---------------------------------------
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"required_quantity": 0},
        {"required_quantity": -1},
        {"required_quantity": 1.5},
        {"required_quantity": 6, "unknown": True},
        {"required_quantity": 6, "recorded_by_coordinator_id": NEW_COORDINATOR_ID},
    ],
)
def test_invalid_quantity_fails_before_orchestration(client, services, body):
    response = client.put(paths(), json=body)

    assert response.status_code == 422
    services.users.get.assert_not_called()
    services.events.get.assert_not_called()
    assert_no_mutation(services)


# --- TC-EQUIPMENTREQUIREMENTS-008 ---------------------------------------
def test_coordinator_reads_current_assignment_requirements(client, services):
    response = client.get("/equipment-requirements", params={"event_id": EVENT_ID})

    assert response.status_code == 200
    services.events.get.assert_awaited_once()
    services.equipment.get.assert_awaited_once_with(
        "/internal/equipment-requirements", params={"event_id": EVENT_ID}
    )


# --- TC-EQUIPMENTREQUIREMENTS-009 ---------------------------------------
def test_technical_support_reads_assigned_event_but_cannot_mutate(client, services):
    services.me = fake_response(
        200, user(role="technical_support", user_id=SUPPORT_ID)
    )

    read = client.get("/equipment-requirements", params={"event_id": EVENT_ID})
    write = client.put(paths(), json={"required_quantity": 6})
    remove = client.delete(paths())

    assert read.status_code == 200
    assert write.status_code == remove.status_code == 403
    services.events.get.assert_any_await(
        f"/events/support-assigned/{EVENT_ID}", cookies=client.cookies
    )
    assert_no_mutation(services)


# --- TC-EQUIPMENTREQUIREMENTS-010 ---------------------------------------
@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "attendee"])
def test_other_roles_cannot_read(client, services, role):
    services.me = fake_response(200, user(role=role))

    response = client.get("/equipment-requirements", params={"event_id": EVENT_ID})

    assert response.status_code == 403
    services.events.get.assert_not_called()
    services.equipment.get.assert_not_called()


# --- TC-EQUIPMENTREQUIREMENTS-011 ---------------------------------------
def test_wrong_coordinator_gets_404(client, services):
    services.assigned_event = fake_response(404, {"detail": "Event not found"})
    response = client.put(paths(), json={"required_quantity": 6})
    assert response.status_code == 404
    assert_no_mutation(services)


# --- TC-EQUIPMENTREQUIREMENTS-020 ---------------------------------------
def test_support_lists_requirements_only_for_active_assigned_events(client, services):
    services.me = fake_response(
        200, user(role="technical_support", user_id=SUPPORT_ID)
    )
    services.support_events = fake_response(
        200,
        [event(), event(event_id=SECOND_EVENT_ID, status="confirmed")],
    )

    response = client.get("/equipment-requirements")

    assert response.status_code == 200
    services.events.get.assert_awaited_once_with(
        "/events/support-assigned", cookies=client.cookies
    )
    services.equipment.get.assert_awaited_once_with(
        "/internal/equipment-requirements",
        params=[("event_ids", EVENT_ID), ("event_ids", SECOND_EVENT_ID)],
    )


# --- TC-EQUIPMENTREQUIREMENTS-021 ---------------------------------------
def test_support_with_no_active_assignments_gets_no_requirements(client, services):
    services.me = fake_response(
        200, user(role="technical_support", user_id=SUPPORT_ID)
    )
    services.support_events = fake_response(200, [])

    response = client.get("/equipment-requirements")

    assert response.status_code == 200
    assert response.json() == []
    services.equipment.get.assert_not_called()


# --- TC-EQUIPMENTREQUIREMENTS-022 ---------------------------------------
def test_support_cannot_select_an_unassigned_or_inactive_event(client, services):
    services.me = fake_response(
        200, user(role="technical_support", user_id=SUPPORT_ID)
    )
    services.support_event = fake_response(404, {"detail": "Event not found"})

    response = client.get(
        "/equipment-requirements", params={"event_id": SECOND_EVENT_ID}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found or not assigned to you"}
    services.equipment.get.assert_not_called()


@pytest.mark.parametrize("service", ["users", "events", "equipment"])
def test_downstream_connection_failures_are_named_502(client, services, service):
    target = getattr(services, service)
    method = target.get if service != "equipment" else target.put
    method.side_effect = httpx.ConnectError("internal address")

    response = client.put(paths(), json={"required_quantity": 6})

    assert response.status_code == 502
    assert response.json() == {"detail": f"{service.title()} service unavailable"}
    assert "internal address" not in response.text
