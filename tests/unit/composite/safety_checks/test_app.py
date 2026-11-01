"""Confirmed acceptance tests for S-86 safety-review orchestration."""

import httpx
import pytest


EVENT_ID = "33333333-3333-4333-8333-333333333333"
ORGANISER_ID = "11111111-1111-4111-8111-111111111111"
COORDINATOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OFFICER_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
SUPPORT_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
VENUE_ID = "44444444-4444-4444-8444-444444444444"
EQUIPMENT_ID = "55555555-5555-4555-8555-555555555555"


def response(status, json):
    return httpx.Response(status, json=json)


def me(role="safety_officer"):
    return response(
        200,
        {"id": OFFICER_ID, "name": "Sam Safety", "email": "sam@example.com", "role": role},
    )


def event(**changes):
    row = {
        "id": EVENT_ID,
        "organiser_id": ORGANISER_ID,
        "status": "confirmed",
        "name": "Safety Forum",
        "purpose": "Operational safety review",
        "start_date": "2026-11-18",
        "start_time": "09:00:00",
        "end_date": "2026-11-18",
        "end_time": "12:00:00",
        "expected_attendance": 120,
        "venue": "Auditorium preferred",
        "special_requirements": "Keep emergency access clear; route crowd around cables",
        "room_layout": "theatre",
        "required_facilities": ["sound_system"],
        "required_accessibility": ["wheelchair_access"],
        "assigned_coordinator_id": COORDINATOR_ID,
        "technical_support_required": True,
        "technical_support_details": "Place speakers clear of exit routes",
        "assigned_technical_support_id": SUPPORT_ID,
        "safety_decision": None,
        "safety_decision_reason": None,
        "safety_officer_id": None,
        "safety_decided_at": None,
    }
    row.update(changes)
    return row


def authorize(services, role="safety_officer"):
    services["users"].get.return_value = me(role)


@pytest.mark.parametrize(
    "me_response,expected",
    [
        (response(401, {"detail": "Not authenticated"}), 401),
        (me("event_coordinator"), 403),
        (me("event_organiser"), 403),
    ],
)
def test_only_safety_officers_can_access_queue(client, services, me_response, expected):
    services["users"].get.return_value = me_response

    result = client.get("/safety-checks")

    assert result.status_code == expected
    services["events"].get.assert_not_awaited()


@pytest.mark.parametrize(
    "me_response,expected",
    [
        (response(401, {"detail": "Not authenticated"}), 401),
        (me("event_coordinator"), 403),
    ],
)
def test_only_safety_officers_can_submit_decisions(
    client, services, me_response, expected
):
    services["users"].get.return_value = me_response

    result = client.post(
        f"/safety-checks/{EVENT_ID}/decision", json={"decision": "approved"}
    )

    assert result.status_code == expected
    services["events"].post.assert_not_awaited()


def test_queue_returns_only_events_selected_by_confirmed_undecided_source(client, services):
    authorize(services)
    services["events"].get.return_value = response(200, [event()])
    services["users"].post.return_value = response(
        200, [{"id": ORGANISER_ID, "name": "Ada Organiser", "email": "ada@example.com"}]
    )

    result = client.get("/safety-checks")

    assert result.status_code == 200
    assert result.json()[0]["status"] == "confirmed"
    assert result.json()[0]["organiser"]["name"] == "Ada Organiser"
    services["events"].get.assert_awaited_once_with("/internal/events/safety-review")


def test_empty_queue_is_an_empty_list(client, services):
    authorize(services)
    services["events"].get.return_value = response(200, [])

    result = client.get("/safety-checks")

    assert result.status_code == 200
    assert result.json() == []
    services["users"].post.assert_not_awaited()


def seed_detail(services):
    authorize(services)
    services["events"].get.return_value = response(200, event())
    services["users"].post.return_value = response(
        200,
        [
            {"id": ORGANISER_ID, "name": "Ada Organiser", "email": "ada@example.com"},
            {"id": SUPPORT_ID, "name": "Terry Support", "email": "terry@example.com"},
        ],
    )
    services["bookings"].get.return_value = response(
        200,
        [
            {
                "id": "66666666-6666-4666-8666-666666666666",
                "event_id": EVENT_ID,
                "venue_id": VENUE_ID,
                "status": "confirmed",
                "venue_name": "Grand Hall",
                "booking_date": "2026-11-18",
                "start_time": "09:00:00",
                "end_time": "12:00:00",
                "room_layout": "theatre",
                "special_requirements": "Maintain emergency access",
                "notes": "Use the north entrance",
            }
        ],
    )
    services["venues"].get.return_value = response(
        200,
        {
            "id": VENUE_ID,
            "name": "Grand Hall",
            "location": "Building A",
            "capacity": 200,
            "accessibility": ["wheelchair_access"],
            "room_layouts": ["theatre"],
            "facilities": ["sound_system"],
            "description": "No open flame; keep north exit clear",
        },
    )
    services["equipment"].get.return_value = response(
        200,
        [
            {
                "id": "77777777-7777-4777-8777-777777777777",
                "event_id": EVENT_ID,
                "equipment_item_id": EQUIPMENT_ID,
                "required_quantity": 4,
                "recorded_by_coordinator_id": COORDINATOR_ID,
                "created_at": "2026-10-01T00:00:00Z",
                "updated_at": "2026-10-01T00:00:00Z",
                "equipment": {
                    "id": EQUIPMENT_ID,
                    "type": "Wireless microphone",
                    "description": "Handheld",
                    "total_quantity": 10,
                    "operational_status": "available",
                    "lifecycle_status": "active",
                },
            }
        ],
    )


