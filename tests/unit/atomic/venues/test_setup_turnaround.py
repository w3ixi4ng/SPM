"""S-75: TC-VENUES-033 to TC-VENUES-036, setup and turnaround minutes."""
import pytest

from .conftest import (
    VALID_VENUE,
    VENUE_ID,
    authenticate,
    fake_user,
    get_operation,
    insert_operation,
    list_operation,
    returns,
    venue_row,
)


def update_operation(db):
    return db.schema.return_value.table.return_value.update.return_value.eq.return_value


# --- TC-VENUES-033 --------------------------------------------------------
def test_a_new_venue_records_its_setup_and_turnaround_times(client, db, auth):
    authenticate(client, auth)
    returns(insert_operation(db), [venue_row(setup_minutes=30, turnaround_minutes=45)])

    response = client.post("/venues", json={**VALID_VENUE, "setup_minutes": 30, "turnaround_minutes": 45})

    assert response.status_code == 201, response.text
    sent = db.schema.return_value.table.return_value.insert.call_args.args[0]
    assert (sent["setup_minutes"], sent["turnaround_minutes"]) == (30, 45)
    assert (response.json()["setup_minutes"], response.json()["turnaround_minutes"]) == (30, 45)


def test_a_new_venue_without_times_starts_at_zero(client, db, auth):
    authenticate(client, auth)
    returns(insert_operation(db), [venue_row()])

    response = client.post("/venues", json=VALID_VENUE)

    assert response.status_code == 201
    sent = db.schema.return_value.table.return_value.insert.call_args.args[0]
    assert (sent["setup_minutes"], sent["turnaround_minutes"]) == (0, 0)
    assert (response.json()["setup_minutes"], response.json()["turnaround_minutes"]) == (0, 0)


# --- TC-VENUES-034 --------------------------------------------------------
@pytest.mark.parametrize("field", ["setup_minutes", "turnaround_minutes"])
@pytest.mark.parametrize("value", [-1, 1.5, "30", None])
def test_times_cannot_be_negative_fractional_text_or_null(client, db, auth, field, value):
    authenticate(client, auth)

    created = client.post("/venues", json={**VALID_VENUE, field: value})
    updated = client.patch(f"/venues/{VENUE_ID}", json={field: value})

    for response in (created, updated):
        assert response.status_code == 422
        assert any(field in key for key in response.json()["errors"]), response.json()
    db.schema.assert_not_called()


@pytest.mark.parametrize("field", ["setup_minutes", "turnaround_minutes"])
@pytest.mark.parametrize("value", [0, 600])
def test_zero_and_large_times_are_accepted(client, db, auth, field, value):
    authenticate(client, auth)
    returns(insert_operation(db), [venue_row(**{field: value})])
    returns(update_operation(db), [venue_row(**{field: value})])

    assert client.post("/venues", json={**VALID_VENUE, field: value}).status_code == 201
    assert client.patch(f"/venues/{VENUE_ID}", json={field: value}).status_code == 200


# --- TC-VENUES-035 --------------------------------------------------------
@pytest.mark.parametrize("changes", [{"setup_minutes": 15}, {"turnaround_minutes": 0}])
def test_staff_update_one_time_leaving_the_rest(client, db, auth, changes):
    authenticate(client, auth)
    returns(update_operation(db), [venue_row(**changes)])

    response = client.patch(f"/venues/{VENUE_ID}", json=changes)

    assert response.status_code == 200, response.text
    db.schema.return_value.table.return_value.update.assert_called_once_with(changes)


@pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "technical_support"])
def test_only_venue_staff_update_the_times(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))

    response = client.patch(f"/venues/{VENUE_ID}", json={"setup_minutes": 15})

    assert response.status_code == 403
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-VENUES-036 --------------------------------------------------------
def test_every_venue_read_includes_both_times(client, db, auth):
    authenticate(client, auth)
    returns(list_operation(db), [venue_row(setup_minutes=30, turnaround_minutes=45)])
    returns(get_operation(db), [venue_row(setup_minutes=30, turnaround_minutes=45)])

    listed = client.get("/venues").json()[0]
    one = client.get(f"/venues/{VENUE_ID}").json()

    for venue in (listed, one):
        assert (venue["setup_minutes"], venue["turnaround_minutes"]) == (30, 45)
