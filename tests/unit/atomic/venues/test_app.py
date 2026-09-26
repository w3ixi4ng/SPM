"""Unit tests for the venues service endpoints -- see TEST_CASES.md."""

import pytest
from postgrest.exceptions import APIError

from .conftest import (
    MISSING_ID,
    STAFF_ID,
    VALID_VENUE,
    VALID_VENUE_STORED,
    VENUE_ID,
    authenticate,
    fake_user,
    get_operation,
    insert_operation,
    list_operation,
    returns,
    venue_row,
)

OTHER_ROLES = ["event_organiser", "technical_support", "attendee"]


# --- TC-VENUES-015 --------------------------------------------------------
def test_venue_staff_create_a_venue(client, db, auth):
    authenticate(client, auth)
    returns(insert_operation(db), [venue_row()])

    response = client.post("/venues", json=VALID_VENUE)

    assert response.status_code == 201
    db.schema.assert_called_once_with("venues")
    db.schema.return_value.table.assert_called_once_with("venues")
    db.schema.return_value.table.return_value.insert.assert_called_once_with(
        {**VALID_VENUE_STORED, "created_by": STAFF_ID}
    )
    body = response.json()
    assert {key: body[key] for key in VALID_VENUE_STORED} == VALID_VENUE_STORED
    assert body["id"] == VENUE_ID
    assert body["created_by"] == STAFF_ID
    assert body["created_at"].startswith("2026-09-26T08:00:00")


# --- TC-VENUES-016 --------------------------------------------------------
def test_created_by_comes_from_the_session(client, db, auth):
    authenticate(client, auth)
    returns(insert_operation(db), [venue_row()])

    response = client.post(
        "/venues",
        json={**VALID_VENUE, "created_by": "99999999-9999-9999-9999-999999999999"},
    )

    assert response.status_code == 201
    inserted = db.schema.return_value.table.return_value.insert.call_args.args[0]
    assert inserted["created_by"] == STAFF_ID


