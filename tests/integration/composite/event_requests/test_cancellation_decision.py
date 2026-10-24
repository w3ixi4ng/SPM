"""TC-EVENTREQUESTS-112 (S-61): approving a cancellation through Kong cancels
the event and frees its venue and equipment; declining keeps everything."""

import uuid

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, _make_user, requires_env

pytestmark = requires_env

DAY = "2026-11-12"  # a Thursday


def _cookie(auth_client, user):
    signed_in = auth_client.auth.sign_in_with_password({"email": user["email"], "password": user["password"]})
    return {"Cookie": f"sb_access_token={signed_in.session.access_token}"}


@pytest.fixture
def world(admin):
    """K (Coordinator), O (Organiser), S (Venue Staff), T (Technical Support),
    venue V, equipment item Q (1 unit), and two planning events assigned to K
    with pending cancellation requests: E1 holding a confirmed and a held
    booking of V and 1 × Q; E2 with nothing. All deleted afterwards."""
    tag = uuid.uuid4().hex[:8]
    users = {role: _make_user(admin, role) for role in (
        "event_coordinator", "event_organiser", "venue_staff", "technical_support",
    )}
    k, o, s, t = (users[r] for r in ("event_coordinator", "event_organiser", "venue_staff", "technical_support"))
    venue_id = item_id = None
    event_ids: list[str] = []
    try:
        venue_id = admin.schema("venues").table("venues").insert({
            "name": f"spm-test S61 Hall {tag}", "location": "10 Anson Road", "capacity": 300,
            "room_layouts": ["theatre"], "facilities": [],
            "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
            "created_by": s["id"],
        }).execute().data[0]["id"]
        item_type = f"spm-test S61 Projector {tag}"
        item_id = admin.schema("equipment").table("equipment").insert({
            "type": item_type, "total_quantity": 1, "created_by": t["id"],
        }).execute().data[0]["id"]

        def event(name):
            row = admin.schema("events").table("events").insert({
                "organiser_id": o["id"], "assigned_coordinator_id": k["id"], "status": "planning",
                "name": f"spm-test S61 {name} {tag}", "purpose": "Cancellation review",
                "start_date": DAY, "start_time": "09:00", "end_date": DAY, "end_time": "18:00",
                "expected_attendance": 100, "decision": "approved",
                "decided_at": "2026-10-01T00:00:00Z", "submitted_at": "2026-09-30T00:00:00Z",
                "cancellation_reason": "Keynote speaker withdrew",
                "cancellation_requested_at": "2026-10-11T09:00:00Z",
                "cancellation_requested_by": o["id"],
            }).execute().data[0]
            event_ids.append(row["id"])
            return row

        e1, e2 = event("E1"), event("E2")

        def booking(start, end, status, **extra):
            admin.schema("bookings").table("bookings").insert({
                "event_id": e1["id"], "venue_id": venue_id, "coordinator_id": k["id"],
                "coordinator_name": "spm-test Coordinator", "coordinator_email": k["email"],
                "booking_date": DAY, "start_time": start, "end_time": end,
                "event_name": e1["name"], "event_purpose": "Cancellation review",
                "expected_attendance": 100, "venue_name": "spm-test S61 Hall", "status": status, **extra,
            }).execute()

        booking("09:00", "12:00", "confirmed", decided_by=s["id"], decided_at="2026-10-02T00:00:00Z")
        # S-24: every hold has an expiry; far ahead, so it never lapses mid-test.
        booking("13:00", "15:00", "held", held_by=s["id"], held_at="2026-10-02T00:00:00Z",
                hold_expires_at="2030-01-01T00:00:00+00:00")
        admin.schema("equipment").table("requirements").insert({
            "event_id": e1["id"], "equipment_item_id": item_id,
            "required_quantity": 1, "recorded_by_coordinator_id": k["id"],
        }).execute()

        yield {"k": k, "o": o, "s": s, "t": t, "venue_id": venue_id,
               "item_type": item_type, "e1": e1, "e2": e2}
    finally:
        for event_id in event_ids:
            admin.schema("bookings").table("bookings").delete().eq("event_id", event_id).execute()
            admin.schema("equipment").table("requirements").delete().eq("event_id", event_id).execute()
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        if item_id:
            admin.schema("equipment").table("equipment").delete().eq("id", item_id).execute()
        if venue_id:
            admin.schema("venues").table("venues").delete().eq("id", venue_id).execute()
        for user in users.values():
            admin.auth.admin.delete_user(user["id"])


def test_approving_through_kong_cancels_the_event_and_frees_its_venue_and_equipment(admin, auth_client, world):
    k = _cookie(auth_client, world["k"])
    o = _cookie(auth_client, world["o"])
    s = _cookie(auth_client, world["s"])
    t = _cookie(auth_client, world["t"])
    e1, e2 = world["e1"]["id"], world["e2"]["id"]

    def stored(event_id):
        return admin.schema("events").table("events").select("*").eq("id", event_id).execute().data[0]

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        # 1. Approve E1.
        approved = api.post(f"/event-requests/{e1}/cancellation-decision", headers=k, json={"decision": "approved"})
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "cancelled"
        assert approved.json()["released_bookings"] == 2
        row = stored(e1)
        assert row["status"] == "cancelled"
        assert row["cancellation_decision"] == "approved"
        assert row["cancellation_decided_by"] == world["k"]["id"]
        assert row["cancellation_decided_at"]
        left = admin.schema("bookings").table("bookings").select("id").eq("event_id", e1).execute().data
        assert left == []

        # 2. The venue's day is free.
        calendar = api.get("/venue-bookings/availability", headers=s,
                           params={"venue_id": world["venue_id"], "from": DAY, "to": DAY})
        assert calendar.status_code == 200, calendar.text
        # Only bookings and blocks are entries; a free day has none.
        assert calendar.json()["entries"] == []

        # 3. The projector is free.
        equipment = api.get("/equipment-requirements/availability", headers=t, params={
            "start_date": DAY, "start_time": "09:00", "end_date": DAY, "end_time": "18:00",
            "type": world["item_type"], "quantity": 1,
        })
        assert equipment.status_code == 200, equipment.text
        [item] = equipment.json()["items"]
        assert (item["reserved"], item["available"]) == (0, 1)

        # 4. Decline E2: the event goes on.
        declined = api.post(f"/event-requests/{e2}/cancellation-decision", headers=k,
                            json={"decision": "declined", "reason": "Move the date instead"})
        assert declined.status_code == 200, declined.text
        row = stored(e2)
        assert row["status"] == "planning"
        assert row["cancellation_decision"] == "declined"
        assert row["cancellation_decision_reason"] == "Move the date instead"

        # 5. The Organiser may ask again, which clears the decline.
        again = api.post(f"/events/{e2}/cancellation-request", headers=o, json={"reason": "Still need to cancel"})
        assert again.status_code == 200, again.text
        row = stored(e2)
        assert row["cancellation_reason"] == "Still need to cancel"
        assert (row["cancellation_decision"], row["cancellation_decision_reason"],
                row["cancellation_decided_by"], row["cancellation_decided_at"]) == (None, None, None, None)
