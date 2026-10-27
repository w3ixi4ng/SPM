"""S-51: the Organiser turns registration on or off and sets its period.

TC-EVENTS-163..174. Registration settings are validated on every organiser
payload, fixed once the request is submitted, and confirmed events'
public details are readable for the event_registrations composite.
"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from .conftest import (
    EVENT_ID,
    ORGANISER_ID,
    EventDraftCreate,
    EventSubmittedCreate,
    authenticate,
    event_row,
    on_insert,
    on_owned_select,
    on_update,
    on_update_owned,
)

# Event E starts 2026-11-20 at 18:00.
SUBMITTED = {
    "name": "Alumni networking evening",
    "purpose": "Reconnect alumni with current students",
    "start_date": "2026-11-20",
    "start_time": "18:00",
    "end_date": "2026-11-20",
    "end_time": "21:00",
    "expected_attendance": 120,
}
OPENS = "2026-11-01T09:00:00"
CLOSES = "2026-11-15T18:00:00"
REGISTRATION = {
    "registration_required": True,
    "registration_opens_at": OPENS,
    "registration_closes_at": CLOSES,
}
LOCKED = "Registration settings can only be changed while the request is a draft or returned."
LOCKED_STATUSES = [
    "submitted", "under_review", "planning", "pending_safety_check", "confirmed", "preparation",
]
PUBLIC_FIELDS = {
    "id", "name", "purpose", "start_date", "start_time", "end_date", "end_time",
    "registration_required", "registration_opens_at", "registration_closes_at",
    # S-50: for the composite only; it never passes the attendance figure on.
    "expected_attendance", "registration_closed_at",
}


def _messages(exc: ValidationError) -> dict[str, str]:
    return {".".join(str(p) for p in e["loc"]) or "body": e["msg"] for e in exc.errors()}


def _stored(status="draft", **changes):
    """E as the database returns it, registration on with the period."""
    return event_row(
        **{
            **SUBMITTED,
            "start_time": "18:00:00",
            "end_time": "21:00:00",
            **REGISTRATION,
            "status": status,
            **changes,
        }
    )


def _sent_update(db):
    return db.schema.return_value.table.return_value.update.call_args[0][0]


# --- TC-EVENTS-163 --------------------------------------------------------
def test_registration_is_off_unless_turned_on():
    draft = EventDraftCreate()
    submitted = EventSubmittedCreate(**SUBMITTED)

    for model in (draft, submitted):
        assert model.registration_required is False
        assert model.registration_opens_at is None
        assert model.registration_closes_at is None


# --- TC-EVENTS-164 --------------------------------------------------------
def test_a_draft_may_turn_registration_on_before_choosing_dates():
    EventDraftCreate(registration_required=True)
    EventDraftCreate(registration_required=True, registration_opens_at="2026-11-01T09:00")

    with pytest.raises(ValidationError) as exc:
        EventDraftCreate(
            registration_required=True,
            registration_opens_at="2026-11-01T09:00",
            registration_closes_at="2026-11-01T09:00",
        )
    assert "Registration must close after it opens." in str(exc.value)


# --- TC-EVENTS-165 --------------------------------------------------------
@pytest.mark.parametrize(
    "dates, missing",
    [
        ({}, {"registration_opens_at", "registration_closes_at"}),
        ({"registration_opens_at": "2026-11-01T09:00"}, {"registration_closes_at"}),
        ({"registration_closes_at": "2026-11-15T18:00"}, {"registration_opens_at"}),
    ],
)
def test_submitting_with_registration_on_needs_both_dates(dates, missing):
    with pytest.raises(ValidationError) as exc:
        EventSubmittedCreate(**SUBMITTED, registration_required=True, **dates)

    messages = _messages(exc.value)
    assert set(messages) == missing
    if "registration_opens_at" in missing:
        assert "Choose when registration opens." in messages["registration_opens_at"]
    if "registration_closes_at" in missing:
        assert "Choose when registration closes." in messages["registration_closes_at"]


# --- TC-EVENTS-166 --------------------------------------------------------
@pytest.mark.parametrize(
    "opens, closes, valid",
    [
        ("2026-11-15T18:00", "2026-11-15T18:00", False),
        ("2026-11-15T18:00", "2026-11-01T09:00", False),
        ("2026-11-15T18:00", "2026-11-15T18:01", True),
    ],
)
def test_registration_must_close_after_it_opens(opens, closes, valid):
    def build():
        return EventSubmittedCreate(
            **SUBMITTED,
            registration_required=True,
            registration_opens_at=opens,
            registration_closes_at=closes,
        )

    if valid:
        build()
    else:
        with pytest.raises(ValidationError) as exc:
            build()
        assert "Registration must close after it opens." in str(exc.value)


# --- TC-EVENTS-167 --------------------------------------------------------
@pytest.mark.parametrize(
    "closes, valid",
    [
        ("2026-11-20T18:00", False),
        ("2026-11-21T09:00", False),
        ("2026-11-20T17:59", True),
    ],
)
def test_registration_must_close_before_the_event_starts(closes, valid):
    def build():
        return EventSubmittedCreate(
            **SUBMITTED,
            registration_required=True,
            registration_opens_at="2026-11-01T09:00",
            registration_closes_at=closes,
        )

    if valid:
        build()
    else:
        with pytest.raises(ValidationError) as exc:
            build()
        assert "Registration must close before the event starts." in str(exc.value)


# --- TC-EVENTS-168 --------------------------------------------------------
def test_an_opening_date_that_has_already_passed_is_accepted():
    event = EventSubmittedCreate(
        **SUBMITTED,
        registration_required=True,
        registration_opens_at="2026-10-01T09:00",
        registration_closes_at="2026-11-15T18:00",
    )

    dumped = event.model_dump(mode="json")
    assert dumped["registration_opens_at"] == "2026-10-01T09:00:00"
    assert dumped["registration_closes_at"] == "2026-11-15T18:00:00"


# --- TC-EVENTS-169 --------------------------------------------------------
@pytest.mark.parametrize("model, body", [(EventSubmittedCreate, SUBMITTED), (EventDraftCreate, {})])
def test_turning_registration_off_clears_the_period(model, body):
    event = model(
        **body,
        registration_required=False,
        registration_opens_at="2026-11-15T18:00",
        registration_closes_at="2026-11-01T09:00",
    )

    assert event.registration_opens_at is None
    assert event.registration_closes_at is None


# --- TC-EVENTS-170 --------------------------------------------------------
@pytest.mark.parametrize("status", ["draft", "returned"])
def test_a_draft_or_returned_request_can_change_its_registration_settings(
    client, db, auth, status
):
    authenticate(client, auth)
    on_owned_select(db, [_stored(status)])
    on_update_owned(db, [_stored(status)])

    response = client.patch(
        f"/events/{EVENT_ID}", json={"registration_closes_at": "2026-11-16T12:00"}
    )
    assert response.status_code == 200
    assert _sent_update(db) == {"registration_closes_at": "2026-11-16T12:00:00"}

    response = client.patch(f"/events/{EVENT_ID}", json={"registration_required": False})
    assert response.status_code == 200
    assert _sent_update(db) == {
        "registration_required": False,
        "registration_opens_at": None,
        "registration_closes_at": None,
    }

    db.schema.return_value.table.return_value.update.reset_mock()
    response = client.patch(f"/events/{EVENT_ID}", json={"start_date": "2026-11-10"})
    assert response.status_code == 422
    assert "Registration must close before the event starts." in str(response.json()["errors"])
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-171 --------------------------------------------------------
@pytest.mark.parametrize("status", LOCKED_STATUSES)
@pytest.mark.parametrize(
    "change",
    [{"registration_required": False}, {"registration_opens_at": "2026-11-02T09:00"}],
)
def test_registration_settings_are_fixed_once_the_request_is_submitted(
    client, db, auth, status, change
):
    authenticate(client, auth)
    on_owned_select(db, [_stored(status)])

    response = client.patch(f"/events/{EVENT_ID}", json=change)

    assert response.status_code == 409
    assert response.json()["detail"] == LOCKED
    db.schema.return_value.table.return_value.update.assert_not_called()


def test_the_lock_covers_only_the_registration_fields(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [_stored("submitted")])
    on_update_owned(db, [_stored("submitted", name="Renamed")])

    response = client.patch(f"/events/{EVENT_ID}", json={"name": "Renamed"})

    assert response.status_code == 200
    assert _sent_update(db) == {"name": "Renamed"}


# --- TC-EVENTS-172 --------------------------------------------------------
def test_internal_routes_apply_the_same_rules(client, db):
    response = client.post(
        "/events/internal",
        json={
            **SUBMITTED,
            "organiser_id": ORGANISER_ID,
            "registration_required": True,
            "registration_opens_at": OPENS,
        },
    )
    assert response.status_code == 422
    assert "Choose when registration closes." in response.json()["errors"]["registration_closes_at"]

    on_owned_select(db, [event_row()])
    response = client.post(
        f"/events/{EVENT_ID}/submit/internal",
        json={
            **SUBMITTED,
            "organiser_id": ORGANISER_ID,
            "registration_required": True,
            "registration_opens_at": OPENS,
            "registration_closes_at": "2026-11-20T18:00",
        },
    )
    assert response.status_code == 422
    assert "Registration must close before the event starts." in response.json()["errors"]["body"]

    on_owned_select(db, [_stored("planning")])
    response = client.patch(
        f"/events/{EVENT_ID}/internal",
        json={"organiser_id": ORGANISER_ID, "registration_required": False},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == LOCKED
    db.schema.return_value.table.return_value.update.assert_not_called()

    on_insert(db, [_stored("submitted")])
    response = client.post(
        "/events/internal",
        json={**SUBMITTED, "organiser_id": ORGANISER_ID, **REGISTRATION},
    )
    assert response.status_code == 201
    inserted = db.schema.return_value.table.return_value.insert.call_args[0][0]
    assert {key: inserted[key] for key in REGISTRATION} == REGISTRATION


def test_submitting_carries_the_registration_settings(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row()])
    on_update(db, [_stored("submitted")])

    response = client.post(f"/events/{EVENT_ID}/submit", json={**SUBMITTED, **REGISTRATION})

    assert response.status_code == 200
    sent = _sent_update(db)
    assert {key: sent[key] for key in REGISTRATION} == REGISTRATION


# --- TC-EVENTS-173 --------------------------------------------------------
def _published(**changes):
    row = {
        "id": EVENT_ID,
        "name": SUBMITTED["name"],
        "purpose": SUBMITTED["purpose"],
        "start_date": "2026-11-20",
        "start_time": "18:00:00",
        "end_date": "2026-11-20",
        "end_time": "21:00:00",
        **REGISTRATION,
        "expected_attendance": 120,
        "registration_closed_at": None,
    }
    row.update(changes)
    return row


def test_published_events_list_only_confirmed_events_with_public_fields(client, db):
    table = db.schema.return_value.table.return_value
    listing = table.select.return_value.eq.return_value.order.return_value.order.return_value
    other = "44444444-4444-4444-8444-444444444444"
    listing.execute.return_value = SimpleNamespace(
        data=[
            _published(),
            _published(
                id=other,
                registration_required=False,
                registration_opens_at=None,
                registration_closes_at=None,
            ),
        ]
    )

    response = client.get("/internal/events/published")

    assert response.status_code == 200
    table.select.return_value.eq.assert_called_once_with("status", "confirmed")
    selected = set(table.select.call_args[0][0].split(","))
    assert selected == PUBLIC_FIELDS
    body = response.json()
    assert [set(item) for item in body] == [PUBLIC_FIELDS, PUBLIC_FIELDS]
    assert body[1]["registration_required"] is False


# --- TC-EVENTS-174 --------------------------------------------------------
def test_a_single_published_event_is_found_only_while_confirmed(client, db):
    table = db.schema.return_value.table.return_value
    single = table.select.return_value.eq.return_value.eq.return_value

    single.execute.return_value = SimpleNamespace(data=[_published()])
    response = client.get(f"/internal/events/published/{EVENT_ID}")
    assert response.status_code == 200
    assert set(response.json()) == PUBLIC_FIELDS
    assert response.json()["registration_opens_at"] == OPENS
    table.select.return_value.eq.return_value.eq.assert_called_with("status", "confirmed")

    # The status filter is the database's: any other status, or no event,
    # matches no row.
    single.execute.return_value = SimpleNamespace(data=[])
    response = client.get(f"/internal/events/published/{EVENT_ID}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found."