# --- TC-VENUES-017 --------------------------------------------------------
def test_missing_required_field_is_not_saved(client, db, auth):
    authenticate(client, auth)

    response = client.post(
        "/venues",
        json={
            "name": "",
            "location": "10 Anson Road, Singapore 079903",
            "room_layouts": ["boardroom"],
            "operating_hours": [{"day": "tue", "open": "08:00", "close": "17:00"}],
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "Please check the details you entered"
    assert set(body["errors"]) == {"name", "capacity"}
    db.schema.assert_not_called()


# --- TC-VENUES-018 --------------------------------------------------------
@pytest.mark.parametrize("role", ["event_coordinator", *OTHER_ROLES])
def test_only_venue_staff_may_create(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))

    response = client.post("/venues", json=VALID_VENUE)

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied"}
    db.schema.assert_not_called()


# --- TC-VENUES-019 --------------------------------------------------------
def test_create_requires_a_session(client, db):
    response = client.post("/venues", json=VALID_VENUE)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    db.schema.assert_not_called()


# --- TC-VENUES-020 --------------------------------------------------------
def test_duplicate_name_is_rejected(client, db, auth):
    authenticate(client, auth)
    insert_operation(db).execute.side_effect = APIError(
        {
            "code": "23505",
            "message": 'duplicate key value violates unique constraint "venues_venues_name_key"',
            "details": None,
            "hint": None,
        }
    )

    response = client.post("/venues", json=VALID_VENUE)

    assert response.status_code == 409
    assert response.json() == {"detail": "A venue with this name already exists"}


# --- TC-VENUES-021 --------------------------------------------------------
def test_venue_staff_list_venues(client, db, auth):
    authenticate(client, auth)
    rows = [venue_row(), venue_row(id=MISSING_ID, name="Studio B")]
    returns(list_operation(db), rows)

    response = client.get("/venues")

    assert response.status_code == 200
    assert [venue["name"] for venue in response.json()] == ["Harbourfront Hall", "Studio B"]
    db.schema.assert_called_once_with("venues")
    db.schema.return_value.table.assert_called_once_with("venues")
    select = db.schema.return_value.table.return_value.select
    select.return_value.order.assert_called_once_with("name")
    select.return_value.eq.assert_not_called()


# --- TC-VENUES-022 --------------------------------------------------------
def test_event_coordinators_list_venues(client, db, auth):
    authenticate(client, auth, fake_user(role="event_coordinator"))
    returns(list_operation(db), [venue_row(), venue_row(id=MISSING_ID, name="Studio B")])

    response = client.get("/venues")

    assert response.status_code == 200
    assert len(response.json()) == 2


# --- TC-VENUES-023 --------------------------------------------------------
@pytest.mark.parametrize("role", OTHER_ROLES)
@pytest.mark.parametrize("path", ["/venues", f"/venues/{VENUE_ID}", "/venues/options"])
def test_other_roles_cannot_view_venues(client, db, auth, role, path):
    authenticate(client, auth, fake_user(role=role))

    response = client.get(path)

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied"}
    db.schema.assert_not_called()


# --- TC-VENUES-024 --------------------------------------------------------
def test_read_one_venue(client, db, auth):
    authenticate(client, auth)
    returns(get_operation(db), [venue_row()])

    response = client.get(f"/venues/{VENUE_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == VENUE_ID
    db.schema.return_value.table.return_value.select.return_value.eq.assert_called_once_with(
        "id", VENUE_ID
    )


# --- TC-VENUES-025 --------------------------------------------------------
def test_missing_venue_is_404(client, db, auth):
    authenticate(client, auth)
    returns(get_operation(db), [])

    response = client.get(f"/venues/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Venue not found"}


# --- TC-VENUES-026 --------------------------------------------------------
def test_malformed_venue_id_is_rejected(client, db, auth):
    authenticate(client, auth)

    response = client.get("/venues/not-a-uuid")

    assert response.status_code == 422
    db.schema.assert_not_called()


# --- TC-VENUES-027 --------------------------------------------------------
def test_storage_failure_is_a_safe_500(client, db, auth):
    authenticate(client, auth)
    insert_operation(db).execute.side_effect = Exception("connection refused")
    list_operation(db).execute.side_effect = Exception("connection refused")

    created = client.post("/venues", json=VALID_VENUE)
    listed = client.get("/venues")

    for response in (created, listed):
        assert response.status_code == 500
        assert response.json() == {"detail": "Venue storage unavailable"}
        assert "connection refused" not in response.text


# --- TC-VENUES-028 --------------------------------------------------------
@pytest.mark.parametrize("role", [None, "admin"])
def test_unrecognised_role_is_refused(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))

    listed = client.get("/venues")
    created = client.post("/venues", json=VALID_VENUE)

    for response in (listed, created):
        assert response.status_code == 403
        assert response.json() == {"detail": "Recognized role required"}
    db.schema.assert_not_called()


# --- TC-VENUES-029 --------------------------------------------------------
@pytest.mark.parametrize("role", ["venue_staff", "event_coordinator"])
def test_option_sets_are_served(client, db, auth, role):
    authenticate(client, auth, fake_user(role=role))

    response = client.get("/venues/options")

    assert response.status_code == 200
    assert response.json() == {
        "facilities": [
            "projector",
            "screen",
            "sound_system",
            "microphones",
            "wifi",
            "stage",
            "whiteboard",
            "video_conferencing",
            "catering_kitchen",
            "air_conditioning",
            "parking",
        ],
        "accessibility": [
            "wheelchair_access",
            "step_free_entrance",
            "accessible_toilets",
            "lift",
            "hearing_loop",
            "accessible_parking",
        ],
        "room_layouts": [
            "theatre",
            "classroom",
            "boardroom",
            "u_shape",
            "banquet",
            "cocktail",
        ],
        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    }
    db.schema.assert_not_called()


# --- TC-VENUES-030 --------------------------------------------------------
def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
