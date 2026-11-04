"""S-60 impact decisions over faked owning-service HTTP boundaries."""

from copy import deepcopy

from .conftest import COORDINATOR_A, COORDINATOR_B, EVENT_ID, fake_response, app_module

impact = app_module.impact
REQUEST_ID = "44444444-4444-4444-8444-444444444444"
P = "22222222-2222-4222-8222-222222222222"
B1 = "55555555-5555-4555-8555-555555555555"
B2 = "66666666-6666-4666-8666-666666666666"
V1 = "77777777-7777-4777-8777-777777777777"
V2 = "88888888-8888-4888-8888-888888888888"
OLD = {"start_date": "2026-12-04", "start_time": "09:00:00", "end_date": "2026-12-04", "end_time": "12:00:00",
       "expected_attendance": 120, "venue": None, "special_requirements": None,
       "room_layout": "theatre", "required_facilities": [], "required_accessibility": []}
NEW = {**OLD, "expected_attendance": 150, "room_layout": "banquet"}
EVENT = {"id": EVENT_ID, "status": "confirmed", "assigned_coordinator_id": COORDINATOR_A,
         "assigned_technical_support_id": "99999999-9999-4999-8999-999999999999",
         "updated_at": "2026-10-27T09:00:00Z", "edit_version": 4, **OLD}
REQUEST = {"id": REQUEST_ID, "event_id": EVENT_ID, "status": "pending",
           "accepted_values": OLD, "proposed_values": NEW,
           "accepted_equipment": [{"equipment_item_id": P, "required_quantity": 2}],
           "proposed_equipment": [{"equipment_item_id": P, "required_quantity": 3}],
           "submitted_at": "2026-10-27T09:00:00Z", "impacts": []}
BOOKINGS = [
    {"id": B1, "event_id": EVENT_ID, "venue_id": V1, "status": "confirmed",
     "booking_date": "2026-12-04", "start_time": "09:00:00", "end_time": "12:00:00"},
    {"id": B2, "event_id": EVENT_ID, "venue_id": V2, "status": "confirmed",
     "booking_date": "2026-12-04", "start_time": "09:00:00", "end_time": "12:00:00"},
]
VENUES = {
    V1: {"id": V1, "name": "Hall A", "capacity": 130, "room_layouts": ["theatre"],
         "facilities": [], "accessibility": [], "setup_minutes": 15, "turnaround_minutes": 15},
    V2: {"id": V2, "name": "Hall B", "capacity": 220, "room_layouts": ["theatre", "banquet"],
         "facilities": [], "accessibility": [], "setup_minutes": 0, "turnaround_minutes": 0},
}


def test_attendance_and_layout_impacts_are_booking_specific():
    items = impact.assess(EVENT, REQUEST, BOOKINGS, VENUES, {},
        [{"equipment_item_id": P, "required_quantity": 2}],
        [{"id": P, "total_quantity": 10}], [], [], False)
    codes = {(item["arrangement_id"], item["code"]) for item in items}
    assert (B1, "capacity") in codes and (B1, "layout") in codes
    assert (B2, "capacity") not in codes and (B2, "layout") not in codes
    assert (P, "requirement") in codes
    assert any(item["kind"] == "technical_support" for item in items)
    assert any(item["kind"] == "safety" and item["status"] == "informational" for item in items)


def test_time_change_flags_each_old_booking_but_only_real_clash():
    changed = deepcopy(REQUEST)
    changed["proposed_values"] = {**NEW, "start_date": "2026-12-05", "end_date": "2026-12-05"}
    other = {**BOOKINGS[0], "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "event_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
             "booking_date": "2026-12-05", "start_time": "11:30:00", "end_time": "13:00:00"}
    items = impact.assess(EVENT, changed, BOOKINGS, VENUES, {V1: [other], V2: []}, [], [], [], [], False)
    codes = {(item["arrangement_id"], item["code"]) for item in items}
    assert (B1, "window") in codes and (B2, "window") in codes
    assert (B1, "clash") in codes and (B2, "clash") not in codes


