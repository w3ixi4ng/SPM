"""S-28: TC-VENUES-031 and TC-VENUES-032."""
import pytest

from .conftest import VENUE_ID, MISSING_ID, authenticate, fake_user, returns, venue_row


def operation(db):
    return db.schema.return_value.table.return_value.update.return_value.eq.return_value


@pytest.mark.parametrize("changes", [
    {"capacity": 100}, {"location": "Block B"}, {"facilities": []},
    {"accessibility": []},
    {"location": "Block B", "capacity": 100, "facilities": ["wifi"], "accessibility": ["lift"]},
])
def test_staff_update_preserves_omitted_fields(client, db, auth, changes):
    authenticate(client, auth, fake_user(user_id=MISSING_ID))
    saved = venue_row(**changes)
    returns(operation(db), [saved])
    response = client.patch(f"/venues/{VENUE_ID}", json=changes)
    assert response.status_code == 200
    assert response.json()["created_by"] == venue_row()["created_by"]
    table = db.schema.return_value.table.return_value
    db.schema.assert_called_once_with("venues")
    db.schema.return_value.table.assert_called_once_with("venues")
    table.update.assert_called_once_with(changes)
    table.update.return_value.eq.assert_called_once_with("id", VENUE_ID)
    table.insert.assert_not_called()
    table.delete.assert_not_called()
    for field in changes:
        assert response.json()[field] == changes[field]


def test_update_normalises_values(client, db, auth):
    authenticate(client, auth)
    returns(operation(db), [venue_row(location="Block B", facilities=["wifi"])])
    response = client.patch(f"/venues/{VENUE_ID}", json={"location": " Block B ", "facilities": ["wifi", "wifi"]})
    assert response.status_code == 200
    db.schema.return_value.table.return_value.update.assert_called_once_with({"location": "Block B", "facilities": ["wifi"]})


@pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "attendee", "technical_support", "unknown", None])
def test_update_rejects_other_roles(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))
    assert client.patch(f"/venues/{VENUE_ID}", json={"capacity": 100}).status_code == 403
    db.schema.assert_not_called()


def test_update_requires_session(client, db):
    assert client.patch(f"/venues/{VENUE_ID}", json={"capacity": 100}).status_code == 401
    db.schema.assert_not_called()


@pytest.mark.parametrize("payload", [
    {}, {"location": " "}, {"location": None}, {"capacity": None},
    {"capacity": 0}, {"capacity": -1}, {"capacity": 1.5}, {"capacity": True},
    {"capacity": "100"}, {"capacity": 2147483648},
    {"facilities": None}, {"accessibility": None},
    {"facilities": ["unknown"]}, {"accessibility": ["unknown"]},
    *[{field: value} for field, value in {
        "id": VENUE_ID, "created_by": MISSING_ID, "created_at": "2026-01-01",
        "name": "Changed", "description": "Changed", "room_layouts": ["theatre"],
        "operating_hours": [], "availability": True, "unexpected": 1,
    }.items()],
])
def test_update_rejects_invalid_and_protected_fields(client, db, auth, payload):
    authenticate(client, auth)
    response = client.patch(f"/venues/{VENUE_ID}", json=payload)
    assert response.status_code == 422
    assert response.json()["errors"]
    db.schema.assert_not_called()


def test_update_missing_and_bad_id(client, db, auth):
    authenticate(client, auth)
    returns(operation(db), [])
    response = client.patch(f"/venues/{MISSING_ID}", json={"capacity": 1})
    assert response.status_code == 404
    assert response.json() == {"detail": "Venue not found"}
    assert client.patch("/venues/not-a-uuid", json={"capacity": 1}).status_code == 422


def test_update_storage_error_is_safe(client, db, auth):
    authenticate(client, auth)
    operation(db).execute.side_effect = RuntimeError("private database detail")
    response = client.patch(f"/venues/{VENUE_ID}", json={"capacity": 1})
    assert response.status_code == 500
    assert response.json() == {"detail": "Venue storage unavailable"}
