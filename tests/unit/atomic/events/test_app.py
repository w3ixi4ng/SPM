"""Unit tests for the events service endpoints -- see TEST_CASES.md."""

from unittest.mock import call

from .conftest import (
    EVENT_ORGANISER_PERMISSIONS,
    EVENT_ID,
    ORGANISER_ID,
    ROLE_PERMISSIONS,
    authenticate,
    event_row,
    fake_user,
    on_insert,
    on_owned_list,
    on_owned_select,
    on_update,
    on_update_owned,
)

SUBMITTED = {
    "name": "Alumni networking evening",
    "purpose": "Connect alumni with graduating students",
    "start_date": "2026-10-20",
    "start_time": "18:00",
    "end_date": "2026-10-20",
    "end_time": "21:00",
    "expected_attendance": 120,
    "venue": "Main auditorium",
    "equipment_requests": {"projector": 1},
    "accessibility_requirements": "Wheelchair access",
}


# --- TC-EVENTS-012 --------------------------------------------------------
def test_health_reports_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- TC-EVENTS-031 --------------------------------------------------------
def test_prefixed_health_reports_ok_for_gateway(client):
    response = client.get("/events/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- TC-EVENTS-013 --------------------------------------------------------
def test_create_valid_draft(client, db, auth):
    authenticate(client, auth)
    stored = event_row(name="Planning draft")
    on_insert(db, [stored])

    response = client.post("/events/drafts", json={"name": "Planning draft"})

    assert response.status_code == 201
    assert response.json()["status"] == "draft"


# --- TC-EVENTS-014 --------------------------------------------------------
def test_create_submitted_event(client, db, auth):
    authenticate(client, auth)
    stored = event_row(status="submitted", **SUBMITTED)
    on_insert(db, [stored])

    response = client.post("/events", json=SUBMITTED)

    assert response.status_code == 201
    assert response.json()["status"] == "submitted"


# --- TC-EVENTS-015 --------------------------------------------------------
def test_create_derives_organiser_and_status_from_session(client, db, auth):
    authenticate(client, auth)
    on_insert(db, [event_row()])

    response = client.post("/events/drafts", json={})

    assert response.status_code == 201
    db.schema.return_value.table.return_value.insert.assert_called_once_with(
        {
            "name": None,
            "purpose": None,
            "start_date": None,
            "start_time": None,
            "end_date": None,
            "end_time": None,
            "expected_attendance": None,
            "venue": None,
            "equipment_requests": {},
            "accessibility_requirements": None,
            "organiser_id": ORGANISER_ID,
            "status": "draft",
        }
    )


# --- TC-EVENTS-016 --------------------------------------------------------
def test_create_rejects_wrong_role(client, db, auth):
    authenticate(client, auth, fake_user(role="event_coordinator"))

    response = client.post("/events/drafts", json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
    db.schema.assert_not_called()


# --- TC-EVENTS-017 --------------------------------------------------------
def test_create_rejects_missing_role(client, db, auth):
    authenticate(client, auth, fake_user(role=None))

    response = client.post("/events", json=SUBMITTED)

    assert response.status_code == 403
    db.schema.assert_not_called()


# --- TC-EVENTS-018 --------------------------------------------------------
def test_retrieve_owned_event(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(name="Owned draft")])

    response = client.get(f"/events/{EVENT_ID}")

    assert response.status_code == 200
    assert response.json()["name"] == "Owned draft"
    select = db.schema.return_value.table.return_value.select.return_value
    assert select.eq.call_args_list == [call("id", EVENT_ID)]
    select.eq.return_value.eq.assert_called_once_with("organiser_id", ORGANISER_ID)


# --- TC-EVENTS-019 --------------------------------------------------------
def test_cannot_retrieve_another_users_event(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [])

    response = client.get(f"/events/{EVENT_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"


# --- TC-EVENTS-020 --------------------------------------------------------
def test_update_owned_draft_uses_only_supplied_fields(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(name="Old name")])
    on_update_owned(db, [event_row(name="New name")])

    response = client.patch(f"/events/{EVENT_ID}", json={"name": "New name"})

    assert response.status_code == 200
    assert response.json()["name"] == "New name"
    db.schema.return_value.table.return_value.update.assert_called_once_with(
        {"name": "New name"}
    )


# --- TC-EVENTS-021 --------------------------------------------------------
def test_can_update_submitted_event(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(status="submitted", **SUBMITTED)])
    on_update_owned(db, [event_row(status="submitted", **{**SUBMITTED, "name": "Changed"})])

    response = client.patch(f"/events/{EVENT_ID}", json={"name": "Changed"})

    assert response.status_code == 200
    assert response.json()["name"] == "Changed"
    assert response.json()["status"] == "submitted"
    db.schema.return_value.table.return_value.update.assert_called_once_with(
        {"name": "Changed"}
    )


# --- TC-EVENTS-040 --------------------------------------------------------
def test_updating_submitted_event_still_requires_submitted_fields(client, db, auth):
    # A PATCH on a submitted event is validated against the submitted-required
    # rules, not the draft's permissive ones -- otherwise it could null out a
    # field the database's own constraint requires, turning a readable 422
    # into an opaque storage failure.
    authenticate(client, auth)
    on_owned_select(db, [event_row(status="submitted", **SUBMITTED)])

    response = client.patch(f"/events/{EVENT_ID}", json={"venue": ""})

    assert response.status_code == 422
    assert "venue" in response.json()["errors"]
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-022 --------------------------------------------------------
def test_submit_existing_draft(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row()])
    submitted = event_row(status="submitted", **SUBMITTED)
    on_update(db, [submitted])

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    db.schema.return_value.table.return_value.update.assert_called_once_with(
        {
            **SUBMITTED,
            "start_time": "18:00:00",
            "end_time": "21:00:00",
            "status": "submitted",
        }
    )