def test_time_change_revalidates_live_equipment_and_technical_schedule():
    changed = deepcopy(REQUEST)
    changed["proposed_values"] = {**NEW, "start_date": "2026-12-05", "end_date": "2026-12-05"}
    other_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    items = impact.assess(EVENT, changed, BOOKINGS, VENUES, {},
        [{"equipment_item_id": P, "required_quantity": 2}],
        [{"id": P, "total_quantity": 3}],
        [{"id": other_id}],
        [{"event_id": other_id, "equipment_item_id": P, "required_quantity": 1}], True)
    projector = next(item for item in items if item["kind"] == "equipment")
    technician = next(item for item in items if item["kind"] == "technical_support")
    assert "exceeds the live available quantity" in projector["reason"]
    assert "another assignment" in technician["reason"]


def test_facilities_and_access_are_assessed_for_each_booking():
    changed = deepcopy(REQUEST)
    changed["proposed_values"] = {**OLD, "required_facilities": ["projector"],
                                  "required_accessibility": ["hearing_loop"]}
    venues = deepcopy(VENUES)
    venues[V2]["facilities"] = ["projector"]
    venues[V2]["accessibility"] = ["hearing_loop"]
    items = impact.assess(EVENT, changed, BOOKINGS, venues, {}, [], [], [], [], False)
    codes = {(item["arrangement_id"], item["code"]) for item in items}
    assert (B1, "required_facilities") in codes
    assert (B1, "required_accessibility") in codes
    assert (B2, "required_facilities") not in codes
    assert (B2, "required_accessibility") not in codes


def test_unchanged_equipment_is_not_flagged_for_attendance_only():
    changed = deepcopy(REQUEST)
    changed["proposed_values"] = {**OLD, "expected_attendance": 150}
    changed["proposed_equipment"] = changed["accepted_equipment"]
    items = impact.assess(EVENT, changed, BOOKINGS, VENUES, {}, [],
                          [{"id": P, "total_quantity": 10}], [], [], False)
    assert all(item["kind"] not in {"equipment", "technical_support"} for item in items)
    assert any(item["kind"] == "safety" for item in items)


def configure(users, events, equipment, bookings, venues, *, equipment_failure=False,
              event_override=None, booking_detail=None, catalogue_override=None):
    users.get.return_value = fake_response(200, {"id": COORDINATOR_A, "role": "event_coordinator"})
    change = deepcopy(REQUEST)
    async def events_get(path, **kwargs):
        if path == f"/events/assigned/{EVENT_ID}": return fake_response(200, event_override or EVENT)
        if path == f"/events/{EVENT_ID}/change-requests": return fake_response(200, [change])
        raise AssertionError(path)
    async def events_post(path, **kwargs):
        if path == "/events/overlapping": return fake_response(200, [])
        if path == "/events/technical-support-load": return fake_response(200, [{"conflict": False}])
        if path.endswith("/prepare"):
            change.update({"status": "applying", "operation_id": kwargs["json"]["operation_id"],
                           "impacts": kwargs["json"]["impacts"]})
            return fake_response(200, change)
        if path.endswith("/complete"):
            change["status"] = "accepted"
            change["resolved_at"] = "2026-10-27T10:00:00Z"
            return fake_response(200, change)
        if path.endswith("/reject"):
            change["status"] = "rejected"
            change["decision_reason"] = kwargs["json"]["reason"]
            return fake_response(200, change)
        if path.endswith("/resolve"):
            return fake_response(200, {**change, "impacts": [{**item, "status": "resolved"} for item in change["impacts"]]})
        raise AssertionError(path)
    async def equipment_get(path, **kwargs):
        if path == "/internal/equipment-requirements":
            return fake_response(200, [{"equipment_item_id": P, "required_quantity": 2}])
        if path == "/equipment/selection":
            return fake_response(200, catalogue_override if catalogue_override is not None else [{"id": P, "total_quantity": 10}])
        raise AssertionError(path)
    async def equipment_post(path, **kwargs):
        if equipment_failure: return fake_response(503, {"detail": "down"})
        return fake_response(200, {"id": change.get("operation_id"), "status": "applied"})
    async def bookings_get(path, **kwargs):
        if booking_detail and path == f"/bookings/{booking_detail['id']}":
            return fake_response(200, booking_detail)
        if path == "/bookings":
            return fake_response(200, BOOKINGS if "event_id" in kwargs.get("params", {}) else [])
        raise AssertionError(path)
    async def venues_get(path, **kwargs): return fake_response(200, VENUES[path.rsplit("/", 1)[-1]])
    events.get.side_effect = events_get
    events.post.side_effect = events_post
    equipment.get.side_effect = equipment_get
    equipment.post.side_effect = equipment_post
    bookings.get.side_effect = bookings_get
    venues.get.side_effect = venues_get
    return change


