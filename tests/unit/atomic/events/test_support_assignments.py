"""S-43 visibility for the Technical Support staff currently assigned."""

from types import SimpleNamespace

import pytest

from .conftest import EVENT_ID, authenticate, event_row, fake_user

SUPPORT_A = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
SUPPORT_B = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
EVENT_B = "ffffffff-ffff-4fff-8fff-ffffffffffff"
EVENT_C = "99999999-9999-4999-8999-999999999999"


def support_event(event_id=EVENT_ID, status="planning", staff_id=SUPPORT_A, **changes):
    return event_row(
        id=event_id,
        status=status,
        assigned_technical_support_id=staff_id,
        technical_support_required=True,
        technical_support_details="Sound check",
        technical_support_assigned_at="2026-10-05T01:00:00Z",
        **changes,
    )


# --- TC-EVENTS-109 -------------------------------------------------------
def test_technical_support_lists_only_its_active_assigned_events(client, db, auth):
    authenticate(client, auth, fake_user(user_id=SUPPORT_A, role="technical_support"))
    rows = [
        support_event(status="confirmed", name="Awards night"),
        support_event(event_id=EVENT_C, name="Sound check"),
    ]
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value
        .in_.return_value.order.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)

    response = client.get("/events/support-assigned")

    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == ["Awards night", "Sound check"]
    select = db.schema.return_value.table.return_value.select.return_value
    select.eq.assert_called_once_with("assigned_technical_support_id", SUPPORT_A)
    select.eq.return_value.in_.assert_called_once_with(
        "status", ["planning", "pending_safety_check", "confirmed", "preparation"]
    )
    select.eq.return_value.in_.return_value.order.assert_called_once_with(
        "updated_at", desc=True
    )


# --- TC-EVENTS-110 -------------------------------------------------------
def test_support_worker_reads_one_active_event_assigned_to_them(client, db, auth):
    authenticate(client, auth, fake_user(user_id=SUPPORT_A, role="technical_support"))
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value
        .eq.return_value.in_.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=[support_event()])

    response = client.get(f"/events/support-assigned/{EVENT_ID}")

    assert response.status_code == 200
    first_eq = db.schema.return_value.table.return_value.select.return_value.eq
    first_eq.assert_called_once_with("id", EVENT_ID)
    first_eq.return_value.eq.assert_called_once_with(
        "assigned_technical_support_id", SUPPORT_A
    )
    first_eq.return_value.eq.return_value.in_.assert_called_once_with(
        "status", ["planning", "pending_safety_check", "confirmed", "preparation"]
    )


@pytest.mark.parametrize(
    "stored",
    [
        support_event(event_id=EVENT_B, staff_id=SUPPORT_B),
        support_event(event_id=EVENT_C, status="cancelled"),
        None,
    ],
)
def test_support_worker_cannot_read_unassigned_or_inactive_event(
    client, db, auth, stored
):
    authenticate(client, auth, fake_user(user_id=SUPPORT_A, role="technical_support"))
    operation = (
        db.schema.return_value.table.return_value.select.return_value.eq.return_value
        .eq.return_value.in_.return_value
    )
    # Supabase applies the assignment/status predicates, so every denied case
    # reaches the route as an empty result.
    operation.execute.return_value = SimpleNamespace(data=[])

    event_id = stored["id"] if stored else EVENT_B
    response = client.get(f"/events/support-assigned/{event_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}


# --- TC-EVENTS-111 -------------------------------------------------------
@pytest.mark.parametrize(
    "role",
    ["event_coordinator", "event_organiser", "venue_staff", "attendee", "unknown"],
)
@pytest.mark.parametrize("path", ["/events/support-assigned", f"/events/support-assigned/{EVENT_ID}"])
def test_support_assignment_routes_reject_other_roles(client, db, auth, role, path):
    authenticate(client, auth, fake_user(role=role))

    response = client.get(path)

    assert response.status_code == 403
    db.schema.assert_not_called()


@pytest.mark.parametrize("path", ["/events/support-assigned", f"/events/support-assigned/{EVENT_ID}"])
def test_support_assignment_routes_require_a_session(client, db, path):
    response = client.get(path)

    assert response.status_code == 401
    db.schema.assert_not_called()
