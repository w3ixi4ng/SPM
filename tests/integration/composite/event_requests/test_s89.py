"""TC-EVENTREQUESTS-204 (S-89): through Kong, a venue closure only flags the
event's booking; the Coordinator then cancels it with a reason, which
releases every booking and hold, frees its equipment, and notifies the
Organiser (with the reason) and each registered or waiting Attendee once."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, _make_user, requires_env

pytestmark = requires_env

SGT = timezone(timedelta(hours=8))
REASON = "V1 is closed for repairs and no other hall fits."
ALL_WEEK = [
    {"day": day, "open": "08:00:00", "close": "23:00:00"}
    for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
]


def _cookie(auth_client, user):
    signed_in = auth_client.auth.sign_in_with_password({"email": user["email"], "password": user["password"]})
    return {"Cookie": f"sb_access_token={signed_in.session.access_token}"}


def _day(moment):
    return f"{moment.day} {moment:%b %Y}"


@pytest.fixture
def world(admin):
    """C (Coordinator), O (Organiser), S (Venue Staff), T (Technical Support),
    Attendees A, W and X; venues V1 and V2; equipment E (3 units). Confirmed
    event P owned by O and assigned to C, ten days out 18:00-21:00, with one
    place and registration open, a confirmed booking at V1, a held booking
    at V2 and a requirement for 2 x E. All deleted afterwards."""
    tag = uuid.uuid4().hex[:8]
    users = {name: _make_user(admin, role) for name, role in (
        ("c", "event_coordinator"), ("o", "event_organiser"), ("s", "venue_staff"),
        ("t", "technical_support"), ("a", "attendee"), ("w", "attendee"), ("x", "attendee"),
    )}
    c, o, s, t = (users[n] for n in "cost")
    now = datetime.now(SGT)
    day = (now + timedelta(days=10)).date().isoformat()
    venue_ids: list[str] = []
    item_id = event_id = None
    try:
        def venue(name):
            row = admin.schema("venues").table("venues").insert({
                "name": f"spm-test S89 {name} {tag}", "location": "10 Anson Road", "capacity": 300,
                "room_layouts": ["theatre"], "facilities": [], "operating_hours": ALL_WEEK,
                "created_by": s["id"],
            }).execute().data[0]
            venue_ids.append(row["id"])
            return row

        v1, v2 = venue("V1"), venue("V2")
        item_type = f"spm-test S89 Projector {tag}"
        item_id = admin.schema("equipment").table("equipment").insert({
            "type": item_type, "total_quantity": 3, "created_by": t["id"],
        }).execute().data[0]["id"]
        event = admin.schema("events").table("events").insert({
            "organiser_id": o["id"], "assigned_coordinator_id": c["id"],
            "status": "confirmed", "name": f"spm-test S-89 {tag}",
            "purpose": "Prove a Coordinator's cancellation",
            "start_date": day, "start_time": "18:00", "end_date": day, "end_time": "21:00",
            "expected_attendance": 1, "submitted_at": "2026-10-01T00:00:00Z",
            "decision": "approved", "decided_at": "2026-10-02T00:00:00Z",
            "safety_decision": "approved", "safety_officer_id": o["id"],
            "safety_decided_at": "2026-10-03T00:00:00Z",
            "registration_required": True,
            "registration_opens_at": (now - timedelta(days=1)).replace(tzinfo=None).isoformat(),
            "registration_closes_at": (now + timedelta(days=1)).replace(tzinfo=None).isoformat(),
        }).execute().data[0]
        event_id = event["id"]

        def booking(venue_row, status, **extra):
            return admin.schema("bookings").table("bookings").insert({
                "event_id": event_id, "venue_id": venue_row["id"], "coordinator_id": c["id"],
                "coordinator_name": "spm-test Coordinator", "coordinator_email": c["email"],
                "booking_date": day, "start_time": "18:00", "end_time": "21:00",
                "event_name": event["name"], "event_purpose": "Prove a Coordinator's cancellation",
                "expected_attendance": 1, "venue_name": venue_row["name"], "status": status, **extra,
            }).execute().data[0]

        v1_booking = booking(v1, "confirmed", decided_by=s["id"], decided_at="2026-10-02T00:00:00Z")
        # S-24: every hold has an expiry; far ahead, so it never lapses mid-test.
        booking(v2, "held", held_by=s["id"], held_at="2026-10-02T00:00:00Z",
                hold_expires_at="2030-01-01T00:00:00+00:00")
        admin.schema("equipment").table("requirements").insert({
            "event_id": event_id, "equipment_item_id": item_id,
            "required_quantity": 2, "recorded_by_coordinator_id": c["id"],
        }).execute()

        yield {**users, "event": event, "day": day, "v1": v1, "v1_booking": v1_booking,
               "item_type": item_type}
    finally:
        if event_id:
            admin.schema("notifications").table("notifications").delete().eq("event_id", event_id).execute()
            admin.schema("registrations").table("registrations").delete().eq("event_id", event_id).execute()
            admin.schema("registrations").table("waiting_list").delete().eq("event_id", event_id).execute()
            admin.schema("bookings").table("bookings").delete().eq("event_id", event_id).execute()
            admin.schema("equipment").table("requirements").delete().eq("event_id", event_id).execute()
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        for venue_id in venue_ids:
            admin.schema("bookings").table("blocks").delete().eq("venue_id", venue_id).execute()
            admin.schema("venues").table("venues").delete().eq("id", venue_id).execute()
        if item_id:
            admin.schema("equipment").table("equipment").delete().eq("id", item_id).execute()
        for user in users.values():
            admin.auth.admin.delete_user(user["id"])


def test_a_closure_flags_and_the_coordinators_cancel_releases_everything_and_notifies_once(
    admin, auth_client, world,
):
    c, o, s, t, a, w, x = (_cookie(auth_client, world[n]) for n in "costawx")
    event = world["event"]
    event_id = event["id"]
    day = world["day"]
    start = datetime.fromisoformat(day)
    organiser_message = (
        f"Your event {event['name']}, {_day(start)}, 6:00 pm – 9:00 pm, "
        f"was cancelled by your Event Coordinator: {REASON}"
    )
    attendee_message = (
        f"Event cancelled: {event['name']}, {_day(start)}, 6:00 pm – 9:00 pm. It will not take place."
    )

    def stored():
        return admin.schema("events").table("events").select("*").eq("id", event_id).execute().data[0]

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=30.0) as api:

        def inbox(headers, kind):
            response = api.get("/notifications", headers=headers)
            assert response.status_code == 200, response.text
            return [row for row in response.json() if row["event_id"] == event_id and row["kind"] == kind]

        # 1. A takes the one place; W waits.
        registered = api.post(f"/event-registrations/events/{event_id}/registration", headers=a)
        assert registered.status_code == 201, registered.text
        waiting = api.post(f"/event-registrations/events/{event_id}/waiting-list", headers=w)
        assert waiting.status_code == 201, waiting.text

        # 2. Venue Staff mark V1 unavailable for the evening.
        marked = api.post("/venue-bookings/blocks", headers=s, json={
            "venue_id": world["v1"]["id"], "start_date": day, "start_time": "08:00",
            "end_date": day, "end_time": "23:00", "reason": "maintenance",
        })
        assert marked.status_code == 201, marked.text
        assert [row["id"] for row in marked.json()["affected_bookings"]] == [world["v1_booking"]["id"]]

        # 3. AC1: nothing was cancelled -- the booking is only flagged.
        assert stored()["status"] == "confirmed"
        listed = api.get("/venue-bookings", headers=c, params={"event_id": event_id})
        assert listed.status_code == 200, listed.text
        [v1_row] = [row for row in listed.json() if row["id"] == world["v1_booking"]["id"]]
        assert v1_row["status"] == "confirmed"
        assert v1_row["requires_alternative_arrangements"] is True

        # 4. The Coordinator cancels with a reason.
        cancelled = api.post(f"/event-requests/{event_id}/coordinator-cancellation", headers=c,
                             json={"reason": REASON})
        assert cancelled.status_code == 200, (
            f"{cancelled.text} -- check the S-89 blocks of events.sql and notifications.sql ran"
        )
        body = cancelled.json()
        assert body["status"] == "cancelled"
        assert (body["released_bookings"], body["notified_attendees"], body["organiser_notified"]) == (2, 2, True)

        # 5. Recorded; no bookings or holds left; the equipment is free.
        row = stored()
        assert row["status"] == "cancelled"
        assert row["coordinator_cancellation_reason"] == REASON
        assert row["coordinator_cancelled_by"] == world["c"]["id"]
        left = admin.schema("bookings").table("bookings").select("id").eq("event_id", event_id).execute().data
        assert left == []
        equipment = api.get("/equipment-requirements/availability", headers=t, params={
            "start_date": day, "start_time": "18:00", "end_date": day, "end_time": "21:00",
            "type": world["item_type"], "quantity": 1,
        })
        assert equipment.status_code == 200, equipment.text
        [item] = equipment.json()["items"]
        assert (item["reserved"], item["available"]) == (0, 3)

        # 6. Who heard what.
        [told] = inbox(o, "event_cancelled_by_coordinator")
        assert told["message"] == organiser_message
        for headers in (a, w):
            [heard] = inbox(headers, "event_cancelled")
            assert heard["message"] == attendee_message
            assert REASON not in heard["message"]
        assert inbox(x, "event_cancelled") == []

        # 7. Cancelling again changes nothing and notifies no one twice.
        again = api.post(f"/event-requests/{event_id}/coordinator-cancellation", headers=c,
                         json={"reason": REASON})
        assert again.status_code == 200, again.text
        assert len(inbox(o, "event_cancelled_by_coordinator")) == 1
        assert len(inbox(a, "event_cancelled")) == 1
