"""S-82: the assigned Coordinator and any Lead read an event's change
history, with names. TC-EVENTREQUESTS-117 to -122."""

import httpx
import pytest

from .conftest import fake_response, organiser_me_response

E = "11111111-1111-4111-8111-111111111111"
C = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
C2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
L = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
L2 = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
O = "22222222-2222-4222-8222-222222222222"
GONE = "ffffffff-ffff-4fff-8fff-ffffffffffff"
PATH = f"/event-requests/{E}/history"

PROFILES = [
    {"id": C, "name": "Alex Coordinator", "email": "alex@example.com"},
    {"id": C2, "name": "Blair Coordinator", "email": "blair@example.com"},
    {"id": L, "name": "Lee Lead", "email": "lee@example.com"},
    {"id": O, "name": "Ada Organiser", "email": "ada@example.com"},
]


def scope(owner=C2):
    return {"id": E, "name": "Autumn Forum", "status": "planning",
            "assigned_coordinator_id": owner, "safety_reviewed": False}


def history_entry(entry_id, actor_id, role, category, action, details, occurred_at):
    return {"id": entry_id, "event_id": E, "actor_id": actor_id, "actor_role": role,
            "category": category, "action": action, "details": details, "occurred_at": occurred_at}


HISTORY = [
    history_entry(3, L, "event_coordinator_lead", "assignment", "coordinator_reassigned",
                  {"from_coordinator_id": C, "to_coordinator_id": C2}, "2026-10-03T01:00:00Z"),
    history_entry(2, C, "event_coordinator", "edit", "edited",
                  {"changes": {"expected_attendance": {"before": 120, "after": 150}}, "significant": True},
                  "2026-10-02T01:00:00Z"),
    history_entry(1, O, "event_organiser", "submission", "submitted", {}, "2026-10-01T01:00:00Z"),
]


def signed_in(users, user_id, role):
    users.get.return_value = organiser_me_response(user_id=user_id, role=role)


def events_answer(events, scope_body=None, history=None, scope_status=200, history_status=200):
    async def get(path, **kwargs):
        if path.endswith("/history-scope"):
            return fake_response(scope_status, scope_body or scope())
        if path.endswith("/history"):
            return fake_response(history_status, HISTORY if history is None else history)
        raise AssertionError(path)

    events.get.side_effect = get


def history_reads(events):
    return [call for call in events.get.await_args_list if call.args[0].endswith("/history")]


# --- TC-EVENTREQUESTS-117 ---------------------------------------------------
def test_the_assigned_coordinator_reads_the_history(client, users, events):
    signed_in(users, C2, "event_coordinator")
    events_answer(events)
    users.post.return_value = fake_response(200, PROFILES)

    response = client.get(PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == E
    assert body["event_name"] == "Autumn Forum"
    assert [entry["id"] for entry in body["entries"]] == [3, 2, 1]
    assert body["entries"][0] == {
        "id": 3, "occurred_at": "2026-10-03T01:00:00Z", "category": "assignment",
        "action": "coordinator_reassigned",
        "details": {"from_coordinator_id": C, "to_coordinator_id": C2},
        "actor": {"id": L, "name": "Lee Lead", "role": "event_coordinator_lead"},
    }
    assert body["entries"][2]["actor"] == {"id": O, "name": "Ada Organiser", "role": "event_organiser"}
    assert body["people"] == {C: "Alex Coordinator", C2: "Blair Coordinator"}
    assert users.post.await_count == 1
    assert users.post.await_args.args[0] == "/internal/users/profiles"
    assert set(users.post.await_args.kwargs["json"]["ids"]) == {L, C, O, C2}


# --- TC-EVENTREQUESTS-118 ---------------------------------------------------
def test_any_lead_reads_any_history(client, users, events):
    signed_in(users, L2, "event_coordinator_lead")
    events_answer(events)
    users.post.return_value = fake_response(200, PROFILES)

    response = client.get(PATH)

    assert response.status_code == 200
    assert [entry["action"] for entry in response.json()["entries"]] == [
        "coordinator_reassigned", "edited", "submitted",
    ]


# --- TC-EVENTREQUESTS-119 ---------------------------------------------------
def test_an_unassigned_coordinator_is_turned_away(client, users, events):
    signed_in(users, C, "event_coordinator")
    events_answer(events)
    response = client.get(PATH)
    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"

    events_answer(events, scope_status=404, scope_body={"detail": "Event not found"})
    response = client.get(PATH)
    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"

    assert history_reads(events) == []
    users.post.assert_not_awaited()


# --- TC-EVENTREQUESTS-120 ---------------------------------------------------
@pytest.mark.parametrize(
    ("me", "expected"),
    [
        (fake_response(401, {"detail": "Not authenticated"}), 401),
        (organiser_me_response(user_id=O, role="event_organiser"), 403),
        (organiser_me_response(role="safety_officer"), 403),
        (organiser_me_response(role="technical_support"), 403),
        (organiser_me_response(role="venue_staff"), 403),
        (organiser_me_response(role="attendee"), 403),
    ],
)
def test_other_roles_cannot_read_the_history(client, users, events, me, expected):
    users.get.return_value = me
    events_answer(events)

    assert client.get(PATH).status_code == expected
    events.get.assert_not_awaited()


# --- TC-EVENTREQUESTS-121 ---------------------------------------------------
def test_missing_people_are_shown_honestly(client, users, events):
    signed_in(users, C2, "event_coordinator")
    events_answer(events, history=[
        history_entry(2, None, None, "review", "request_approved",
                      {"reason": None, "comment": None, "backfilled": True}, "2026-10-02T01:00:00Z"),
        history_entry(1, GONE, "event_coordinator", "edit", "edited", {"changes": {}}, "2026-10-01T01:00:00Z"),
    ])
    users.post.return_value = fake_response(200, PROFILES)

    entries = client.get(PATH).json()["entries"]

    assert entries[0]["actor"] is None
    assert entries[1]["actor"] == {"id": GONE, "name": None, "role": "event_coordinator"}


# --- TC-EVENTREQUESTS-122 ---------------------------------------------------
def test_a_service_that_does_not_answer_is_a_502(client, users, events):
    signed_in(users, C2, "event_coordinator")
    users.post.return_value = fake_response(200, PROFILES)

    events_answer(events, history_status=500)
    response = client.get(PATH)
    assert (response.status_code, response.json()["detail"]) == (502, "Events service unavailable")

    async def times_out(path, **kwargs):
        if path.endswith("/history-scope"):
            return fake_response(200, scope())
        raise httpx.ReadTimeout("slow")

    events.get.side_effect = times_out
    response = client.get(PATH)
    assert (response.status_code, response.json()["detail"]) == (502, "Events service unavailable")

    events_answer(events)
    users.post.return_value = fake_response(500, {"detail": "boom"})
    response = client.get(PATH)
    assert (response.status_code, response.json()["detail"]) == (502, "Users service unavailable")