def test_review_requires_current_coordinator_and_exact_acknowledgement(client, users, events, equipment, bookings, venues):
    configure(users, events, equipment, bookings, venues)
    review = client.get(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/review")
    assert review.status_code == 200, review.json()
    items = review.json()["impacts"]
    assert any(item["arrangement_id"] == B1 for item in items)
    assert client.post(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/accept", json={
        "expected_event_updated_at": EVENT["updated_at"], "impact_ids": [],
    }).status_code == 409
    assert not equipment.post.called


def test_review_follows_current_assignment_without_exposing_other_coordinator_data(
    client, users, events, equipment, bookings, venues,
):
    assigned_event = deepcopy(EVENT)
    configure(users, events, equipment, bookings, venues, event_override=assigned_event)
    original_get = events.get.side_effect
    current_user = {"id": COORDINATOR_A}

    async def scoped_get(path, **kwargs):
        if path == f"/events/assigned/{EVENT_ID}" and current_user["id"] != assigned_event["assigned_coordinator_id"]:
            return fake_response(404, {"detail": "Event not found"})
        return await original_get(path, **kwargs)

    events.get.side_effect = scoped_get
    path = f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/review"
    assert client.get(path).status_code == 200
    current_user["id"] = COORDINATOR_B
    users.get.return_value = fake_response(200, {"id": COORDINATOR_B, "role": "event_coordinator"})
    assert client.get(path).status_code == 404
    assigned_event["assigned_coordinator_id"] = COORDINATOR_B
    assert client.get(path).status_code == 200
    current_user["id"] = COORDINATOR_A
    users.get.return_value = fake_response(200, {"id": COORDINATOR_A, "role": "event_coordinator"})
    assert client.get(path).status_code == 404


def test_review_requires_coordinator_authentication(client, users, events, equipment, bookings, venues):
    configure(users, events, equipment, bookings, venues)
    path = f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/review"
    users.get.return_value = fake_response(401, {"detail": "Not authenticated"})
    assert client.get(path).status_code == 401
    users.get.return_value = fake_response(200, {"id": COORDINATOR_A, "role": "event_organiser"})
    assert client.get(path).status_code == 403
    events.get.assert_not_awaited()


