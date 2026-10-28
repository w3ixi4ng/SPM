"""S-50: the Organiser closes registration early, and reopens it.

TC-EVENTS-180..183. The close decision is the owning Organiser's alone, and
only applies to a confirmed event that takes registrations.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from .conftest import (
    EVENT_ID,
    ORGANISER_ID,
    OTHER_USER_ID,
    authenticate,
    event_row,
    fake_user,
    on_owned_select,
    on_update_owned,
)

CLOSED_AT = "2026-11-03T06:15:00+00:00"
NOT_APPLICABLE = (
    "Registration can only be closed or reopened on a confirmed event that takes registrations."
)
CLOSURE = f"/events/{EVENT_ID}/registration-closure"


def _confirmed(**changes):
    """C: confirmed, registration on, 50 expected, open."""
    return event_row(
        **{
            "status": "confirmed",
            "name": "Alumni networking evening",
            "expected_attendance": 50,
            "registration_required": True,
            "registration_opens_at": "2026-11-01T09:00:00",
            "registration_closes_at": "2026-11-15T18:00:00",
            "registration_closed_at": None,
            **changes,
        }
    )


def _update(db):
    return db.schema.return_value.table.return_value.update


# --- TC-EVENTS-180 --------------------------------------------------------
def test_the_organiser_closes_registration_early(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [_confirmed()])
    on_update_owned(db, [_confirmed(registration_closed_at=CLOSED_AT)])
    before = datetime.now(timezone.utc)

    response = client.put(CLOSURE)

    assert response.status_code == 200
    assert response.json()["registration_closed_at"] is not None
    _update(db).assert_called_once()
    written = _update(db).call_args.args[0]
    assert set(written) == {"registration_closed_at"}
    stamp = datetime.fromisoformat(written["registration_closed_at"])
    assert before <= stamp <= datetime.now(timezone.utc)
    _update(db).return_value.eq.assert_called_with("id", EVENT_ID)
    _update(db).return_value.eq.return_value.eq.assert_called_with("organiser_id", ORGANISER_ID)


def test_closing_an_already_closed_event_keeps_the_first_time(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [_confirmed(registration_closed_at=CLOSED_AT)])

    response = client.put(CLOSURE)

    assert response.status_code == 200
    assert response.json()["registration_closed_at"].startswith("2026-11-03T06:15:00")
    _update(db).assert_not_called()


# --- TC-EVENTS-181 --------------------------------------------------------
def test_the_organiser_reopens_registration(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [_confirmed(registration_closed_at=CLOSED_AT)])
    on_update_owned(db, [_confirmed()])

    response = client.delete(CLOSURE)

    assert response.status_code == 200
    assert response.json()["registration_closed_at"] is None
    _update(db).assert_called_once_with({"registration_closed_at": None})
    _update(db).return_value.eq.assert_called_with("id", EVENT_ID)
    _update(db).return_value.eq.return_value.eq.assert_called_with("organiser_id", ORGANISER_ID)


# --- TC-EVENTS-182 --------------------------------------------------------
@pytest.mark.parametrize("method", ["put", "delete"])
def test_closing_needs_a_session(client, db, method):
    response = getattr(client, method)(CLOSURE)

    assert response.status_code == 401
    _update(db).assert_not_called()


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize("role", ["attendee", "event_coordinator"])
def test_only_organisers_close_registration(client, db, auth, method, role):
    authenticate(client, auth, fake_user(OTHER_USER_ID, role))

    response = getattr(client, method)(CLOSURE)

    assert response.status_code == 403
    _update(db).assert_not_called()


@pytest.mark.parametrize("method", ["put", "delete"])
def test_another_organisers_event_is_not_found(client, db, auth, method):
    authenticate(client, auth, fake_user(OTHER_USER_ID))
    on_owned_select(db, [])

    response = getattr(client, method)(CLOSURE)

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    _update(db).assert_not_called()


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize(
    "stored",
    [
        {"status": "planning"},
        {
            "registration_required": False,
            "registration_opens_at": None,
            "registration_closes_at": None,
        },
    ],
    ids=["not-confirmed", "registration-off"],
)
def test_closing_applies_only_where_registration_exists(client, db, auth, method, stored):
    authenticate(client, auth)
    on_owned_select(db, [_confirmed(registration_closed_at=CLOSED_AT, **stored)])

    response = getattr(client, method)(CLOSURE)

    assert response.status_code == 409
    assert response.json()["detail"] == NOT_APPLICABLE
    _update(db).assert_not_called()


# --- TC-EVENTS-183 --------------------------------------------------------
def test_the_published_read_carries_the_cap_and_the_close_decision(client, db):
    row = {
        "id": EVENT_ID,
        "name": "Alumni networking evening",
        "purpose": "Reconnect alumni with current students",
        "start_date": "2026-11-20",
        "start_time": "18:00:00",
        "end_date": "2026-11-20",
        "end_time": "21:00:00",
        "registration_required": True,
        "registration_opens_at": "2026-11-01T09:00:00",
        "registration_closes_at": "2026-11-15T18:00:00",
        "expected_attendance": 50,
        "registration_closed_at": CLOSED_AT,
    }
    select = db.schema.return_value.table.return_value.select
    select.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[row]
    )
    select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value = (
        SimpleNamespace(data=[row])
    )

    single = client.get(f"/internal/events/published/{EVENT_ID}")
    listed = client.get("/internal/events/published")

    for body in (single.json(), listed.json()[0]):
        assert body["expected_attendance"] == 50
        assert datetime.fromisoformat(body["registration_closed_at"]) == datetime.fromisoformat(
            CLOSED_AT
        )
        assert "organiser_id" not in body
    selected = set(select.call_args.args[0].split(","))
    assert {"expected_attendance", "registration_closed_at"} <= selected
    assert "organiser_id" not in selected
