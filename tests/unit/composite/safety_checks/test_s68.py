"""S-68: registered Attendees hear only a finally confirmed reschedule."""

import uuid

from .test_app import (
    EVENT_ID,
    OFFICER_ID,
    REVIEW_UPDATED_AT,
    authorize,
    event,
    response,
)


PRIOR_APPROVAL = "2026-10-01T09:00:00Z"
CURRENT_APPROVAL = "2026-10-10T09:00:00Z"


def approved_reschedule(**changes):
    row = event(
        status="confirmed",
        start_date="2026-11-20",
        start_time="13:00:00",
        end_date="2026-11-20",
        end_time="16:00:00",
        safety_decision="approved",
        safety_officer_id=OFFICER_ID,
        safety_decided_at=CURRENT_APPROVAL,
        safety_review_history=[
            {
                "review_number": 1,
                "decision": "approved",
                "reason": None,
                "safety_officer_id": OFFICER_ID,
                "decided_at": PRIOR_APPROVAL,
            },
            {
                "review_number": 2,
                "decision": "approved",
                "reason": None,
                "safety_officer_id": OFFICER_ID,
                "decided_at": CURRENT_APPROVAL,
            },
        ],
    )
    row.update(changes)
    return row


def schedule_history(*entries):
    return response(200, list(entries) or [
        {
            "occurred_at": "2026-10-05T09:00:00Z",
            "action": "edited",
            "details": {
                "changes": {
                    "start_date": {"before": "2026-11-18", "after": "2026-11-20"},
                    "start_time": {"before": "09:00:00", "after": "13:00:00"},
                    "end_date": {"before": "2026-11-18", "after": "2026-11-20"},
                    "end_time": {"before": "12:00:00", "after": "16:00:00"},
                }
            },
        }
    ])


def attendee_rows(count):
    return [
        {"id": str(uuid.uuid4()), "event_id": EVENT_ID, "attendee_id": str(uuid.uuid4())}
        for _ in range(count)
    ]


def test_reconfirmation_notifies_every_current_registration_in_bounded_batches(
    client, services
):
    authorize(services)
    saved = approved_reschedule()
    services["events"].post.return_value = response(200, saved)
    services["events"].get.return_value = schedule_history()
    registrations = attendee_rows(21)
    services["registrations"].get.return_value = response(200, registrations)

    result = client.post(
        f"/safety-checks/{EVENT_ID}/decision",
        json={"decision": "approved", "expected_event_updated_at": REVIEW_UPDATED_AT},
    )

    assert result.status_code == 200, result.text
    services["events"].get.assert_awaited_once_with(
        f"/internal/events/{EVENT_ID}/history"
    )
    services["registrations"].get.assert_awaited_once_with(
        f"/registrations/events/{EVENT_ID}"
    )
    calls = services["notifications"].post.await_args_list
    attendee_batches = [call.kwargs["json"]["notifications"] for call in calls[1:]]
    assert [len(batch) for batch in attendee_batches] == [20, 1]
    sent = [row for batch in attendee_batches for row in batch]
    assert {row["recipient_id"] for row in sent} == {
        row["attendee_id"] for row in registrations
    }
    assert {row["kind"] for row in sent} == {"event_schedule_changed"}
    assert all("Safety Forum" in row["message"] for row in sent)
    assert all("20 Nov 2026, 1:00 pm to 4:00 pm" in row["message"] for row in sent)
    assert all("registration is still active" in row["message"] for row in sent)
    assert len({row["deduplication_key"] for row in sent}) == 21
    assert all(CURRENT_APPROVAL in row["deduplication_key"] for row in sent)


def test_initial_confirmation_does_not_claim_the_event_was_rescheduled(client, services):
    authorize(services)
    services["events"].post.return_value = response(
        200,
        event(
            status="confirmed",
            safety_decision="approved",
            safety_officer_id=OFFICER_ID,
            safety_decided_at=CURRENT_APPROVAL,
            safety_review_history=[{
                "review_number": 1,
                "decision": "approved",
                "reason": None,
                "safety_officer_id": OFFICER_ID,
                "decided_at": CURRENT_APPROVAL,
            }],
        ),
    )

    result = client.post(
        f"/safety-checks/{EVENT_ID}/decision",
        json={"decision": "approved", "expected_event_updated_at": REVIEW_UPDATED_AT},
    )

    assert result.status_code == 200
    services["events"].get.assert_not_awaited()
    services["registrations"].get.assert_not_awaited()
    assert len(services["notifications"].post.await_args_list) == 1


def test_non_schedule_work_and_a_change_back_to_the_confirmed_window_send_nothing(
    client, services
):
    authorize(services)
    services["events"].post.return_value = response(
        200,
        approved_reschedule(
            start_date="2026-11-18",
            start_time="09:00:00",
            end_date="2026-11-18",
            end_time="12:00:00",
        ),
    )
    services["events"].get.return_value = schedule_history(
        {
            "occurred_at": "2026-10-04T09:00:00Z",
            "action": "edited",
            "details": {"changes": {
                "expected_attendance": {"before": 100, "after": 120},
                "start_date": {"before": "2026-11-18", "after": "2026-11-20"},
            }},
        },
        {
            "occurred_at": "2026-10-05T09:00:00Z",
            "action": "edited",
            "details": {"changes": {
                "start_date": {"before": "2026-11-20", "after": "2026-11-18"},
            }},
        },
    )

    result = client.post(
        f"/safety-checks/{EVENT_ID}/decision",
        json={"decision": "approved", "expected_event_updated_at": REVIEW_UPDATED_AT},
    )

    assert result.status_code == 200
    services["registrations"].get.assert_not_awaited()
    assert len(services["notifications"].post.await_args_list) == 1


def test_rejected_or_returned_reviews_do_not_read_attendees(client, services):
    for decision, reason in (
        ("rejected", "Unsafe route"),
        ("changes_requested", "Move the cables"),
    ):
        services["users"].reset_mock()
        services["events"].reset_mock()
        services["notifications"].reset_mock()
        services["registrations"].reset_mock()
        authorize(services)
        services["events"].post.return_value = response(
            200,
            event(
                status="safety_rejected" if decision == "rejected" else "planning",
                safety_decision=decision,
                safety_decision_reason=reason,
                safety_officer_id=OFFICER_ID,
                safety_decided_at=CURRENT_APPROVAL,
            ),
        )
        services["notifications"].post.return_value.status_code = 201

        result = client.post(
            f"/safety-checks/{EVENT_ID}/decision",
            json={
                "decision": decision,
                "reason": reason,
                "expected_event_updated_at": REVIEW_UPDATED_AT,
            },
        )

        assert result.status_code == 200
        services["events"].get.assert_not_awaited()
        services["registrations"].get.assert_not_awaited()
        assert len(services["notifications"].post.await_args_list) == 1
