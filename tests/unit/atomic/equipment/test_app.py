"""Endpoint tests for the S-39 equipment atomic service."""

import pytest

from .conftest import (
    STAFF_ID,
    VALID_ITEM,
    authenticate,
    catalogue_operation,
    equipment_row,
    fake_user,
    insert_operation,
    returns,
    selection_operation,
    table,
)


# --- TC-EQUIPMENT-002 ----------------------------------------------------
def test_invalid_create_never_calls_storage(client, db, auth):
    authenticate(client, auth)

    response = client.post("/equipment", json={"type": " ", "total_quantity": 0})

    assert response.status_code == 422
    assert set(response.json()["errors"]) == {"type", "total_quantity"}
    db.schema.assert_not_called()


# --- TC-EQUIPMENT-003 ----------------------------------------------------
def test_technical_support_creates_an_active_available_item(client, db, auth):
    authenticate(client, auth)
    returns(insert_operation(db), [equipment_row()])

    response = client.post("/equipment", json=VALID_ITEM)

    assert response.status_code == 201
    db.schema.assert_called_once_with("equipment")
    table(db).insert.assert_called_once_with(
        {
            **VALID_ITEM,
            "operational_status": "available",
            "lifecycle_status": "active",
            "created_by": STAFF_ID,
        }
    )
    assert response.json() == equipment_row()


# --- TC-EQUIPMENT-004 ----------------------------------------------------
@pytest.mark.parametrize(
    "role", ["event_organiser", "event_coordinator", "venue_staff", "attendee"]
)
def test_only_technical_support_can_create(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))

    response = client.post("/equipment", json=VALID_ITEM)

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied"}
    db.schema.assert_not_called()


# --- TC-EQUIPMENT-005 ----------------------------------------------------
def test_create_requires_a_session(client, db):
    response = client.post("/equipment", json=VALID_ITEM)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    db.schema.assert_not_called()


# --- TC-EQUIPMENT-006 ----------------------------------------------------
def test_technical_support_lists_the_complete_catalogue(client, db, auth):
    authenticate(client, auth)
    rows = [equipment_row(), equipment_row(type="Projector", operational_status="maintenance")]
    returns(catalogue_operation(db), rows)

    response = client.get("/equipment")

    assert response.status_code == 200
    assert response.json() == rows
    table(db).select.assert_called_once_with("*")
    table(db).select.return_value.order.assert_called_once_with("type")


# --- TC-EQUIPMENT-007 ----------------------------------------------------
@pytest.mark.parametrize("role", ["technical_support", "event_coordinator", "event_organiser"])
def test_workflow_roles_list_active_available_selection(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))
    returns(selection_operation(db), [equipment_row()])

    response = client.get("/equipment/selection")

    assert response.status_code == 200
    assert response.json() == [equipment_row()]
    first_filter = table(db).select.return_value.eq
    first_filter.assert_called_once_with("operational_status", "available")
    second_filter = first_filter.return_value.eq
    second_filter.assert_called_once_with("lifecycle_status", "active")
    second_filter.return_value.order.assert_called_once_with("type")


# --- TC-EQUIPMENT-008 ----------------------------------------------------
@pytest.mark.parametrize("role", ["event_organiser", "event_coordinator", "venue_staff", "attendee"])
def test_only_technical_support_reads_management_catalogue(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))

    response = client.get("/equipment")

    assert response.status_code == 403
    db.schema.assert_not_called()


@pytest.mark.parametrize("role", ["venue_staff", "attendee"])
def test_unrelated_roles_cannot_read_selection(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))

    response = client.get("/equipment/selection")

    assert response.status_code == 403
    db.schema.assert_not_called()


# --- TC-EQUIPMENT-009 ----------------------------------------------------
@pytest.mark.parametrize("role", [None, "admin"])
def test_unknown_roles_fail_closed(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))

    responses = [
        client.get("/equipment"),
        client.get("/equipment/selection"),
        client.post("/equipment", json=VALID_ITEM),
    ]

    assert all(response.status_code == 403 for response in responses)
    assert all(response.json() == {"detail": "Recognized role required"} for response in responses)
    db.schema.assert_not_called()


# --- TC-EQUIPMENT-010 ----------------------------------------------------
def test_storage_failures_are_safe(client, db, auth):
    authenticate(client, auth)
    insert_operation(db).execute.side_effect = Exception("connection refused")
    catalogue_operation(db).execute.side_effect = Exception("connection refused")

    responses = [
        client.post("/equipment", json=VALID_ITEM),
        client.get("/equipment"),
    ]

    for response in responses:
        assert response.status_code == 500
        assert response.json() == {"detail": "Equipment storage unavailable"}
        assert "connection refused" not in response.text


# --- TC-EQUIPMENT-011 ----------------------------------------------------
def test_health_needs_no_storage_or_session(client, db):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    db.schema.assert_not_called()
