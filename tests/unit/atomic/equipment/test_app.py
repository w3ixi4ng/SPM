"""Endpoint tests for the equipment atomic service."""

from types import SimpleNamespace

import pytest

from .conftest import (
    EVENT_ID,
    ITEM_ID,
    STAFF_ID,
    VALID_ITEM,
    VALID_UPDATE,
    authenticate,
    catalogue_operation,
    detail_operation,
    equipment_row,
    fake_user,
    insert_operation,
    returns,
    requirement_detail,
    requirement_row,
    selection_operation,
    table,
    update_operation,
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


# --- TC-EQUIPMENT-019 ----------------------------------------------------
def test_invalid_update_never_calls_storage(client, db, auth):
    authenticate(client, auth)

    response = client.put(
        f"/equipment/{ITEM_ID}",
        json={**VALID_UPDATE, "type": " ", "total_quantity": 0},
    )

    assert response.status_code == 422
    assert set(response.json()["errors"]) == {"type", "total_quantity"}
    db.schema.assert_not_called()


# --- TC-EQUIPMENT-020 ----------------------------------------------------
def test_technical_support_reads_and_updates_one_item(client, db, auth):
    authenticate(client, auth)
    returns(detail_operation(db), [equipment_row()])
    updated = equipment_row(**VALID_UPDATE, updated_at="2026-09-28T01:00:00Z")
    returns(update_operation(db), [updated])

    read = client.get(f"/equipment/{ITEM_ID}")
    response = client.put(f"/equipment/{ITEM_ID}", json=VALID_UPDATE)

    assert read.status_code == 200
    assert read.json() == equipment_row()
    assert response.status_code == 200
    assert response.json() == updated
    table(db).select.assert_called_once_with("*")
    table(db).select.return_value.eq.assert_called_once_with("id", ITEM_ID)
    values = table(db).update.call_args.args[0]
    assert {key: values[key] for key in VALID_UPDATE} == VALID_UPDATE
    assert set(values) == {*VALID_UPDATE, "updated_at"}
    table(db).update.return_value.eq.assert_called_once_with("id", ITEM_ID)
    table(db).update.return_value.eq.return_value.select.assert_called_once_with("*")


# --- TC-EQUIPMENT-021 ----------------------------------------------------
def test_missing_item_returns_404(client, db, auth):
    authenticate(client, auth)
    returns(detail_operation(db), [])
    returns(update_operation(db), [])

    responses = [
        client.get(f"/equipment/{ITEM_ID}"),
        client.put(f"/equipment/{ITEM_ID}", json=VALID_UPDATE),
    ]

    assert all(response.status_code == 404 for response in responses)
    assert all(
        response.json() == {"detail": "Equipment item not found"}
        for response in responses
    )


# --- TC-EQUIPMENT-022 ----------------------------------------------------
def test_s41_requires_a_session(client, db):
    responses = [
        client.get(f"/equipment/{ITEM_ID}"),
        client.put(f"/equipment/{ITEM_ID}", json=VALID_UPDATE),
    ]

    assert all(response.status_code == 401 for response in responses)
    assert all(response.json() == {"detail": "Not authenticated"} for response in responses)
    db.schema.assert_not_called()


@pytest.mark.parametrize(
    "role", ["event_organiser", "event_coordinator", "venue_staff", "attendee"]
)
def test_only_technical_support_updates_equipment(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))

    responses = [
        client.get(f"/equipment/{ITEM_ID}"),
        client.put(f"/equipment/{ITEM_ID}", json=VALID_UPDATE),
    ]

    assert all(response.status_code == 403 for response in responses)
    assert all(response.json() == {"detail": "Permission denied"} for response in responses)
    db.schema.assert_not_called()


# --- TC-EQUIPMENT-023 ----------------------------------------------------
def test_catalogue_update_does_not_touch_requirements(client, db, auth):
    authenticate(client, auth)
    returns(update_operation(db), [equipment_row(**VALID_UPDATE)])

    response = client.put(f"/equipment/{ITEM_ID}", json=VALID_UPDATE)

    assert response.status_code == 200
    db.schema.assert_called_once_with("equipment")
    db.schema.return_value.table.assert_called_once_with("equipment")
    table(db).insert.assert_not_called()
    table(db).upsert.assert_not_called()
    table(db).delete.assert_not_called()


# --- TC-EQUIPMENT-024 ----------------------------------------------------
@pytest.mark.parametrize("method", ["get", "put"])
def test_s41_storage_failures_are_safe(client, db, auth, method):
    authenticate(client, auth)
    if method == "get":
        detail_operation(db).execute.side_effect = Exception("database secret")
        response = client.get(f"/equipment/{ITEM_ID}")
    else:
        update_operation(db).execute.side_effect = Exception("database secret")
        response = client.put(f"/equipment/{ITEM_ID}", json=VALID_UPDATE)

    assert response.status_code == 500
    assert response.json() == {"detail": "Equipment storage unavailable"}
    assert "database secret" not in response.text


