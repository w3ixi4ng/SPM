"""S-51: the registrations service records who holds a place.

TC-REGISTRATIONS-001..005; S-48 adds 006..007; S-50 adds 008..013 and
routes 002..004 through the capped insert; S-52 adds 014..015; S-53 adds
016..019, withdrawing; S-55 adds 020..026, offering a freed place, and
retires 017; S-58 adds 027, listing withdrawals.
"""

from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

from .conftest import ATTENDEE_A, ATTENDEE_B, EVENT_ID, REGISTRATION_ID, registration_row


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
        # S-55: set once a freed place is held for this entry.
        "offered_at": None,
    }
    row.update(changes)
    return row


def _waiting(db):
    """S-52: an event's waiting list is ordered by join time, then id."""
    return _listed(db).order.return_value


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
    _waiting(db).execute.return_value = SimpleNamespace(data=rows)
    response = client.get(f"/registrations/waiting-list/events/{EVENT_ID}")
    assert response.status_code == 200
    assert response.json() == rows
    db.schema.return_value.table.assert_called_with("waiting_list")
    select = db.schema.return_value.table.return_value.select
    select.return_value.eq.assert_called_with("event_id", EVENT_ID)
    select.return_value.eq.return_value.order.assert_called_with("created_at")

    _waiting(db).execute.return_value = SimpleNamespace(data=[])
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


C_ATTENDEE = "55555555-5555-4555-8555-555555555555"


# --- TC-REGISTRATIONS-014 -------------------------------------------------
def test_an_attendees_waiting_list_entries(client, db):
    rows = [
        waiting_row(created_at="2026-11-05T04:00:00Z"),
        waiting_row(
            id="99999999-9999-4999-8999-999999999999",
            event_id=OTHER_EVENT,
            created_at="2026-11-06T04:00:00Z",
        ),
    ]
    _listed(db).execute.return_value = SimpleNamespace(data=rows)
    response = client.get(f"/registrations/waiting-list/attendees/{ATTENDEE_B}")
    assert response.status_code == 200
    assert response.json() == rows
    db.schema.assert_called_with("registrations")
    db.schema.return_value.table.assert_called_with("waiting_list")
    select = db.schema.return_value.table.return_value.select
    select.return_value.eq.assert_called_with("attendee_id", ATTENDEE_B)
    select.return_value.eq.return_value.order.assert_called_with("created_at")

    _listed(db).execute.return_value = SimpleNamespace(data=[])
    response = client.get(f"/registrations/waiting-list/attendees/{ATTENDEE_A}")
    assert response.status_code == 200
    assert response.json() == []


# --- TC-REGISTRATIONS-015 -------------------------------------------------
def test_an_events_waiting_list_is_first_come_first_served(client, db):
    rows = [
        waiting_row(),
        waiting_row(id="99999999-9999-4999-8999-999999999999", attendee_id=C_ATTENDEE),
    ]
    _waiting(db).execute.return_value = SimpleNamespace(data=rows)
    response = client.get(f"/registrations/waiting-list/events/{EVENT_ID}")
    assert response.status_code == 200
    assert response.json() == rows
    select = db.schema.return_value.table.return_value.select
    select.return_value.eq.assert_called_with("event_id", EVENT_ID)
    by_join_time = select.return_value.eq.return_value.order
    by_join_time.assert_called_once_with("created_at")
    by_join_time.return_value.order.assert_called_once_with("id")


WITHDRAWAL = {"event_id": EVENT_ID, "attendee_id": ATTENDEE_A, "capacity": 2}


def _withdrawn(db, offered=None):
    """S-53: registrations.withdraw answers one jsonb object, not a list.
    S-55: naming the entry the freed place is offered to."""
    _register(db).return_value.execute.return_value = SimpleNamespace(
        data={"withdrawn": registration_row(), "offered": offered}
    )


# --- TC-REGISTRATIONS-016 -------------------------------------------------
def test_an_attendee_withdraws_and_no_one_is_waiting(client, db):
    _withdrawn(db)

    response = client.post("/registrations/withdrawals", json=WITHDRAWAL)

    assert response.status_code == 200
    assert response.json() == {"withdrawn": registration_row(), "offered": None}
    db.schema.assert_called_with("registrations")
    _register(db).assert_called_once_with(
        "withdraw", {"p_event_id": EVENT_ID, "p_attendee_id": ATTENDEE_A, "p_capacity": 2}
    )
    db.schema.return_value.table.assert_not_called()


# --- TC-REGISTRATIONS-018 -------------------------------------------------
def test_withdrawing_a_place_that_isnt_held(client, db):
    _register(db).return_value.execute.side_effect = APIError(
        {"code": "SP053", "message": "not registered"}
    )

    response = client.post(
        "/registrations/withdrawals", json={**WITHDRAWAL, "attendee_id": ATTENDEE_B}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "You're not registered for this event."}


