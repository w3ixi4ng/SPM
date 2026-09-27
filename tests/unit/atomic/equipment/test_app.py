"""Endpoint tests for the S-39 equipment atomic service."""

import pytest

from .conftest import (
    EVENT_ID,
    ITEM_ID,
    STAFF_ID,
    VALID_ITEM,
    authenticate,
    catalogue_operation,
    equipment_row,
    fake_user,
    insert_operation,
    returns,
    requirement_detail,
    requirement_row,
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


def _usable_item_operation(db):
    return (
        table(db)
        .select.return_value.eq.return_value.eq.return_value.eq.return_value
    )


# --- TC-EQUIPMENT-013 / 014 ---------------------------------------------
def test_requirement_upsert_uses_the_event_item_conflict_and_updates_audit(client, db):
    returns(_usable_item_operation(db), [{"id": ITEM_ID}])
    returns(table(db).upsert.return_value, [requirement_row(required_quantity=9)])

    response = client.put(
        f"/internal/equipment-requirements/{EVENT_ID}/{ITEM_ID}",
        json={"required_quantity": 9, "recorded_by_coordinator_id": STAFF_ID},
    )

    assert response.status_code == 200
    values = table(db).upsert.call_args.args[0]
    assert values["event_id"] == EVENT_ID
    assert values["equipment_item_id"] == ITEM_ID
    assert values["required_quantity"] == 9
    assert values["recorded_by_coordinator_id"] == STAFF_ID
    assert "updated_at" in values
    assert table(db).upsert.call_args.kwargs == {
        "on_conflict": "event_id,equipment_item_id"
    }


def test_requirement_refuses_an_item_outside_active_available_selection(client, db):
    returns(_usable_item_operation(db), [])

    response = client.put(
        f"/internal/equipment-requirements/{EVENT_ID}/{ITEM_ID}",
        json={"required_quantity": 6, "recorded_by_coordinator_id": STAFF_ID},
    )

    assert response.status_code == 409
    table(db).upsert.assert_not_called()


# --- TC-EQUIPMENT-015 ----------------------------------------------------
def test_requirement_list_embeds_catalogue_and_filters_by_event(client, db):
    operation = table(db).select.return_value.eq.return_value.order.return_value
    returns(operation, [requirement_detail()])

    response = client.get(
        "/internal/equipment-requirements", params={"event_id": EVENT_ID}
    )

    assert response.status_code == 200
    assert response.json()[0]["equipment"]["type"] == "Wireless Microphone"
    table(db).select.return_value.eq.assert_called_once_with("event_id", EVENT_ID)
    table(db).select.return_value.eq.return_value.order.assert_called_once_with(
        "created_at"
    )


# --- TC-EQUIPMENT-016 ----------------------------------------------------
def test_requirement_delete_is_constrained_by_event_and_item(client, db):
    operation = (
        table(db)
        .delete.return_value.eq.return_value.eq.return_value
    )
    returns(operation, [requirement_row()])

    response = client.delete(
        f"/internal/equipment-requirements/{EVENT_ID}/{ITEM_ID}"
    )

    assert response.status_code == 204
    first_eq = table(db).delete.return_value.eq
    first_eq.assert_called_once_with("event_id", EVENT_ID)
    first_eq.return_value.eq.assert_called_once_with("equipment_item_id", ITEM_ID)


def test_requirement_delete_returns_404_when_relationship_is_missing(client, db):
    operation = table(db).delete.return_value.eq.return_value.eq.return_value
    returns(operation, [])

    response = client.delete(
        f"/internal/equipment-requirements/{EVENT_ID}/{ITEM_ID}"
    )

    assert response.status_code == 404


# --- TC-EQUIPMENT-017 ----------------------------------------------------
@pytest.mark.parametrize("method", ["put", "get", "delete"])
def test_requirement_storage_failures_are_safe(client, db, method):
    if method == "put":
        _usable_item_operation(db).execute.side_effect = Exception("database secret")
        response = client.put(
            f"/internal/equipment-requirements/{EVENT_ID}/{ITEM_ID}",
            json={"required_quantity": 6, "recorded_by_coordinator_id": STAFF_ID},
        )
    elif method == "get":
        table(db).select.return_value.order.return_value.execute.side_effect = Exception(
            "database secret"
        )
        response = client.get("/internal/equipment-requirements")
    else:
        operation = table(db).delete.return_value.eq.return_value.eq.return_value
        operation.execute.side_effect = Exception("database secret")
        response = client.delete(
            f"/internal/equipment-requirements/{EVENT_ID}/{ITEM_ID}"
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Equipment storage unavailable"}
    assert "database secret" not in response.text