# --- TC-EQUIPMENT-025 ----------------------------------------------------
def test_technical_support_retires_an_item_idempotently(client, db, auth):
    authenticate(client, auth)
    active = equipment_row(operational_status="maintenance")
    retired = equipment_row(
        operational_status="maintenance",
        lifecycle_status="retired",
        updated_at="2026-09-28T02:00:00Z",
    )
    detail_operation(db).execute.side_effect = [
        SimpleNamespace(data=[active]),
        SimpleNamespace(data=[retired]),
    ]
    returns(update_operation(db), [retired])

    first = client.post(f"/equipment/{ITEM_ID}/retire")
    second = client.post(f"/equipment/{ITEM_ID}/retire")

    assert first.status_code == 200
    assert first.json() == retired
    assert second.status_code == 200
    assert second.json() == retired
    assert second.json()["updated_at"] == first.json()["updated_at"]
    values = table(db).update.call_args.args[0]
    assert set(values) == {"lifecycle_status", "updated_at"}
    assert values["lifecycle_status"] == "retired"
    assert values["updated_at"] != active["updated_at"]
    table(db).update.assert_called_once()

    unchanged = (
        "id",
        "type",
        "description",
        "total_quantity",
        "operational_status",
        "created_by",
        "created_at",
    )
    for field in unchanged:
        assert first.json()[field] == active[field]


# --- TC-EQUIPMENT-026 ----------------------------------------------------
def test_retirement_requires_a_session(client, db):
    response = client.post(f"/equipment/{ITEM_ID}/retire")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    db.schema.assert_not_called()


@pytest.mark.parametrize(
    "role", ["event_organiser", "event_coordinator", "venue_staff", "attendee"]
)
def test_only_technical_support_retires_equipment(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))

    response = client.post(f"/equipment/{ITEM_ID}/retire")

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied"}
    db.schema.assert_not_called()


# --- TC-EQUIPMENT-027 ----------------------------------------------------
def test_retiring_missing_item_returns_404(client, db, auth):
    authenticate(client, auth)
    returns(detail_operation(db), [])

    response = client.post(f"/equipment/{ITEM_ID}/retire")

    assert response.status_code == 404
    assert response.json() == {"detail": "Equipment item not found"}
    table(db).update.assert_not_called()


# --- TC-EQUIPMENT-028 ----------------------------------------------------
def test_retired_item_is_excluded_from_selection(client, db, auth):
    authenticate(client, auth)
    returns(selection_operation(db), [])

    response = client.get("/equipment/selection")

    assert response.status_code == 200
    assert response.json() == []
    first_filter = table(db).select.return_value.eq
    first_filter.assert_called_once_with("operational_status", "available")
    first_filter.return_value.eq.assert_called_once_with("lifecycle_status", "active")


def test_retired_item_is_refused_for_new_requirements(client, db):
    returns(_usable_item_operation(db), [])

    response = client.put(
        f"/internal/equipment-requirements/{EVENT_ID}/{ITEM_ID}",
        json={"required_quantity": 6, "recorded_by_coordinator_id": STAFF_ID},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Equipment item is not available for new requirements"
    }
    table(db).upsert.assert_not_called()


def test_existing_requirement_remains_readable_after_retirement(client, db):
    retired_detail = requirement_detail()
    retired_detail["equipment"]["lifecycle_status"] = "retired"
    operation = table(db).select.return_value.eq.return_value.order.return_value
    returns(operation, [retired_detail])

    response = client.get(
        "/internal/equipment-requirements", params={"event_id": EVENT_ID}
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == retired_detail["id"]
    assert response.json()[0]["event_id"] == retired_detail["event_id"]
    assert response.json()[0]["equipment_item_id"] == retired_detail["equipment_item_id"]
    assert response.json()[0]["required_quantity"] == 6
    assert response.json()[0]["equipment"]["lifecycle_status"] == "retired"


def test_retirement_never_deletes_or_mutates_requirements(client, db, auth):
    authenticate(client, auth)
    returns(detail_operation(db), [equipment_row()])
    returns(
        update_operation(db),
        [equipment_row(lifecycle_status="retired", updated_at="2026-09-28T02:00:00Z")],
    )

    response = client.post(f"/equipment/{ITEM_ID}/retire")

    assert response.status_code == 200
    assert [entry.args for entry in db.schema.return_value.table.call_args_list] == [
        ("equipment",),
        ("equipment",),
    ]
    table(db).insert.assert_not_called()
    table(db).upsert.assert_not_called()
    table(db).delete.assert_not_called()


# --- TC-EQUIPMENT-029 ----------------------------------------------------
@pytest.mark.parametrize("failure", ["lookup", "update"])
def test_retirement_storage_failures_are_safe(client, db, auth, failure):
    authenticate(client, auth)
    if failure == "lookup":
        detail_operation(db).execute.side_effect = Exception("database secret")
    else:
        returns(detail_operation(db), [equipment_row()])
        update_operation(db).execute.side_effect = Exception("database secret")

    response = client.post(f"/equipment/{ITEM_ID}/retire")

    assert response.status_code == 500
    assert response.json() == {"detail": "Equipment storage unavailable"}
    assert "database secret" not in response.text