# --- TC-REGISTRATIONS-019 -------------------------------------------------
@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"event_id": EVENT_ID, "attendee_id": ATTENDEE_A}, "capacity"),
        ({**WITHDRAWAL, "capacity": -1}, "capacity"),
        ({**WITHDRAWAL, "event_id": "nope"}, "event_id"),
        ({**WITHDRAWAL, "x": 1}, "x"),
    ],
)
def test_a_malformed_withdrawal_is_refused(client, db, body, field):
    response = client.post("/registrations/withdrawals", json=body)

    assert response.status_code == 422
    assert field in response.json()["errors"]
    _register(db).assert_not_called()


def test_a_withdrawal_with_no_free_place_is_accepted(client, db):
    _withdrawn(db)

    response = client.post("/registrations/withdrawals", json={**WITHDRAWAL, "capacity": 0})

    assert response.status_code == 200
    assert _register(db).call_args.args[1]["p_capacity"] == 0


def test_a_withdrawal_storage_cant_record(client, db):
    _register(db).return_value.execute.side_effect = APIError(
        {"code": "XX000", "message": "boom"}
    )

    response = client.post("/registrations/withdrawals", json=WITHDRAWAL)

    assert response.status_code == 500
    assert response.json() == {"detail": "Registration storage unavailable"}


# --- S-55 -----------------------------------------------------------------
OFFERED_B = "77777777-7777-4777-8777-777777777777"
OFFERED_C = "88888888-8888-4888-8888-888888888888"
ACCEPTANCE = {"event_id": EVENT_ID, "attendee_id": ATTENDEE_B}
DECLINE = {"event_id": EVENT_ID, "attendee_id": ATTENDEE_B, "capacity": 2}
NO_OFFER = {"detail": "You don't have a place on offer for this event."}


def _offered_b(**changes):
    return waiting_row(
        id=OFFERED_B,
        created_at="2026-11-04T04:00:00+00:00",
        offered_at="2026-11-06T04:00:00+00:00",
        **changes,
    )


def _rpc_fails(db, code):
    _register(db).return_value.execute.side_effect = APIError({"code": code, "message": "x"})


# --- TC-REGISTRATIONS-020 -------------------------------------------------
def test_a_withdrawal_offers_the_freed_place_to_the_next_in_line(client, db):
    _withdrawn(db, _offered_b())

    response = client.post("/registrations/withdrawals", json=WITHDRAWAL)

    assert response.status_code == 200
    body = response.json()
    assert body["withdrawn"] == registration_row()
    assert body["offered"] == {
        "id": OFFERED_B,
        "event_id": EVENT_ID,
        "attendee_id": ATTENDEE_B,
        "created_at": "2026-11-04T04:00:00Z",
        "offered_at": "2026-11-06T04:00:00Z",
    }
    assert "promoted" not in body


# --- TC-REGISTRATIONS-021 -------------------------------------------------
def test_the_invited_attendee_accepts_the_place(client, db):
    _register(db).return_value.execute.return_value = SimpleNamespace(
        data=[registration_row(attendee_id=ATTENDEE_B, created_at="2026-11-07T04:00:00+00:00")]
    )

    response = client.post("/registrations/offers/acceptances", json=ACCEPTANCE)

    assert response.status_code == 201
    assert response.json() == registration_row(
        attendee_id=ATTENDEE_B, created_at="2026-11-07T04:00:00Z"
    )
    db.schema.assert_called_with("registrations")
    _register(db).assert_called_once_with(
        "accept_offer", {"p_event_id": EVENT_ID, "p_attendee_id": ATTENDEE_B}
    )
    db.schema.return_value.table.assert_not_called()


# --- TC-REGISTRATIONS-022 -------------------------------------------------
def test_accepting_without_an_open_offer(client, db):
    _rpc_fails(db, "SP055")

    response = client.post(
        "/registrations/offers/acceptances", json={**ACCEPTANCE, "attendee_id": C_ATTENDEE}
    )

    assert response.status_code == 404
    assert response.json() == NO_OFFER


# --- TC-REGISTRATIONS-023 -------------------------------------------------
def test_declining_passes_the_place_to_the_next_in_line(client, db):
    offered_c = waiting_row(
        id=OFFERED_C, attendee_id=C_ATTENDEE, offered_at="2026-11-07T04:00:00+00:00"
    )
    _register(db).return_value.execute.return_value = SimpleNamespace(
        data={"declined": _offered_b(), "offered": offered_c}
    )

    response = client.post("/registrations/offers/declines", json=DECLINE)

    assert response.status_code == 200
    assert response.json()["declined"]["attendee_id"] == ATTENDEE_B
    assert response.json()["offered"]["attendee_id"] == C_ATTENDEE
    assert response.json()["offered"]["offered_at"] == "2026-11-07T04:00:00Z"
    _register(db).assert_called_once_with(
        "decline_offer", {"p_event_id": EVENT_ID, "p_attendee_id": ATTENDEE_B, "p_capacity": 2}
    )


def test_declining_with_no_one_else_waiting(client, db):
    _register(db).return_value.execute.return_value = SimpleNamespace(
        data={"declined": _offered_b(), "offered": None}
    )

    response = client.post("/registrations/offers/declines", json=DECLINE)

    assert response.status_code == 200
    assert response.json()["declined"]["attendee_id"] == ATTENDEE_B
    assert response.json()["offered"] is None


