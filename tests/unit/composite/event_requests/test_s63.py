"""S-63: important request decisions and schedule changes reach the Organiser."""

import pytest

from .conftest import EVENT_ID, ORGANISER_ID, event_response, fake_response


DECISION_URL = f"/event-requests/{EVENT_ID}/decision"
INFORMATION_URL = f"/event-requests/{EVENT_ID}/information"


def _sent(notifications):
    return notifications.post.await_args.kwargs["json"]["notifications"][0]


@pytest.mark.parametrize(
    "decision,reason,comment,status,expected",
    [
        ("approved", None, None, "planning", "approved"),
        ("rejected", "Budget unavailable", None, "rejected", "Budget unavailable"),
        (
            "returned",
            "Clarify attendance",
            "Add the invited audience",
            "returned",
            "Update the request and resubmit it",
        ),
    ],
)
def test_each_request_decision_notifies_the_organiser_with_its_action(
    client, events, notifications, decision, reason, comment, status, expected
):
    events.post.return_value = event_response(
        200,
        status=status,
        decision=decision,
        decision_reason=reason,
        decision_comment=comment,
        decided_at="2026-10-31T09:00:00Z",
    )
    notifications.post.return_value = fake_response(201, [])
    body = {"decision": decision}
    if reason:
        body["reason"] = reason
    if comment:
        body["comment"] = comment

    response = client.post(DECISION_URL, json=body)

    assert response.status_code == 200, response.text
    row = _sent(notifications)
    assert row["recipient_id"] == ORGANISER_ID
    assert row["event_id"] == EVENT_ID
    assert row["event_name"] == "Alumni networking evening"
    assert row["kind"] == "event_request_decision"
    assert expected in row["message"]
    assert row["deduplication_key"].startswith(
        f"event_request_decision:{EVENT_ID}:{decision}:2026-10-31T09:00:00Z:"
    )


def test_a_refused_request_decision_never_notifies(client, events, notifications):
    events.post.return_value = fake_response(409, {"detail": "Already decided"})

    response = client.post(DECISION_URL, json={"decision": "approved"})

    assert response.status_code == 409
    notifications.post.assert_not_awaited()


@pytest.mark.parametrize(
    "after,word",
    [
        (
            {
                "start_date": "2026-10-22",
                "start_time": "18:00:00",
                "end_date": "2026-10-22",
                "end_time": "21:00:00",
            },
            "postponed",
        ),
        (
            {
                "start_date": "2026-10-20",
                "start_time": "17:00:00",
                "end_date": "2026-10-20",
                "end_time": "20:00:00",
            },
            "rescheduled",
        ),
    ],
)
def test_schedule_changes_name_the_old_and_new_time_and_required_attention(
    client, events, notifications, after, word
):
    before = event_response(200, edit_version=4).json()
    saved = {**before, **after, "edit_version": 5}
    events.get.return_value = fake_response(200, before)
    events.patch.return_value = fake_response(200, saved)
    notifications.post.return_value = fake_response(201, [])

    response = client.patch(
        INFORMATION_URL,
        json={"expected_version": 4, "impact_accepted": True, **after},
    )

    assert response.status_code == 200, response.text
    row = _sent(notifications)
    assert row["kind"] == "event_schedule_changed"
    assert word in row["message"]
    assert "20 Oct 2026 18:00–21:00" in row["message"]
    assert "Review the updated event details" in row["message"]
    assert row["deduplication_key"] == (
        f"event_schedule_changed:{EVENT_ID}:5:{ORGANISER_ID}"
    )


def test_routine_information_edits_do_not_create_a_change_notification(
    client, events, notifications
):
    before = event_response(200, edit_version=4, internal_notes="Old note").json()
    events.get.return_value = fake_response(200, before)
    events.patch.return_value = fake_response(
        200, {**before, "internal_notes": "Latest note", "edit_version": 5}
    )

    response = client.patch(
        INFORMATION_URL,
        json={"expected_version": 4, "internal_notes": "Latest note"},
    )

    assert response.status_code == 200, response.text
    notifications.post.assert_not_awaited()


def test_a_notification_failure_is_reported_after_the_event_was_saved(
    client, events, notifications
):
    events.post.return_value = event_response(
        200,
        status="planning",
        decision="approved",
        decided_at="2026-10-31T09:00:00Z",
    )
    notifications.post.return_value = fake_response(500, {"detail": "down"})

    response = client.post(DECISION_URL, json={"decision": "approved"})

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "The event was saved, but the Organiser notification could not be delivered."
    )
