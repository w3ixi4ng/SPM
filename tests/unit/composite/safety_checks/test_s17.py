"""S-17: submitting a fully arranged event for the Operational Safety Check."""

import httpx
import pytest

EVENT_ID = "0b6f0e55-0000-4000-8000-000000000001"
C1 = "c0000000-0000-4000-8000-000000000001"
C2 = "c0000000-0000-4000-8000-000000000002"
T1 = "70000000-0000-4000-8000-000000000001"
S1 = "50000000-0000-4000-8000-000000000001"
B1 = "b0000000-0000-4000-8000-000000000001"
B2 = "b0000000-0000-4000-8000-000000000002"
B3 = "b0000000-0000-4000-8000-000000000003"
HALL_A = "f0000000-0000-4000-8000-00000000000a"
STUDIO_2 = "f0000000-0000-4000-8000-000000000002"
ROOM_5 = "f0000000-0000-4000-8000-000000000005"
VENUE_NAMES = {B1: ("Hall A", HALL_A), B2: ("Studio 2", STUDIO_2), B3: ("Room 5", ROOM_5)}

SUBMIT = f"/safety-checks/coordinator/events/{EVENT_ID}/submit"
READINESS = f"/safety-checks/coordinator/events/{EVENT_ID}/readiness"
RESUBMIT = f"/safety-checks/coordinator/events/{EVENT_ID}/resubmit"


def response(status, body):
    return httpx.Response(status, json=body)


def profile(user_id=C1, role="event_coordinator"):
    return {"id": user_id, "name": "Casey", "email": "casey@example.com", "role": role}


def event(**changes):
    row = {
        "id": EVENT_ID,
        "name": "Autumn Forum",
        "organiser_id": "11111111-1111-4111-8111-111111111111",
        "status": "planning",
        "assigned_coordinator_id": C1,
        "technical_support_required": False,
        "assigned_technical_support_id": T1,
        "technical_signoff_decision": "approved",
        "technical_signoff_reason": None,
        "equipment_preparation_status": "ready",
        "safety_decision": None,
        "safety_review_history": [],
    }
    row.update(changes)
    return row


def booking(booking_id, status, **changes):
    name, venue_id = VENUE_NAMES[booking_id]
    row = {
        "id": booking_id,
        "event_id": EVENT_ID,
        "venue_id": venue_id,
        "venue_name": name,
        "status": status,
        "booking_date": "2026-11-20",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "alternative_resolved_at": None,
    }
    row.update(changes)
    return row


BLOCK_K1 = {
    "venue_id": HALL_A,
    "start_date": "2026-11-20",
    "start_time": "09:00:00",
    "end_date": "2026-11-20",
    "end_time": "17:00:00",
    "created_at": "2026-11-01T10:00:00+00:00",
}
BLOCK_K2 = {**BLOCK_K1, "created_at": "2026-11-03T10:00:00+00:00"}
PROJECTORS = [{"event_id": EVENT_ID, "equipment_item_id": "p1", "quantity": 2}]


def arrange(
    services,
    *,
    the_event=None,
    bookings=None,
    blocks=(),
    requirements=PROJECTORS,
    user=None,
):
    services["users"].get.return_value = response(200, user or profile())
    services["events"].get.return_value = response(200, the_event or event())
    rows = [booking(B1, "confirmed")] if bookings is None else bookings

    async def bookings_get(path, params=None):
        if path == "/bookings":
            return response(200, rows)
        if path == "/blocks":
            return response(200, [b for b in blocks if b["venue_id"] == params["venue_id"]])
        raise AssertionError(path)

    services["bookings"].get.side_effect = bookings_get
    services["venues"].get.return_value = response(
        200, {"id": HALL_A, "name": "Hall A", "setup_minutes": 0, "turnaround_minutes": 0}
    )
    services["equipment"].get.return_value = response(200, list(requirements))
    services["events"].post.return_value = response(200, event(status="pending_safety_check"))


def codes(result):
    return [(item["code"], item.get("booking_id")) for item in result.json()["outstanding"]]


def refused(result):
    assert result.status_code == 409, result.text
    assert result.json()["detail"] == "This event has outstanding arrangements"


