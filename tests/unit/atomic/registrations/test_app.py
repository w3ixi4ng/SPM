"""S-51: the registrations service records who holds a place.

TC-REGISTRATIONS-001..005; S-48 adds 006..007.
"""

from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

from .conftest import ATTENDEE_A, ATTENDEE_B, EVENT_ID, registration_row


def _insert(db):
    return db.schema.return_value.table.return_value.insert


def _lookup(db):
    return db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value


# --- TC-REGISTRATIONS-001 -------------------------------------------------
def test_health_reports_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- TC-REGISTRATIONS-002 -------------------------------------------------
def test_an_attendee_takes_a_place(client, db):
    _insert(db).return_value.execute.return_value = SimpleNamespace(data=[registration_row()])

    response = client.post(
        "/registrations", json={"event_id": EVENT_ID, "attendee_id": ATTENDEE_A}
    )

    assert response.status_code == 201
    assert response.json() == registration_row()
    db.schema.assert_called_with("registrations")
    db.schema.return_value.table.assert_called_with("registrations")
    _insert(db).assert_called_once_with({"event_id": EVENT_ID, "attendee_id": ATTENDEE_A})


# --- TC-REGISTRATIONS-003 -------------------------------------------------
def test_one_account_registers_once(client, db):
    _insert(db).return_value.execute.side_effect = APIError(
        {"code": "23505", "message": "duplicate key value violates unique constraint"}
    )

    response = client.post(
        "/registrations", json={"event_id": EVENT_ID, "attendee_id": ATTENDEE_A}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "You're already registered for this event."


# --- TC-REGISTRATIONS-004 -------------------------------------------------
@pytest.mark.parametrize(
    "body",
    [
        {"event_id": EVENT_ID},
        {"event_id": "not-a-uuid", "attendee_id": ATTENDEE_A},
        {"event_id": EVENT_ID, "attendee_id": ATTENDEE_A, "id": EVENT_ID},
    ],
)
def test_malformed_registration_requests(client, db, body):
    response = client.post("/registrations", json=body)

    assert response.status_code == 422
    _insert(db).assert_not_called()


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