# --- TC-EVENTS-023 --------------------------------------------------------
def test_cannot_resubmit_submitted_event(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(status="submitted", **SUBMITTED)])

    response = client.post(f"/events/{EVENT_ID}/submit", json=SUBMITTED)

    assert response.status_code == 409
    assert response.json()["detail"] == "Event has already been submitted"
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-024 --------------------------------------------------------
def test_database_failure_returns_safe_500(client, db, auth):
    authenticate(client, auth)
    on_insert(db, error=RuntimeError("database credentials leaked here"))

    response = client.post("/events/drafts", json={})

    assert response.status_code == 500
    assert response.json() == {"detail": "Event storage unavailable"}
    assert "credentials" not in response.text


# --- TC-EVENTS-025 --------------------------------------------------------
def test_create_requires_authentication(client, db, auth):
    response = client.post("/events/drafts", json={})

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    db.schema.assert_not_called()


# --- TC-EVENTS-026 --------------------------------------------------------
def test_update_validates_time_order_against_existing_draft(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(start_time="18:00:00")])

    response = client.patch(f"/events/{EVENT_ID}", json={"end_time": "17:00"})

    assert response.status_code == 422
    assert "end_time must be after start_time" in response.json()["errors"]["body"]
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-027 --------------------------------------------------------
def test_event_organiser_has_the_sprint_one_permissions():
    assert ROLE_PERMISSIONS["event_organiser"] == {
        "dashboard:view",
        "events:create",
        "events:save_draft",
        "events:view_own",
        "events:update_own_draft",
        "events:submit_own",
    }
    assert ROLE_PERMISSIONS["event_organiser"] == EVENT_ORGANISER_PERMISSIONS


# --- TC-EVENTS-028 --------------------------------------------------------
def test_other_known_roles_only_have_dashboard_permission():
    for role in (
        "event_coordinator",
        "venue_staff",
        "technical_support",
        "attendee",
    ):
        assert ROLE_PERMISSIONS[role] == {"dashboard:view"}


# --- TC-EVENTS-029 --------------------------------------------------------
def test_unknown_role_is_rejected(client, db, auth):
    authenticate(client, auth, fake_user(role="invented_role"))

    response = client.post("/events/drafts", json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "Recognized role required"
    db.schema.assert_not_called()


# --- TC-EVENTS-030 --------------------------------------------------------
def test_user_metadata_role_is_not_trusted(client, db, auth):
    user = fake_user(role="attendee")
    user.user_metadata = {"role": "event_organiser"}
    authenticate(client, auth, user)

    response = client.post("/events/drafts", json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
    db.schema.assert_not_called()


# --- TC-EVENTS-032 --------------------------------------------------------
def test_list_returns_only_authenticated_organisers_events(client, db, auth):
    authenticate(client, auth)
    rows = [
        event_row(name="Recent draft"),
        event_row(
            id="44444444-4444-4444-8444-444444444444",
            status="submitted",
            **SUBMITTED,
        ),
    ]
    on_owned_list(db, rows)

    response = client.get("/events")

    assert response.status_code == 200
    assert [event["name"] for event in response.json()] == [
        "Recent draft",
        "Alumni networking evening",
    ]
    select = db.schema.return_value.table.return_value.select.return_value
    select.eq.assert_called_once_with("organiser_id", ORGANISER_ID)
    select.eq.return_value.order.assert_called_once_with("updated_at", desc=True)


# --- TC-EVENTS-033 --------------------------------------------------------
def test_list_returns_empty_array_when_organiser_has_no_events(client, db, auth):
    authenticate(client, auth)
    on_owned_list(db, [])

    response = client.get("/events")

    assert response.status_code == 200
    assert response.json() == []


# --- TC-EVENTS-034 --------------------------------------------------------
def test_list_rejects_role_without_view_permission(client, db, auth):
    authenticate(client, auth, fake_user(role="attendee"))

    response = client.get("/events")

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
    db.schema.assert_not_called()


# --- TC-EVENTS-035 --------------------------------------------------------
def test_update_validates_date_order_against_existing_draft(client, db, auth):
    authenticate(client, auth)
    on_owned_select(db, [event_row(start_date="2026-10-20")])

    response = client.patch(f"/events/{EVENT_ID}", json={"end_date": "2026-10-19"})

    assert response.status_code == 422
    assert "end_date must be on or after start_date" in response.json()["errors"]["body"]
    db.schema.return_value.table.return_value.update.assert_not_called()


# --- TC-EVENTS-036 --------------------------------------------------------
def test_create_accepts_multi_day_event_with_end_time_before_start_time(client, db, auth):
    authenticate(client, auth)
    overnight = {
        **SUBMITTED,
        "start_date": "2026-10-20",
        "start_time": "22:00",
        "end_date": "2026-10-21",
        "end_time": "02:00",
    }
    on_insert(db, [event_row(status="submitted", **overnight)])

    response = client.post("/events", json=overnight)

    assert response.status_code == 201
    assert response.json()["status"] == "submitted"