# --- TC-SAFETYCHECKS-010 --------------------------------------------------
def test_fully_arranged_event_moves_to_pending_safety_check(client, services):
    arrange(services)

    result = client.post(SUBMIT)

    assert result.status_code == 200, result.text
    assert result.json()["status"] == "pending_safety_check"
    services["events"].post.assert_awaited_once_with(
        f"/internal/events/{EVENT_ID}/safety-submission",
        json={"coordinator_id": C1},
    )
    services["events"].get.assert_awaited_once()
    assert services["events"].get.await_args.args[0] == f"/events/assigned/{EVENT_ID}"
    for name in ("bookings", "equipment", "venues"):
        services[name].post.assert_not_awaited()
        services[name].put.assert_not_awaited()
        services[name].patch.assert_not_awaited()
        services[name].delete.assert_not_awaited()


# --- TC-SAFETYCHECKS-011 --------------------------------------------------
def test_venue_only_event_needs_no_technical_signoff(client, services):
    arrange(
        services,
        the_event=event(
            assigned_technical_support_id=None,
            technical_signoff_decision=None,
            equipment_preparation_status="not_started",
        ),
        requirements=[],
    )

    result = client.post(SUBMIT)

    assert result.status_code == 200, result.text
    assert result.json()["status"] == "pending_safety_check"


# --- TC-SAFETYCHECKS-012 --------------------------------------------------
def test_no_confirmed_venue_is_outstanding(client, services):
    arrange(services, bookings=[])

    result = client.post(SUBMIT)

    refused(result)
    assert codes(result) == [("venue_missing", None)]
    services["events"].post.assert_not_awaited()


# --- TC-SAFETYCHECKS-013 --------------------------------------------------
def test_pending_and_held_bookings_are_outstanding(client, services):
    arrange(services, bookings=[
        booking(B1, "confirmed"), booking(B2, "pending"), booking(B3, "held"),
    ])

    result = client.post(SUBMIT)

    refused(result)
    assert result.json()["outstanding"] == [
        {"code": "venue_awaiting", "booking_id": B2,
         "label": "Studio 2 on 20 Nov 2026 is waiting for Venue Staff"},
        {"code": "venue_awaiting", "booking_id": B3,
         "label": "Room 5 on 20 Nov 2026 is waiting for Venue Staff"},
    ]
    services["events"].post.assert_not_awaited()


# --- TC-SAFETYCHECKS-014 --------------------------------------------------
def test_rejected_booking_keeps_event_in_planning(client, services):
    arrange(services, bookings=[
        booking(B1, "confirmed"),
        booking(B2, "rejected", decision_reason="Double-booked"),
    ])

    result = client.post(SUBMIT)

    refused(result)
    assert codes(result) == [("venue_rejected", B2)]
    assert result.json()["outstanding"][0]["label"] == (
        "Studio 2 on 20 Nov 2026 was rejected — request a replacement venue"
    )
    # Nothing is written anywhere: the event stays in planning and B1 stays
    # confirmed on it.
    for name in ("events", "bookings", "equipment"):
        services[name].post.assert_not_awaited()
        services[name].patch.assert_not_awaited()
        services[name].delete.assert_not_awaited()


# --- TC-SAFETYCHECKS-015 --------------------------------------------------
def test_rejected_booking_cleared_by_confirmed_replacement(client, services):
    arrange(services, bookings=[
        booking(B1, "confirmed"),
        booking(B2, "rejected"),
        booking(B3, "pending", replaces_booking_id=B2),
    ])
    waiting = client.post(SUBMIT)
    refused(waiting)
    assert set(codes(waiting)) == {("venue_rejected", B2), ("venue_awaiting", B3)}

    arrange(services, bookings=[
        booking(B1, "confirmed"),
        booking(B2, "replaced", replaced_by_booking_id=B3),
        booking(B3, "confirmed", replaces_booking_id=B2),
    ])
    replaced = client.post(SUBMIT)
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["status"] == "pending_safety_check"


# --- TC-SAFETYCHECKS-026 --------------------------------------------------
def test_rejected_replacement_request_does_not_count_again(client, services):
    # B1 confirmed; B2 rejected; B3 was a replacement request for B2 that
    # Venue Staff also rejected. Only B2 is outstanding.
    arrange(services, bookings=[
        booking(B1, "confirmed"),
        booking(B2, "rejected"),
        booking(B3, "rejected", replaces_booking_id=B2),
    ])
    blocked = client.post(SUBMIT)
    refused(blocked)
    assert codes(blocked) == [("venue_rejected", B2)]

    # A later replacement for B2 is confirmed: B2 is replaced, B3 stays
    # rejected, and nothing is outstanding.
    arrange(services, bookings=[
        booking(B1, "confirmed"),
        booking(B2, "replaced"),
        booking(B3, "rejected", replaces_booking_id=B2),
    ])
    assert client.post(SUBMIT).status_code == 200


