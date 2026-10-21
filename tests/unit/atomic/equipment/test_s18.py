"""S-18 atomic requirement-audit boundary."""

from types import SimpleNamespace

from .conftest import EVENT_ID, ITEM_ID, STAFF_ID, requirement_row


def usable(db, rows):
    operation = (
        db.schema.return_value.table.return_value.select.return_value
        .eq.return_value.eq.return_value.eq.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)


def test_audited_requirement_save_uses_one_database_function(client, db):
    usable(db, [{"id": ITEM_ID}])
    db.schema.return_value.rpc.return_value.execute.return_value = SimpleNamespace(
        data=[requirement_row(required_quantity=4)]
    )

    response = client.put(
        f"/internal/equipment-requirements/{EVENT_ID}/{ITEM_ID}/audited",
        json={"required_quantity": 4, "recorded_by_coordinator_id": STAFF_ID},
    )

    assert response.status_code == 200
    db.schema.return_value.rpc.assert_called_once_with(
        "save_requirement_with_history",
        {
            "p_event_id": EVENT_ID,
            "p_equipment_item_id": ITEM_ID,
            "p_required_quantity": 4,
            "p_changed_by": STAFF_ID,
        },
    )


def test_audited_requirement_removal_uses_one_database_function(client, db):
    db.schema.return_value.rpc.return_value.execute.return_value = SimpleNamespace(
        data=[requirement_row()]
    )

    response = client.post(
        f"/internal/equipment-requirements/{EVENT_ID}/{ITEM_ID}/remove-audited",
        json={"recorded_by_coordinator_id": STAFF_ID},
    )

    assert response.status_code == 204
    db.schema.return_value.rpc.assert_called_once_with(
        "delete_requirement_with_history",
        {"p_event_id": EVENT_ID, "p_equipment_item_id": ITEM_ID, "p_changed_by": STAFF_ID},
    )
