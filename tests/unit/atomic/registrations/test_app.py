"""S-51: the registrations service records who holds a place.

TC-REGISTRATIONS-001..005; S-48 adds 006..007; S-50 adds 008..013 and
routes 002..004 through the capped insert.
"""

from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

from .conftest import ATTENDEE_A, ATTENDEE_B, EVENT_ID, registration_row


def _insert(db):
    return db.schema.return_value.table.return_value.insert


def _register(db):
    """S-50: a place is taken through registrations.register, not an insert."""
    return db.schema.return_value.rpc


def _lookup(db):
    return db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value


# --- TC-REGISTRATIONS-001 -------------------------------------------------
def test_health_reports_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- TC-REGISTRATIONS-002 -------------------------------------------------
def test_an_attendee_takes_a_place(client, db):
    _register(db).return_value.execute.return_value = SimpleNamespace(data=[registration_row()])

    response = client.post(
        "/registrations",
        json={"event_id": EVENT_ID, "attendee_id": ATTENDEE_A, "capacity": 50},
    )

    assert response.status_code == 201
    assert response.json() == registration_row()
    db.schema.assert_called_with("registrations")


# --- TC-REGISTRATIONS-003 -------------------------------------------------
def test_one_account_registers_once(client, db):
    _register(db).return_value.execute.side_effect = APIError(
        {"code": "23505", "message": "duplicate key value violates unique constraint"}
    )

    response = client.post(
        "/registrations",
        json={"event_id": EVENT_ID, "attendee_id": ATTENDEE_A, "capacity": 50},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "You're already registered for this event."


# --- TC-REGISTRATIONS-004 -------------------------------------------------
@pytest.mark.parametrize(
    "body",
    [
        {"event_id": EVENT_ID, "capacity": 50},
        {"event_id": "not-a-uuid", "attendee_id": ATTENDEE_A, "capacity": 50},
        {"event_id": EVENT_ID, "attendee_id": ATTENDEE_A, "capacity": 50, "id": EVENT_ID},
    ],
)
def test_malformed_registration_requests(client, db, body):
    response = client.post("/registrations", json=body)

    assert response.status_code == 422
    _register(db).assert_not_called()


# --- TC-REGISTRATIONS-005 -------------------------------------------------
def test_reading_whether_an_attendee_holds_a_place(client, db):
    _lookup(db).execute.return_value = SimpleNamespace(data=[registration_row()])
    response = client.get(f"/registrations/events/{EVENT_ID}/attendees/{ATTENDEE_A}")
    assert response.status_code == 200
    assert response.json() == registration_row()
    select = db.schema.return_value.table.return_value.select
    select.return_value.eq.assert_called_with("event_id", EVENT_ID)
    select.return_value.eq.return_value.eq.assert_called_with("attendee_id", ATTENDEE_A)

    _lookup(db).execute.return_value = SimpleNamespace(data=[])
    response = client.get(f"/registrations/events/{EVENT_ID}/attendees/{ATTENDEE_B}")
    assert response.status_code == 404
    assert response.json()["detail"] == "You're not registered for this event."
    select.return_value.eq.return_value.eq.assert_called_with("attendee_id", ATTENDEE_B)


def _listed(db):
    return db.schema.return_value.table.return_value.select.return_value.eq.return_value.order.return_value


OTHER_EVENT = "66666666-6666-4666-8666-666666666666"


# --- TC-REGISTRATIONS-006 -------------------------------------------------
def test_every_place_at_one_event(client, db):
    rows = [
        registration_row(),
        registration_row(
            id="77777777-7777-4777-8777-777777777777",
            attendee_id=ATTENDEE_B,
            created_at="2026-11-06T04:00:00Z",
        ),
    ]
    _listed(db).execute.return_value = SimpleNamespace(data=rows)
    response = client.get(f"/registrations/events/{EVENT_ID}")
    assert response.status_code == 200
    assert response.json() == rows
    select = db.schema.return_value.table.return_value.select
    select.return_value.eq.assert_called_with("event_id", EVENT_ID)
    select.return_value.eq.return_value.order.assert_called_with("created_at")

    _listed(db).execute.return_value = SimpleNamespace(data=[])
    response = client.get(f"/registrations/events/{OTHER_EVENT}")
    assert response.status_code == 200
    assert response.json() == []


def test_listing_an_events_places_needs_a_uuid(client, db):
    response = client.get("/registrations/events/not-a-uuid")

    assert response.status_code == 422
    db.schema.assert_not_called()


# --- TC-REGISTRATIONS-007 -------------------------------------------------
def test_every_place_one_attendee_holds(client, db):
    rows = [
        registration_row(),
        registration_row(id="77777777-7777-4777-8777-777777777777", event_id=OTHER_EVENT),
    ]
    _listed(db).execute.return_value = SimpleNamespace(data=rows)
    response = client.get(f"/registrations/attendees/{ATTENDEE_A}")
    assert response.status_code == 200
    assert response.json() == rows
    select = db.schema.return_value.table.return_value.select
    select.return_value.eq.assert_called_with("attendee_id", ATTENDEE_A)
    select.return_value.eq.return_value.order.assert_called_with("created_at")

    _listed(db).execute.return_value = SimpleNamespace(data=[])
    response = client.get(f"/registrations/attendees/{ATTENDEE_B}")
    assert response.status_code == 200
    assert response.json() == []


def test_listing_an_attendees_places_needs_a_uuid(client, db):
    response = client.get("/registrations/attendees/not-a-uuid")

    assert response.status_code == 422
    db.schema.assert_not_called()


# --- TC-REGISTRATIONS-008 -------------------------------------------------
def test_a_place_is_taken_while_the_event_has_room(client, db):
    _register(db).return_value.execute.return_value = SimpleNamespace(data=[registration_row()])

    response = client.post(
        "/registrations",
        json={"event_id": EVENT_ID, "attendee_id": ATTENDEE_A, "capacity": 50},
    )

    assert response.status_code == 201
    assert response.json() == registration_row()
    db.schema.assert_called_with("registrations")
    _register(db).assert_called_once_with(
        "register", {"p_event_id": EVENT_ID, "p_attendee_id": ATTENDEE_A, "p_capacity": 50}
    )
    _insert(db).assert_not_called()


# --- TC-REGISTRATIONS-009 -------------------------------------------------
def test_a_full_event_refuses_the_place(client, db):
    _register(db).return_value.execute.side_effect = APIError(
        {"code": "SP050", "message": "event full"}
    )

    response = client.post(
        "/registrations",
        json={"event_id": EVENT_ID, "attendee_id": ATTENDEE_B, "capacity": 1},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "This event is full."}


# --- TC-REGISTRATIONS-010 -------------------------------------------------
@pytest.mark.parametrize("capacity", [None, 0, -5])
def test_a_registration_without_a_usable_capacity_is_rejected(client, db, capacity):
    body = {"event_id": EVENT_ID, "attendee_id": ATTENDEE_A}
    if capacity is not None:
        body["capacity"] = capacity

    response = client.post("/registrations", json=body)

    assert response.status_code == 422
    assert "capacity" in response.json()["errors"]
    _register(db).assert_not_called()


WAITING_ID = "88888888-8888-4888-8888-888888888888"


def waiting_row(**changes):
    row = {
        "id": WAITING_ID,
        "event_id": EVENT_ID,
        "attendee_id": ATTENDEE_B,
        "created_at": "2026-11-02T02:00:00Z",
    }
    row.update(changes)
    return row


# --- TC-REGISTRATIONS-011 -------------------------------------------------
def test_joining_the_waiting_list_once(client, db):
    _insert(db).return_value.execute.side_effect = [
        SimpleNamespace(data=[waiting_row()]),
        APIError({"code": "23505", "message": "duplicate key value violates unique constraint"}),
    ]
    body = {"event_id": EVENT_ID, "attendee_id": ATTENDEE_B}

    first = client.post("/registrations/waiting-list", json=body)
    second = client.post("/registrations/waiting-list", json=body)

    assert first.status_code == 201
    assert first.json() == waiting_row()
    db.schema.assert_called_with("registrations")
    db.schema.return_value.table.assert_called_with("waiting_list")
    _insert(db).assert_called_with(body)
    assert second.status_code == 409
    assert second.json() == {"detail": "You're already on the waiting list for this event."}


# --- TC-REGISTRATIONS-012 -------------------------------------------------
def test_an_events_waiting_list_in_join_order(client, db):
    rows = [
        waiting_row(),
        waiting_row(
            id="99999999-9999-4999-8999-999999999999",
            attendee_id=ATTENDEE_A,
            created_at="2026-11-02T03:00:00Z",
        ),
    ]
    _listed(db).execute.return_value = SimpleNamespace(data=rows)
    response = client.get(f"/registrations/waiting-list/events/{EVENT_ID}")
    assert response.status_code == 200
    assert response.json() == rows
    db.schema.return_value.table.assert_called_with("waiting_list")
    select = db.schema.return_value.table.return_value.select
    select.return_value.eq.assert_called_with("event_id", EVENT_ID)
    select.return_value.eq.return_value.order.assert_called_with("created_at")

    _listed(db).execute.return_value = SimpleNamespace(data=[])
    response = client.get(f"/registrations/waiting-list/events/{OTHER_EVENT}")
    assert response.status_code == 200
    assert response.json() == []


# --- TC-REGISTRATIONS-013 -------------------------------------------------
def test_one_attendees_waiting_list_entry(client, db):
    _lookup(db).execute.return_value = SimpleNamespace(data=[waiting_row()])
    response = client.get(f"/registrations/waiting-list/events/{EVENT_ID}/attendees/{ATTENDEE_B}")
    assert response.status_code == 200
    assert response.json() == waiting_row()
    db.schema.return_value.table.assert_called_with("waiting_list")

    _lookup(db).execute.return_value = SimpleNamespace(data=[])
    response = client.get(f"/registrations/waiting-list/events/{EVENT_ID}/attendees/{ATTENDEE_A}")
    assert response.status_code == 404
    assert response.json() == {"detail": "You're not on the waiting list for this event."}