# --- TC-SAFETYCHECKS-016 --------------------------------------------------
def test_unavailability_flag_blocks_until_resolved(client, services):
    arrange(services, blocks=[BLOCK_K1])
    flagged = client.post(SUBMIT)
    refused(flagged)
    assert codes(flagged) == [("venue_unavailable", B1)]

    resolved = [booking(B1, "confirmed", alternative_resolved_at="2026-11-02T09:00:00+00:00")]
    arrange(services, bookings=resolved, blocks=[BLOCK_K1])
    assert client.post(SUBMIT).status_code == 200

    arrange(services, bookings=resolved, blocks=[BLOCK_K1, BLOCK_K2])
    flagged_again = client.post(SUBMIT)
    refused(flagged_again)
    assert codes(flagged_again) == [("venue_unavailable", B1)]


# --- TC-SAFETYCHECKS-017 --------------------------------------------------
@pytest.mark.parametrize(
    "requirements, support_required",
    [(PROJECTORS, False), ([], True)],
)
def test_signoff_needed_without_support_assigned(client, services, requirements, support_required):
    arrange(
        services,
        the_event=event(
            technical_support_required=support_required,
            assigned_technical_support_id=None,
            technical_signoff_decision=None,
            equipment_preparation_status="not_started",
        ),
        requirements=requirements,
    )

    result = client.post(SUBMIT)

    refused(result)
    assert codes(result) == [
        ("technical_support_unassigned", None),
        ("technical_signoff_awaiting", None),
        ("equipment_preparation", None),
    ]
    assert result.json()["outstanding"][2]["label"] == "Equipment preparation is Not Started"
    services["events"].post.assert_not_awaited()


# --- TC-SAFETYCHECKS-018 --------------------------------------------------
def test_signoff_awaiting_or_declined_is_outstanding(client, services):
    arrange(services, the_event=event(technical_signoff_decision=None))
    awaiting = client.post(SUBMIT)
    refused(awaiting)
    assert codes(awaiting) == [("technical_signoff_awaiting", None)]

    arrange(services, the_event=event(
        technical_signoff_decision="declined",
        technical_signoff_reason="Only one sound desk exists",
    ))
    declined = client.post(SUBMIT)
    refused(declined)
    assert declined.json()["outstanding"] == [{
        "code": "technical_signoff_declined",
        "label": "Technical Support declined: Only one sound desk exists",
    }]

    arrange(services, the_event=event(
        technical_signoff_override_comment="Borrowing 2 projectors from Library",
    ))
    assert client.post(SUBMIT).status_code == 200


# --- TC-SAFETYCHECKS-019 --------------------------------------------------
@pytest.mark.parametrize(
    "preparation, label",
    [("not_started", "Not Started"), ("in_progress", "In Progress")],
)
def test_equipment_preparation_must_be_ready(client, services, preparation, label):
    arrange(services, the_event=event(equipment_preparation_status=preparation))

    result = client.post(SUBMIT)

    refused(result)
    assert result.json()["outstanding"] == [
        {"code": "equipment_preparation", "label": f"Equipment preparation is {label}"},
    ]


# --- TC-SAFETYCHECKS-020 --------------------------------------------------
def test_every_outstanding_item_listed(client, services):
    arrange(
        services,
        the_event=event(
            assigned_technical_support_id=None,
            technical_signoff_decision=None,
            equipment_preparation_status="not_started",
        ),
        bookings=[booking(B2, "pending"), booking(B3, "rejected")],
    )
    expected = [
        ("venue_missing", None),
        ("venue_awaiting", B2),
        ("venue_rejected", B3),
        ("technical_support_unassigned", None),
        ("technical_signoff_awaiting", None),
        ("equipment_preparation", None),
    ]

    submitted = client.post(SUBMIT)
    refused(submitted)
    assert codes(submitted) == expected

    read = client.get(READINESS)
    assert read.status_code == 200
    assert read.json()["ready"] is False
    assert read.json()["outstanding"] == submitted.json()["outstanding"]
    services["events"].post.assert_not_awaited()


