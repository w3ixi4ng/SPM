"""S-82: the Safety Officer reads the safety review's view of an event's
change history. TC-SAFETYCHECKS-027 to -030."""

import httpx
import pytest

E = "11111111-1111-4111-8111-111111111111"
S = "55555555-5555-4555-8555-555555555555"
C = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
V = "77777777-7777-4777-8777-777777777777"
PATH = f"/safety-checks/{E}/history"

ENTRIES = [
    {"id": 2, "event_id": E, "actor_id": V, "actor_role": "venue_staff", "category": "venue",
     "action": "venue_confirmed", "details": {"venue_name": "Hall One", "reason": None},
     "occurred_at": "2026-10-02T01:00:00Z"},
    {"id": 1, "event_id": E, "actor_id": C, "actor_role": "event_coordinator", "category": "edit",
     "action": "edited", "details": {"changes": {"expected_attendance": {"before": 120, "after": 150}}},
     "occurred_at": "2026-10-01T01:00:00Z"},
]
PROFILES = [
    {"id": C, "name": "Alex Coordinator", "email": "alex@example.com"},
    {"id": V, "name": "Val Venue", "email": "val@example.com"},
]


def response(status, body):
    return httpx.Response(status, json=body)


def signed_in(services, role="safety_officer"):
    services["users"].get.return_value = response(200, {"id": S, "name": "Sam Safety", "role": role})
    services["users"].post.return_value = response(200, PROFILES)


def events_answer(services, status="pending_safety_check", reviewed=False, history_status=200, scope_status=200):
    async def get(path, **kwargs):
        if path.endswith("/history-scope"):
            return response(scope_status, {
                "id": E, "name": "Autumn Forum", "status": status,
                "assigned_coordinator_id": C, "safety_reviewed": reviewed,
            } if scope_status == 200 else {"detail": "Event not found"})
        if path.endswith("/history"):
            return response(history_status, ENTRIES)
        raise AssertionError(path)

    services["events"].get.side_effect = get


def history_reads(services):
    return [call for call in services["events"].get.await_args_list if call.args[0].endswith("/history")]


# --- TC-SAFETYCHECKS-027 ----------------------------------------------------
def test_a_safety_officer_reads_the_safety_view(client, services):
    signed_in(services)
    events_answer(services)

    result = client.get(PATH)

    assert result.status_code == 200
    body = result.json()
    assert body["event_id"] == E and body["event_name"] == "Autumn Forum"
    assert [entry["action"] for entry in body["entries"]] == ["venue_confirmed", "edited"]
    assert body["entries"][0]["actor"] == {"id": V, "name": "Val Venue", "role": "venue_staff"}
    assert body["entries"][1]["actor"] == {"id": C, "name": "Alex Coordinator", "role": "event_coordinator"}
    assert body["people"] == {}
    reads = history_reads(services)
    assert len(reads) == 1 and reads[0].kwargs["params"] == {"scope": "safety"}


# --- TC-SAFETYCHECKS-028 ----------------------------------------------------
@pytest.mark.parametrize(
    ("status", "reviewed", "expected"),
    [
        ("pending_safety_check", False, 200),
        ("safety_changes_requested", False, 200),
        ("safety_rejected", False, 200),
        ("confirmed", False, 200),
        ("preparation", False, 200),
        ("planning", True, 200),
        ("planning", False, 404),
        ("submitted", False, 404),
        ("draft", False, 404),
        ("rejected", False, 404),
    ],
)
def test_only_events_that_entered_the_safety_check_are_shown(client, services, status, reviewed, expected):
    signed_in(services)
    events_answer(services, status=status, reviewed=reviewed)

    result = client.get(PATH)

    assert result.status_code == expected
    if expected == 404:
        assert result.json()["detail"] == "Event not found"
        assert history_reads(services) == []


def test_a_missing_event_is_not_found(client, services):
    signed_in(services)
    events_answer(services, scope_status=404)

    result = client.get(PATH)

    assert result.status_code == 404
    assert history_reads(services) == []


# --- TC-SAFETYCHECKS-029 ----------------------------------------------------
@pytest.mark.parametrize(
    "role",
    ["event_coordinator", "event_coordinator_lead", "event_organiser",
     "technical_support", "venue_staff", "attendee"],
)
def test_only_safety_officers_use_this_route(client, services, role):
    signed_in(services, role=role)
    events_answer(services)

    assert client.get(PATH).status_code == 403
    services["events"].get.assert_not_awaited()


def test_no_session_is_401(client, services):
    services["users"].get.return_value = response(401, {"detail": "Not authenticated"})

    assert client.get(PATH).status_code == 401
    services["events"].get.assert_not_awaited()


# --- TC-SAFETYCHECKS-030 ----------------------------------------------------
def test_a_service_that_does_not_answer_is_a_502(client, services):
    signed_in(services)
    events_answer(services, history_status=500)
    result = client.get(PATH)
    assert (result.status_code, result.json()["detail"]) == (502, "Events service unavailable")

    async def times_out(path, **kwargs):
        raise httpx.ReadTimeout("slow")

    services["events"].get.side_effect = times_out
    result = client.get(PATH)
    assert (result.status_code, result.json()["detail"]) == (502, "Events service unavailable")

    events_answer(services)
    services["users"].post.return_value = response(500, {"detail": "boom"})
    result = client.get(PATH)
    assert (result.status_code, result.json()["detail"]) == (502, "Users service unavailable")
