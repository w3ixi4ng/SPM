"""S-28 reopened: Venue Staff edit opening hours. TC-VENUES-037 to 039."""
import pytest

from .conftest import VENUE_ID, authenticate, fake_user, returns, venue_row
from .test_update import operation

HOURS = [{"day": "thu", "open": "08:00", "close": "20:00"},
         {"day": "mon", "open": "10:00", "close": "16:00"}]
STORED = [{"day": "mon", "open": "10:00:00", "close": "16:00:00"},
          {"day": "thu", "open": "08:00:00", "close": "20:00:00"}]


# --- TC-VENUES-037 ---------------------------------------------------------
def test_venue_staff_replace_a_venues_opening_hours(client, db, auth):
    authenticate(client, auth)
    returns(operation(db), [venue_row(operating_hours=STORED)])

    response = client.patch(f"/venues/{VENUE_ID}", json={"operating_hours": HOURS})

    assert response.status_code == 200, response.text
    # The whole week is replaced, in week order, and nothing else is written.
    db.schema.return_value.table.return_value.update.assert_called_once_with({"operating_hours": STORED})
    assert response.json()["operating_hours"] == STORED


@pytest.mark.parametrize("role", ["event_coordinator", "attendee"])
def test_other_roles_cannot_change_hours(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))
    assert client.patch(f"/venues/{VENUE_ID}", json={"operating_hours": HOURS}).status_code == 403
    db.schema.assert_not_called()


def test_changing_hours_needs_a_session(client, db):
    assert client.patch(f"/venues/{VENUE_ID}", json={"operating_hours": HOURS}).status_code == 401
    db.schema.assert_not_called()


# --- TC-VENUES-038 ---------------------------------------------------------
@pytest.mark.parametrize("hours", [
    [], None,
    [{"day": "mon", "open": "18:00", "close": "09:00"}],
    [{"day": "mon", "open": "09:00", "close": "17:00"}, {"day": "mon", "open": "10:00", "close": "12:00"}],
    [{"day": "funday", "open": "09:00", "close": "17:00"}],
])
def test_opening_hours_are_checked_as_on_create(client, db, auth, hours):
    authenticate(client, auth)
    response = client.patch(f"/venues/{VENUE_ID}", json={"operating_hours": hours})
    assert response.status_code == 422
    assert response.json()["errors"]
    db.schema.assert_not_called()


# --- TC-VENUES-039 ---------------------------------------------------------
@pytest.mark.parametrize("payload", [{"room_layouts": ["banquet"]}, {"name": "New name"}])
def test_the_name_and_room_layouts_stay_protected(client, db, auth, payload):
    authenticate(client, auth)
    assert client.patch(f"/venues/{VENUE_ID}", json=payload).status_code == 422
    db.schema.assert_not_called()