def test_detail_enriches_event_organiser_venues_technical_support_and_equipment(client, services):
    seed_detail(services)

    result = client.get(f"/safety-checks/{EVENT_ID}")

    assert result.status_code == 200
    body = result.json()
    assert body["event"]["expected_attendance"] == 120
    assert body["event"]["special_requirements"].startswith("Keep emergency access")
    assert body["organiser"]["name"] == "Ada Organiser"
    assert body["technical_support"]["name"] == "Terry Support"
    assert body["technical_support_notes"] == "Place speakers clear of exit routes"
    assert body["confirmed_venues"][0]["capacity"] == 200
    assert body["confirmed_venues"][0]["layout"] == "theatre"
    assert body["confirmed_venues"][0]["accessibility"] == ["wheelchair_access"]
    assert body["confirmed_venues"][0]["restrictions"] == "No open flame; keep north exit clear"
    assert body["equipment_requirements"][0]["equipment"]["type"] == "Wireless microphone"


@pytest.mark.parametrize(
    "decision,reason,expected_status",
    [
        ("approved", None, "confirmed"),
        ("rejected", "Unsafe crowd route", "safety_rejected"),
        ("changes_requested", "Move equipment away from exit", "planning"),
    ],
)
def test_decision_forwards_verified_officer_and_returns_transition(
    client, services, decision, reason, expected_status
):
    authorize(services)
    services["events"].post.return_value = response(
        200,
        event(
            status=expected_status,
            safety_decision=decision,
            safety_decision_reason=reason,
            safety_officer_id=OFFICER_ID,
            safety_decided_at="2026-10-10T09:00:00Z",
        ),
    )

    result = client.post(
        f"/safety-checks/{EVENT_ID}/decision",
        json={"decision": decision, "reason": reason},
    )

    assert result.status_code == 200
    assert result.json()["status"] == expected_status
    services["events"].post.assert_awaited_once_with(
        f"/internal/events/safety-review/{EVENT_ID}/decision",
        json={"decision": decision, "reason": reason, "safety_officer_id": OFFICER_ID},
    )
    sent = services["notifications"].post.await_args.kwargs["json"]["notifications"][0]
    assert sent["recipient_id"] == ORGANISER_ID
    assert sent["event_id"] == EVENT_ID
    assert sent["event_name"] == "Safety Forum"
    assert sent["kind"] == "safety_check_outcome"
    assert decision.replace("_", " ") in sent["message"].lower()
    assert sent["deduplication_key"] == (
        f"safety_check_outcome:{EVENT_ID}:{decision}:"
        f"2026-10-10T09:00:00Z:{ORGANISER_ID}"
    )
    if decision == "approved":
        assert "event is now confirmed" in sent["message"].lower()
    else:
        assert reason in sent["message"]
        assert "review" in sent["message"].lower()


@pytest.mark.parametrize("status", [404, 409, 422])
def test_identified_event_errors_are_preserved(client, services, status):
    authorize(services)
    services["events"].post.return_value = response(status, {"detail": "identified"})

    result = client.post(
        f"/safety-checks/{EVENT_ID}/decision",
        json={"decision": "approved"},
    )

    assert result.status_code == status
    assert result.json()["detail"] == "identified"
    services["notifications"].post.assert_not_awaited()


def test_a_notification_failure_is_controlled_after_the_safety_outcome_is_saved(
    client, services
):
    authorize(services)
    services["events"].post.return_value = response(
        200,
        event(
            status="confirmed",
            safety_decision="approved",
            safety_officer_id=OFFICER_ID,
            safety_decided_at="2026-10-10T09:00:00Z",
        ),
    )
    services["notifications"].post.return_value.status_code = 500

    result = client.post(
        f"/safety-checks/{EVENT_ID}/decision", json={"decision": "approved"}
    )

    assert result.status_code == 502
    assert result.json() == {"detail": "Notifications service unavailable"}


@pytest.mark.parametrize("failed", ["events", "profiles", "bookings", "venues", "equipment"])
def test_detail_dependency_failures_are_controlled_and_never_write(client, services, failed):
    seed_detail(services)
    if failed == "events":
        services["events"].get.side_effect = httpx.ConnectError("down")
    elif failed == "profiles":
        services["users"].post.return_value = response(500, {"detail": "down"})
    else:
        services[failed].get.side_effect = httpx.ConnectError("down")

    result = client.get(f"/safety-checks/{EVENT_ID}")

    assert result.status_code == 502
    services["events"].post.assert_not_awaited()