def test_missing_venue_owner_data_fails_closed_before_acceptance(client, users, events, equipment, bookings, venues):
    configure(users, events, equipment, bookings, venues)
    venues.get.side_effect = lambda path, **kwargs: fake_response(503, {"detail": "down"})
    result = client.get(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/review")
    assert result.status_code == 502
    assert "Venues service unavailable" in result.json()["detail"]
    events.post.assert_not_awaited()


def test_acceptance_applies_equipment_before_events_and_never_reports_partial_success(client, users, events, equipment, bookings, venues):
    configure(users, events, equipment, bookings, venues, equipment_failure=True)
    review = client.get(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/review").json()
    body = {"expected_event_updated_at": EVENT["updated_at"], "impact_ids": [item["id"] for item in review["impacts"]]}
    first = client.post(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/accept", json=body)
    assert first.status_code == 502
    assert not any(call.args[0].endswith("/complete") for call in events.post.await_args_list)
    equipment.post.side_effect = None
    equipment.post.return_value = fake_response(200, {"status": "applied"})
    second = client.post(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/accept", json=body)
    assert second.status_code == 200, second.json()
    assert second.json()["status"] == "accepted"
    paths = [call.args[0] for call in events.post.await_args_list]
    assert paths.index(next(path for path in paths if path.endswith("/prepare"))) < paths.index(next(path for path in paths if path.endswith("/complete")))


def test_events_finalization_failure_keeps_operation_applying_until_same_retry_succeeds(
    client, users, events, equipment, bookings, venues,
):
    change = configure(users, events, equipment, bookings, venues)
    original_post = events.post.side_effect
    failures = {"remaining": 1}

    async def fail_complete_once(path, **kwargs):
        if path.endswith("/complete") and failures["remaining"]:
            failures["remaining"] -= 1
            return fake_response(503, {"detail": "Temporary Events failure"})
        return await original_post(path, **kwargs)

    events.post.side_effect = fail_complete_once
    review = client.get(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/review").json()
    body = {"expected_event_updated_at": EVENT["updated_at"],
            "impact_ids": [item["id"] for item in review["impacts"]]}
    first = client.post(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/accept", json=body)
    assert first.status_code == 502
    assert change["status"] == "applying" and change["operation_id"]
    assert not any(call.args[0].endswith("/finish") for call in equipment.post.await_args_list)

    retried = client.post(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/accept", json={
        **body, "operation_id": change["operation_id"],
    })
    assert retried.status_code == 200, retried.json()
    assert change["status"] == "accepted"
    assert sum(call.args[0].endswith("/change-batches") for call in equipment.post.await_args_list) == 2
    assert sum(call.args[0].endswith("/finish") for call in equipment.post.await_args_list) == 1


def test_equipment_finish_failure_returns_incomplete_until_idempotent_recovery(
    client, users, events, equipment, bookings, venues,
):
    change = configure(users, events, equipment, bookings, venues)
    original_post = equipment.post.side_effect
    failures = {"remaining": 1}

    async def fail_finish_once(path, **kwargs):
        if path.endswith("/finish") and failures["remaining"]:
            failures["remaining"] -= 1
            return fake_response(503, {"detail": "Temporary Equipment failure"})
        return await original_post(path, **kwargs)

    equipment.post.side_effect = fail_finish_once
    review = client.get(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/review").json()
    body = {"expected_event_updated_at": EVENT["updated_at"],
            "impact_ids": [item["id"] for item in review["impacts"]]}
    first = client.post(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/accept", json=body)
    assert first.status_code == 502
    assert change["status"] == "accepted"
    retry = client.post(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/accept", json={
        **body, "operation_id": change["operation_id"],
    })
    assert retry.status_code == 200 and retry.json()["status"] == "accepted"
    assert sum(call.args[0].endswith("/change-batches") for call in equipment.post.await_args_list) == 1
    assert sum(call.args[0].endswith("/complete") for call in events.post.await_args_list) == 1


def test_rejection_preserves_accepted_values_and_never_mutates_equipment(client, users, events, equipment, bookings, venues):
    change = configure(users, events, equipment, bookings, venues)
    refused = client.post(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/reject", json={"reason": "  Hall unavailable  "})
    assert refused.status_code == 200, refused.json()
    assert refused.json()["status"] == "rejected"
    assert refused.json()["decision_reason"] == "Hall unavailable"
    assert change["accepted_values"]["expected_attendance"] == 120
    assert not equipment.post.called


def test_retired_changed_item_is_rejected_before_durable_prepare(client, users, events, equipment, bookings, venues):
    configure(users, events, equipment, bookings, venues, catalogue_override=[])
    review = client.get(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/review").json()
    result = client.post(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/accept", json={
        "expected_event_updated_at": EVENT["updated_at"],
        "impact_ids": [item["id"] for item in review["impacts"]],
    })
    assert result.status_code == 409
    assert P in result.json()["detail"]
    assert not any(call.args[0].endswith("/prepare") for call in events.post.await_args_list)
    assert not equipment.post.called


def test_live_equipment_shortage_can_be_accepted_with_outstanding_flag(client, users, events, equipment, bookings, venues):
    configure(users, events, equipment, bookings, venues,
              catalogue_override=[{"id": P, "total_quantity": 2}])
    review = client.get(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/review").json()
    shortage = next(item for item in review["impacts"] if item["kind"] == "equipment")
    assert "exceeds the live available quantity" in shortage["reason"]
    result = client.post(f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/accept", json={
        "expected_event_updated_at": EVENT["updated_at"],
        "impact_ids": [item["id"] for item in review["impacts"]],
    })
    assert result.status_code == 200, result.json()
    assert result.json()["status"] == "accepted"
    assert any(item["id"] == shortage["id"] and item["status"] == "outstanding"
               for item in result.json()["impacts"])


def test_impact_resolution_cannot_impersonate_technical_support(client, users, events, equipment, bookings, venues):
    change = configure(users, events, equipment, bookings, venues)
    change.update({"status": "accepted", "resolved_at": "2026-10-27T10:00:00Z", "impact_version": 1,
                   "impacts": [{"id": f"equipment:{P}:requirement", "kind": "equipment",
                                "arrangement_id": P, "status": "outstanding", "reason": "Quantity changed"}]})
    result = client.post(
        f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/impacts/equipment:{P}:requirement/resolve",
        json={"expected_impact_version": 1, "action": "I approve equipment", "evidence": {"signoff_at": "2026-10-28T00:00:00Z"}},
    )
    assert result.status_code == 409
    assert "Technical Support" in result.json()["detail"]
    assert not any(call.args[0].endswith("/resolve") for call in events.post.await_args_list)


def test_new_staff_approved_booking_resolves_old_booking_impact_with_trusted_evidence(
    client, users, events, equipment, bookings, venues,
):
    staff_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    replacement_id = "aaaaaaaa-aaaa-4aaa-8aaa-bbbbbbbbbbbb"
    replacement = {"id": replacement_id, "event_id": EVENT_ID, "venue_id": V2,
                   "status": "confirmed", "booking_date": OLD["start_date"],
                   "start_time": OLD["start_time"], "end_time": OLD["end_time"],
                   "decided_by": staff_id, "decided_at": "2026-10-28T00:00:00Z"}
    changed_event = {**EVENT, "expected_attendance": 150, "room_layout": "banquet"}
    change = configure(users, events, equipment, bookings, venues,
        event_override=changed_event, booking_detail=replacement)
    change.update({"status": "accepted", "resolved_at": "2026-10-27T10:00:00Z", "impact_version": 1,
                   "impacts": [{"id": f"venue_booking:{B1}:capacity", "kind": "venue_booking",
                                "arrangement_id": B1, "status": "outstanding", "reason": "Capacity too low"}]})
    result = client.post(
        f"/event-requests/{EVENT_ID}/change-requests/{REQUEST_ID}/impacts/venue_booking:{B1}:capacity/resolve",
        json={"expected_impact_version": 1, "action": "New Hall B approval reviewed",
              "evidence": {"booking_id": replacement_id, "staff_approved": "forged"}},
    )
    assert result.status_code == 200, result.json()
    sent = next(call.kwargs["json"] for call in events.post.await_args_list if call.args[0].endswith("/resolve"))
    assert sent["evidence"] == {
        "booking_id": replacement_id, "venue_id": V2,
        "venue_decided_by": staff_id, "venue_decided_at": "2026-10-28T00:00:00Z",
    }