def test_readiness_of_a_ready_event(client, services):
    arrange(services)

    read = client.get(READINESS)

    assert read.json() == {"ready": True, "outstanding": []}
    services["events"].post.assert_not_awaited()


# --- TC-SAFETYCHECKS-021 --------------------------------------------------
@pytest.mark.parametrize("body", [{"override": True}, {"force": True, "outstanding": []}])
def test_submission_cannot_be_overridden(client, services, body):
    arrange(services, bookings=[booking(B1, "confirmed"), booking(B2, "rejected")])

    result = client.post(SUBMIT, json=body)

    assert result.status_code == 422
    services["events"].post.assert_not_awaited()


# --- TC-SAFETYCHECKS-022 --------------------------------------------------
def test_submission_limited_to_assigned_coordinator_in_planning(client, services):
    arrange(services, user=profile(C2))
    services["events"].get.return_value = response(404, {"detail": "Event not found"})
    assert client.post(SUBMIT).status_code == 404

    for role in ("event_organiser", "technical_support", "safety_officer"):
        arrange(services, user=profile(role=role))
        assert client.post(SUBMIT).status_code == 403

    for status in ("submitted", "pending_safety_check", "confirmed"):
        arrange(services, the_event=event(status=status))
        services["bookings"].get.reset_mock()
        result = client.post(SUBMIT)
        assert result.status_code == 409
        assert result.json()["detail"] == "This event is not in planning"
        services["bookings"].get.assert_not_awaited()

    arrange(services)
    services["users"].get.return_value = response(401, {"detail": "Not authenticated"})
    assert client.post(SUBMIT).status_code == 401

    services["events"].post.assert_not_awaited()


# --- TC-SAFETYCHECKS-023 --------------------------------------------------
def test_safety_resubmit_runs_the_same_check(client, services):
    returned = event(safety_decision="changes_requested", safety_review_history=[{
        "review_number": 1, "decision": "changes_requested", "reason": "Add stewards",
        "safety_officer_id": S1, "decided_at": "2026-10-10T09:00:00Z",
    }])
    arrange(services, the_event=returned, bookings=[booking(B1, "confirmed"), booking(B2, "rejected")])

    blocked = client.post(RESUBMIT)
    refused(blocked)
    assert codes(blocked) == [("venue_rejected", B2)]
    services["events"].post.assert_not_awaited()

    arrange(services, the_event=returned)
    services["events"].post.return_value = response(200, {
        **returned, "status": "pending_safety_check", "safety_decision": None,
    })
    ready = client.post(RESUBMIT)
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "pending_safety_check"
    assert len(ready.json()["safety_review_history"]) == 1
    services["events"].post.assert_awaited_once_with(
        f"/internal/events/{EVENT_ID}/safety-resubmit",
        json={"coordinator_id": C1},
    )


# --- TC-SAFETYCHECKS-024 --------------------------------------------------
@pytest.mark.parametrize("service", ["bookings", "venues", "equipment", "events"])
@pytest.mark.parametrize("failure", ["500", "timeout"])
def test_dependency_failure_never_submits(client, services, service, failure):
    arrange(services)
    broken = (
        response(500, {"detail": "boom"}) if failure == "500"
        else httpx.ReadTimeout("slow")
    )
    target = services[service].get
    target.side_effect = None
    if failure == "500":
        target.return_value = broken
    else:
        target.side_effect = broken

    result = client.post(SUBMIT)

    assert result.status_code == 502
    services["events"].post.assert_not_awaited()


# --- TC-SAFETYCHECKS-025 --------------------------------------------------
def test_queue_and_approval_use_new_stage(client, services):
    services["users"].get.return_value = response(200, profile(S1, "safety_officer"))
    services["events"].get.return_value = response(
        200, [event(status="pending_safety_check", organiser_id="o1")]
    )
    services["users"].post.return_value = response(200, [])

    queue = client.get("/safety-checks")

    assert queue.status_code == 200
    assert queue.json()[0]["status"] == "pending_safety_check"

    services["events"].post.return_value = response(
        200, event(status="confirmed", safety_decision="approved")
    )
    decided = client.post(f"/safety-checks/{EVENT_ID}/decision", json={"decision": "approved"})
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "confirmed"
