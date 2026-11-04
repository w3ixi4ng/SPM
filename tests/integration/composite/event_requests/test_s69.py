"""TC-EVENTREQUESTS-203 (S-69): approving a cancellation through Kong notifies
every Attendee registered or waiting, once, and no one else."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, _make_user, requires_env

pytestmark = requires_env

SGT = timezone(timedelta(hours=8))


def _cookie(auth_client, user):
    signed_in = auth_client.auth.sign_in_with_password({"email": user["email"], "password": user["password"]})
    return {"Cookie": f"sb_access_token={signed_in.session.access_token}"}


def _day(moment):
    return f"{moment.day} {moment:%b %Y}"


@pytest.fixture
def world(admin):
    """K (Coordinator), O (Organiser), Attendees A, W and X, and confirmed
    event P assigned to K, with one place, registration open and a pending
    cancellation request from O. All deleted afterwards."""
    users = {name: _make_user(admin, role) for name, role in (
        ("k", "event_coordinator"), ("o", "event_organiser"),
        ("a", "attendee"), ("w", "attendee"), ("x", "attendee"),
    )}
    now = datetime.now(SGT)
    start = now + timedelta(days=10)
    event_id = None
    try:
        event = admin.schema("events").table("events").insert({
            "organiser_id": users["o"]["id"], "assigned_coordinator_id": users["k"]["id"],
            "status": "confirmed", "name": f"spm-test S-69 {uuid.uuid4().hex[:8]}",
            "purpose": "Prove cancellation notifications",
            "start_date": start.date().isoformat(), "start_time": "18:00",
            "end_date": start.date().isoformat(), "end_time": "21:00",
            "expected_attendance": 1, "submitted_at": "2026-10-01T00:00:00Z",
            "decision": "approved", "decided_at": "2026-10-02T00:00:00Z",
            "safety_decision": "approved", "safety_officer_id": users["o"]["id"],
            "safety_decided_at": "2026-10-03T00:00:00Z",
            "registration_required": True,
            "registration_opens_at": (now - timedelta(days=1)).replace(tzinfo=None).isoformat(),
            "registration_closes_at": (now + timedelta(days=1)).replace(tzinfo=None).isoformat(),
            "cancellation_reason": "Speaker unavailable",
            "cancellation_requested_at": "2026-10-11T09:00:00Z",
            "cancellation_requested_by": users["o"]["id"],
        }).execute().data[0]
        event_id = event["id"]
        yield {**users, "event": event, "start": start}
    finally:
        if event_id:
            admin.schema("notifications").table("notifications").delete().eq("event_id", event_id).execute()
            admin.schema("registrations").table("registrations").delete().eq("event_id", event_id).execute()
            admin.schema("registrations").table("waiting_list").delete().eq("event_id", event_id).execute()
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        for user in users.values():
            admin.auth.admin.delete_user(user["id"])


def test_approving_a_cancellation_notifies_registered_and_waiting_attendees_once(admin, auth_client, world):
    k, a, w, x = (_cookie(auth_client, world[n]) for n in ("k", "a", "w", "x"))
    event = world["event"]
    event_id = event["id"]
    expected = (
        f"Event cancelled: {event['name']}, {_day(world['start'].date())}, "
        "6:00 pm – 9:00 pm. It will not take place."
    )

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:

        def cancelled(headers):
            inbox = api.get("/notifications", headers=headers)
            assert inbox.status_code == 200, inbox.text
            return [row for row in inbox.json()
                    if row["kind"] == "event_cancelled" and row["event_id"] == event_id]

        registered = api.post(f"/event-registrations/events/{event_id}/registration", headers=a)
        assert registered.status_code == 201, registered.text
        waiting = api.post(f"/event-registrations/events/{event_id}/waiting-list", headers=w)
        assert waiting.status_code == 201, waiting.text

        approved = api.post(f"/event-requests/{event_id}/cancellation-decision", headers=k,
                            json={"decision": "approved"})
        assert approved.status_code == 200, (
            f"{approved.text} -- check the S-69 block of notifications.sql is applied"
        )
        assert approved.json()["status"] == "cancelled"
        assert approved.json()["notified_attendees"] == 2

        for headers in (a, w):
            [row] = cancelled(headers)
            assert row["message"] == expected
            assert "Speaker unavailable" not in row["message"]
        assert cancelled(x) == []

        again = api.post(f"/event-requests/{event_id}/cancellation-decision", headers=k,
                         json={"decision": "approved"})
        assert again.status_code == 200, again.text
        assert len(cancelled(a)) == 1
