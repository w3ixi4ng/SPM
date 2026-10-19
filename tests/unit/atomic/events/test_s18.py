"""S-18 Coordinator event-information edit specifications."""

from types import SimpleNamespace

from .conftest import COORDINATOR_A, COORDINATOR_B, EVENT_ID, authenticate, event_row, fake_user


def editable_event(**changes):
    values = {
        "status": "planning",
        "name": "Annual Forum",
        "purpose": "Original briefing",
        "start_date": "2026-11-18",
        "start_time": "09:00:00",
        "end_date": "2026-11-18",
        "end_time": "12:00:00",
        "expected_attendance": 120,
        "venue": "Main Hall",
        "special_requirements": None,
        "room_layout": "theatre",
        "required_facilities": ["projector"],
        "required_accessibility": ["wheelchair_access"],
        "assigned_coordinator_id": COORDINATOR_A,
        "decision": "approved",
        "decided_at": "2026-10-10T00:00:00Z",
        "submitted_at": "2026-10-09T00:00:00Z",
        "contact_name": "Alex Tan",
        "contact_email": "alex@example.com",
        "contact_phone": "+65 6000 0000",
        "internal_notes": "Original note",
        "edit_version": 0,
        "edit_history": [],
        "equipment_preparation_status": "ready",
        "equipment_preparation_updated_by": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        "equipment_preparation_updated_at": "2026-10-10T08:00:00Z",
        "safety_review_history": [],
        "safety_decision": None,
        "safety_decision_reason": None,
        "safety_officer_id": None,
        "safety_decided_at": None,
    }
    values.update(changes)
    return event_row(**values)


def assigned_select(db, rows):
    operation = db.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value
    operation.execute.return_value = SimpleNamespace(data=rows)


def edit_update(db, rows):
    operation = (
        db.schema.return_value.table.return_value.update.return_value
        .eq.return_value.eq.return_value.in_.return_value.eq.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)


def safety_submit_update(db, rows):
    operation = (
        db.schema.return_value.table.return_value.update.return_value
        .eq.return_value.eq.return_value.eq.return_value.eq.return_value
    )
    operation.execute.return_value = SimpleNamespace(data=rows)


def sign_in_coordinator(client, auth, coordinator_id=COORDINATOR_A):
    authenticate(client, auth, fake_user(coordinator_id, "event_coordinator"))


def test_routine_edits_save_immediately_without_lifecycle_review(client, db, auth):
    current = editable_event(status="preparation", safety_decision="approved",
        safety_officer_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        safety_decided_at="2026-10-10T09:00:00Z")
    stored = editable_event(**{
        **{key: value for key, value in current.items() if key not in {"purpose", "contact_name", "internal_notes", "edit_version", "edit_history"}},
        "purpose": "Updated delegate briefing",
        "contact_name": "Sam Lee",
        "internal_notes": "Call organiser on arrival",
        "edit_version": 1,
        "edit_history": [{
            "change_number": 1,
            "changed_by": COORDINATOR_A,
            "changed_at": "2026-10-19T01:00:00Z",
            "changes": {},
        }],
    })
    assigned_select(db, [current])
    edit_update(db, [stored])
    sign_in_coordinator(client, auth)

    response = client.patch(f"/events/assigned/{EVENT_ID}", json={
        "expected_version": 0,
        "purpose": "  Updated delegate briefing  ",
        "contact_name": " Sam Lee ",
        "internal_notes": "Call organiser on arrival",
    })

    assert response.status_code == 200
    values = db.schema.return_value.table.return_value.update.call_args.args[0]
    assert values["purpose"] == "Updated delegate briefing"
    assert values["contact_name"] == "Sam Lee"
    assert values["edit_version"] == 1
    assert values["edit_history"][0]["changed_by"] == COORDINATOR_A
    assert set(values["edit_history"][0]["changes"]) == {"purpose", "contact_name", "internal_notes"}
    assert "status" not in values
    assert "safety_decision" not in values


def test_significant_changes_are_server_classified_and_require_acceptance(client, db, auth):
    current = editable_event()
    assigned_select(db, [current])
    sign_in_coordinator(client, auth)

    preview = client.post(f"/events/assigned/{EVENT_ID}/edit-impact", json={
        "expected_version": 0,
        "expected_attendance": 150,
        "required_facilities": ["projector", "stage", "projector"],
    })
    assert preview.status_code == 200
    assert preview.json()["significant_fields"] == ["expected_attendance", "required_facilities"]
    assert preview.json()["requires_impact_acceptance"] is True

    assigned_select(db, [current])
    refused = client.patch(f"/events/assigned/{EVENT_ID}", json={
        "expected_version": 0,
        "expected_attendance": 150,
    })
    assert refused.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()


def test_accepted_significant_edit_restarts_lifecycle_and_safety_check(client, db, auth):
    review = {"review_number": 1, "decision": "approved", "reason": None,
        "safety_officer_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        "decided_at": "2026-10-10T09:00:00Z"}
    current = editable_event(status="preparation", safety_decision="approved",
        safety_officer_id=review["safety_officer_id"], safety_decided_at=review["decided_at"],
        safety_review_history=[review])
    planning = editable_event(expected_attendance=150, status="planning", edit_version=1,
        safety_recheck_required=True,
        safety_review_history=[review], edit_history=[{
            "change_number": 1, "changed_by": COORDINATOR_A,
            "changed_at": "2026-10-19T01:00:00Z",
            "changes": {"expected_attendance": {"before": 120, "after": 150}},
        }])
    assigned_select(db, [current])
    edit_update(db, [planning])
    sign_in_coordinator(client, auth)

    response = client.patch(f"/events/assigned/{EVENT_ID}", json={
        "expected_version": 0,
        "impact_accepted": True,
        "expected_attendance": 150,
    })
    assert response.status_code == 200
    values = db.schema.return_value.table.return_value.update.call_args.args[0]
    assert values["status"] == "planning"
    assert values["safety_recheck_required"] is True
    assert values["safety_decision"] is None
    assert "safety_review_history" not in values
    assert "equipment_preparation_status" not in values

    db.reset_mock()
    assigned_select(db, [planning])
    confirmed = {**planning, "status": "confirmed"}
    safety_submit_update(db, [confirmed])
    submitted = client.post(
        f"/events/assigned/{EVENT_ID}/submit-safety-review",
        json={"expected_version": 1},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "confirmed"


def test_event_edits_fail_closed_and_are_atomic(client, db, auth):
    sign_in_coordinator(client, auth, COORDINATOR_B)
    assigned_select(db, [])
    hidden = client.patch(f"/events/assigned/{EVENT_ID}", json={
        "expected_version": 0, "purpose": "No access",
    })
    assert hidden.status_code == 404

    sign_in_coordinator(client, auth)
    assigned_select(db, [editable_event(status="cancelled")])
    closed = client.patch(f"/events/assigned/{EVENT_ID}", json={
        "expected_version": 0, "purpose": "Too late",
    })
    assert closed.status_code == 409

    assigned_select(db, [editable_event(edit_version=2)])
    stale = client.patch(f"/events/assigned/{EVENT_ID}", json={
        "expected_version": 1, "purpose": "Stale",
    })
    assert stale.status_code == 409
    db.schema.return_value.table.return_value.update.assert_not_called()
