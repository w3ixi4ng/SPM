"""S-93 eligibility and cross-Lead inventory at the composite boundary."""

from .conftest import COORDINATOR_A, COORDINATOR_B, EVENT_ID, coordinator, event_response, fake_response, organiser_me_response

LEAD = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
OTHER = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


def lead_user():
    return organiser_me_response(user_id=LEAD, role="event_coordinator_lead")


def test_candidate_pool_filters_inactive_and_malformed(client, users):
    users.get.side_effect = [lead_user(), fake_response(200, [
        {**coordinator(COORDINATOR_A), "coordinator_active": False},
        {**coordinator(COORDINATOR_B), "coordinator_active": True},
        {**coordinator(OTHER), "coordinator_active": None},
    ])]
    response = client.get("/event-requests/coordinators")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [COORDINATOR_B]


def test_selected_inventory_marks_cross_lead_and_legacy_read_only(client, users, events):
    users.get.side_effect = [lead_user(), fake_response(200, [
        {**coordinator(COORDINATOR_A), "coordinator_active": False},
    ])]
    events.get.return_value = fake_response(200, [
        {"id": EVENT_ID, "name": "Mine", "assigning_lead_id": LEAD},
        {"id": COORDINATOR_B, "name": "Other", "assigning_lead_id": OTHER,
         "organiser_id": "private-organiser", "internal_notes": "private note"},
        {"id": OTHER, "name": "Legacy", "assigning_lead_id": None},
    ])
    response = client.get(f"/event-requests/coordinators/{COORDINATOR_A}/active-events")
    assert response.status_code == 200
    assert response.json()["active_assignment_count"] == 3
    assert [(row["scope"], row["actionable"], row["inactive_owner"]) for row in response.json()["events"]] == [
        ("mine", True, True), ("other_lead", False, True), ("legacy", False, True),
    ]
    assert "organiser_id" not in response.json()["events"][1]
    assert "internal_notes" not in response.json()["events"][1]
    events.get.assert_awaited_once()


def test_selected_inventory_rejects_unknown_coordinator_and_non_lead(client, users, events):
    users.get.side_effect = [lead_user(), fake_response(200, [])]
    unknown = client.get(f"/event-requests/coordinators/{COORDINATOR_A}/active-events")
    assert unknown.status_code == 404
    events.get.assert_not_awaited()

    users.get.side_effect = [organiser_me_response(role="event_coordinator")]
    denied = client.get(f"/event-requests/coordinators/{COORDINATOR_A}/active-events")
    assert denied.status_code == 403
    events.get.assert_not_awaited()


def test_selected_coordinator_with_no_active_events_has_zero_count(client, users, events):
    users.get.side_effect = [lead_user(), fake_response(200, [coordinator(COORDINATOR_B)])]
    events.get.return_value = fake_response(200, [])
    response = client.get(f"/event-requests/coordinators/{COORDINATOR_B}/active-events")
    assert response.status_code == 200
    assert response.json()["active_assignment_count"] == 0
    assert response.json()["events"] == []

def test_s83_and_s84_reject_inactive_target_before_events_write(client, users, events):
    for path, body in [
        ("assignment", {"coordinator_id": COORDINATOR_A}),
        ("reassignment", {
            "coordinator_id": COORDINATOR_A,
            "expected_coordinator_id": COORDINATOR_B,
            "expected_assignment_version": 2,
        }),
    ]:
        users.get.side_effect = [lead_user(), fake_response(200, [
            {**coordinator(COORDINATOR_A), "coordinator_active": False},
            {**coordinator(COORDINATOR_B), "coordinator_active": True},
        ])]
        response = client.post(f"/event-requests/{EVENT_ID}/{path}", json=body)
        assert response.status_code == 422
    events.post.assert_not_awaited()
    events.get.assert_not_awaited()


def test_browser_supplied_service_token_is_not_forwarded_to_atomic_write(client, users, events, notifications):
    users.get.side_effect = [lead_user(), fake_response(200, [coordinator(COORDINATOR_B)])]
    events.post.return_value = event_response(status_code=200, name="Autumn Forum")
    notifications.post.return_value = fake_response(201, {"notifications": []})
    response = client.post(
        f"/event-requests/{EVENT_ID}/assignment",
        json={"coordinator_id": COORDINATOR_B},
        headers={"X-Assignment-Service-Token": "attacker-controlled"},
    )
    assert response.status_code == 200
    assert events.post.await_args.kwargs["headers"] == {
        "X-Assignment-Service-Token": "unit-assignment-secret"
    }