# --- TC-REGISTRATIONS-024 -------------------------------------------------
def test_declining_without_an_open_offer(client, db):
    _rpc_fails(db, "SP055")

    response = client.post(
        "/registrations/offers/declines", json={**DECLINE, "attendee_id": C_ATTENDEE}
    )

    assert response.status_code == 404
    assert response.json() == NO_OFFER


# --- TC-REGISTRATIONS-025 -------------------------------------------------
@pytest.mark.parametrize(
    ("path", "body", "field"),
    [
        ("acceptances", {**ACCEPTANCE, "event_id": "nope"}, "event_id"),
        ("acceptances", {**ACCEPTANCE, "x": 1}, "x"),
        ("declines", {"event_id": EVENT_ID, "attendee_id": ATTENDEE_B}, "capacity"),
        ("declines", {**DECLINE, "capacity": -1}, "capacity"),
    ],
)
def test_a_malformed_accept_or_decline_is_refused(client, db, path, body, field):
    response = client.post(f"/registrations/offers/{path}", json=body)

    assert response.status_code == 422
    assert field in response.json()["errors"]
    _register(db).assert_not_called()


def test_a_decline_with_no_free_place_is_accepted(client, db):
    _register(db).return_value.execute.return_value = SimpleNamespace(
        data={"declined": _offered_b(), "offered": None}
    )

    response = client.post("/registrations/offers/declines", json={**DECLINE, "capacity": 0})

    assert response.status_code == 200
    assert _register(db).call_args.args[1]["p_capacity"] == 0


@pytest.mark.parametrize(("path", "body"), [("acceptances", ACCEPTANCE), ("declines", DECLINE)])
def test_an_accept_or_decline_storage_cant_record(client, db, path, body):
    _rpc_fails(db, "XX000")

    response = client.post(f"/registrations/offers/{path}", json=body)

    assert response.status_code == 500
    assert response.json() == {"detail": "Registration storage unavailable"}


# --- TC-REGISTRATIONS-026 -------------------------------------------------
def test_waiting_list_reads_say_who_holds_an_offer(client, db):
    held = _offered_b()
    waiting = waiting_row(id=OFFERED_C, attendee_id=C_ATTENDEE)

    _waiting(db).execute.return_value = SimpleNamespace(data=[held, waiting])
    listed = client.get(f"/registrations/waiting-list/events/{EVENT_ID}")
    assert listed.status_code == 200
    assert [row["offered_at"] for row in listed.json()] == ["2026-11-06T04:00:00Z", None]
    assert [row["attendee_id"] for row in listed.json()] == [ATTENDEE_B, C_ATTENDEE]

    _listed(db).execute.return_value = SimpleNamespace(data=[held])
    mine = client.get(f"/registrations/waiting-list/attendees/{ATTENDEE_B}")
    assert mine.status_code == 200
    assert mine.json()[0]["offered_at"] == "2026-11-06T04:00:00Z"

    _lookup(db).execute.return_value = SimpleNamespace(data=[waiting])
    entry = client.get(f"/registrations/waiting-list/events/{EVENT_ID}/attendees/{C_ATTENDEE}")
    assert entry.status_code == 200
    assert entry.json()["offered_at"] is None


# --- TC-REGISTRATIONS-027 -------------------------------------------------
def test_an_attendees_withdrawals_are_listed(client, db):
    withdrawal = {
        "id": REGISTRATION_ID,
        "event_id": EVENT_ID,
        "attendee_id": ATTENDEE_A,
        "withdrawn_at": "2026-10-28T02:15:00+00:00",
    }
    _listed(db).execute.return_value = SimpleNamespace(data=[withdrawal])

    response = client.get(f"/registrations/withdrawals/attendees/{ATTENDEE_A}")

    assert response.status_code == 200
    assert response.json() == [{**withdrawal, "withdrawn_at": "2026-10-28T02:15:00Z"}]
    db.schema.assert_called_with("registrations")
    db.schema.return_value.table.assert_called_with("withdrawals")
    db.schema.return_value.table.return_value.select.return_value.eq.assert_called_with(
        "attendee_id", ATTENDEE_A
    )
    _listed_order = db.schema.return_value.table.return_value.select.return_value.eq.return_value.order
    _listed_order.assert_called_with("withdrawn_at")

    _listed(db).execute.return_value = SimpleNamespace(data=[])
    empty = client.get(f"/registrations/withdrawals/attendees/{ATTENDEE_A}")
    assert empty.status_code == 200
    assert empty.json() == []

    _listed(db).execute.side_effect = RuntimeError("connection reset")
    failed = client.get(f"/registrations/withdrawals/attendees/{ATTENDEE_A}")
    assert failed.status_code == 500
    assert failed.json() == {"detail": "Registration storage unavailable"}

    assert client.get("/registrations/withdrawals/attendees/not-a-uuid").status_code == 422
