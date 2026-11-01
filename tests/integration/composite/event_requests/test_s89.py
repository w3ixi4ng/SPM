"""TC-EVENTREQUESTS-450..451 (S-89): through Kong, against real Events,
Bookings, Venues, Registrations, Notifications and Equipment.

Needs the S-89 blocks of events.sql and bookings.sql on the test project, and
event_requests able to reach venue_bookings (VENUE_BOOKINGS_SERVICE_URL, which
docker-compose.yml defaults).
"""

import uuid
from datetime import date, timedelta

import httpx
import pytest

from .conftest import GATEWAY_BASE_URL, _make_user, requires_env

pytestmark = requires_env

DAY = date.today() + timedelta(days=21)
WEEKDAY = DAY.strftime("%a").lower()
REASON = "spm-test Hall closed for structural repairs"
ALTERNATIVES = "spm-test Discussed two halls with the Organiser; neither fits"
NOT_AFFECTED = (
    "None of this event's venue bookings is affected by an unavailable venue, "
    "so it can't be cancelled here."
)


def _cookie(auth_client, user):
    signed_in = auth_client.auth.sign_in_with_password({"email": user["email"], "password": user["password"]})
    return {"Cookie": f"sb_access_token={signed_in.session.access_token}"}


@pytest.fixture
def world(admin):
    """Coordinators K and D, Organiser O, Venue Staff S, Technical Support T,
    Attendees A1, A2 (places) and W1 (waiting). Venues V1–V3, equipment item Q
    (10 units). Confirmed event E: confirmed bookings at V1 and V2, a pending
    replacement for V1 at V3, a requirement for 4 × Q. Planning event G: one
    confirmed booking at V2 that nothing affects. All deleted afterwards."""
    tag = uuid.uuid4().hex[:8]
    names = {"k": "event_coordinator", "d": "event_coordinator", "o": "event_organiser",
             "s": "venue_staff", "t": "technical_support",
             "a1": "attendee", "a2": "attendee", "w1": "attendee"}
    users = {name: _make_user(admin, role) for name, role in names.items()}
    venue_ids: list[str] = []
    event_ids: list[str] = []
    item_id = None
    try:
        def venue(label):
            row = admin.schema("venues").table("venues").insert({
                "name": f"spm-test S89 {label} {tag}", "location": "10 Anson Road", "capacity": 300,
                "room_layouts": ["theatre"], "facilities": [],
                "operating_hours": [{"day": WEEKDAY, "open": "07:00:00", "close": "23:00:00"}],
                "created_by": users["s"]["id"],
            }).execute().data[0]
            venue_ids.append(row["id"])
            return row

        v1, v2, v3 = venue("V1"), venue("V2"), venue("V3")
        item_type = f"spm-test S89 Projector {tag}"
        item_id = admin.schema("equipment").table("equipment").insert({
            "type": item_type, "total_quantity": 10, "created_by": users["t"]["id"],
        }).execute().data[0]["id"]

        def event(label, status, **extra):
            row = admin.schema("events").table("events").insert({
                "organiser_id": users["o"]["id"], "assigned_coordinator_id": users["k"]["id"],
                "status": status, "name": f"spm-test S89 {label} {tag}", "purpose": "Venue unavailability",
                "start_date": DAY.isoformat(), "start_time": "09:00",
                "end_date": DAY.isoformat(), "end_time": "21:00", "expected_attendance": 100,
                "submitted_at": "2026-10-01T00:00:00Z", "decision": "approved",
                "decided_at": "2026-10-02T00:00:00Z", **extra,
            }).execute().data[0]
            event_ids.append(row["id"])
            return row

        e = event("E", "confirmed", safety_decision="approved", safety_officer_id=users["s"]["id"],
                  safety_decided_at="2026-10-03T00:00:00Z")
        g = event("G", "planning")

        def booking(event_row, venue_row, start, end, status, **extra):
            values = {
                "event_id": event_row["id"], "venue_id": venue_row["id"], "coordinator_id": users["k"]["id"],
                "coordinator_name": "spm-test Coordinator", "coordinator_email": users["k"]["email"],
                "booking_date": DAY.isoformat(), "start_time": start, "end_time": end,
                "event_name": event_row["name"], "event_purpose": "Venue unavailability",
                "expected_attendance": 100, "venue_name": venue_row["name"], "status": status, **extra,
            }
            if status == "confirmed":
                values.update(decided_by=users["s"]["id"], decided_at="2026-10-04T00:00:00Z")
            return admin.schema("bookings").table("bookings").insert(values).execute().data[0]

        b1 = booking(e, v1, "18:00", "21:00", "confirmed")
        booking(e, v2, "09:00", "12:00", "confirmed")
        booking(e, v3, "18:00", "21:00", "pending", replaces_booking_id=b1["id"])
        booking(g, v2, "14:00", "16:00", "confirmed")
        admin.schema("equipment").table("requirements").insert({
            "event_id": e["id"], "equipment_item_id": item_id,
            "required_quantity": 4, "recorded_by_coordinator_id": users["k"]["id"],
        }).execute()
        for name in ("a1", "a2"):
            admin.schema("registrations").table("registrations").insert(
                {"event_id": e["id"], "attendee_id": users[name]["id"]}).execute()
        admin.schema("registrations").table("waiting_list").insert(
            {"event_id": e["id"], "attendee_id": users["w1"]["id"]}).execute()

        yield {**users, "e": e, "g": g, "v1": v1, "item_type": item_type}
    finally:
        for event_id in event_ids:
            admin.schema("notifications").table("notifications").delete().eq("event_id", event_id).execute()
            admin.schema("registrations").table("registrations").delete().eq("event_id", event_id).execute()
            admin.schema("registrations").table("waiting_list").delete().eq("event_id", event_id).execute()
            admin.schema("bookings").table("bookings").delete().eq("event_id", event_id).execute()
            admin.schema("bookings").table("closed_events").delete().eq("event_id", event_id).execute()
            admin.schema("equipment").table("requirements").delete().eq("event_id", event_id).execute()
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        for venue_id in venue_ids:
            admin.schema("bookings").table("blocks").delete().eq("venue_id", venue_id).execute()
            admin.schema("venues").table("venues").delete().eq("id", venue_id).execute()
        if item_id:
            admin.schema("equipment").table("equipment").delete().eq("id", item_id).execute()
        for user in users.values():
            admin.auth.admin.delete_user(user["id"])


def _stored(admin, event_id):
    return admin.schema("events").table("events").select("*").eq("id", event_id).execute().data[0]


def _bookings(admin, event_id):
    return admin.schema("bookings").table("bookings").select("*").eq("event_id", event_id).execute().data


def _notified(admin, event_id, recipient_id):
    return (
        admin.schema("notifications").table("notifications").select("*")
        .eq("event_id", event_id).eq("recipient_id", recipient_id).eq("kind", "event_cancelled")
        .execute().data
    )


def _body(event):
    return {"reason": REASON, "alternatives_considered": ALTERNATIVES,
            "expected_version": event.get("edit_version") or 0}


def _mark_v1_unavailable(api, staff, world):
    marked = api.post("/venue-bookings/blocks", headers=staff, json={
        "venue_id": world["v1"]["id"], "start_date": DAY.isoformat(), "start_time": "08:00",
        "end_date": (DAY + timedelta(days=1)).isoformat(), "end_time": "08:00",
        "reason": "maintenance", "note": "spm-test S89 repairs",
    })
    assert marked.status_code == 201, marked.text


# --- TC-EVENTREQUESTS-450 ----------------------------------------------------
def test_an_affected_two_venue_event_is_cancelled_with_everything_released_and_announced(
    admin, auth_client, world,
):
    k, s, t = (_cookie(auth_client, world[name]) for name in ("k", "s", "t"))
    e = world["e"]

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=30.0) as api:
        _mark_v1_unavailable(api, s, world)

        # AC1: nothing is cancelled or released automatically.
        assert _stored(admin, e["id"])["status"] == "confirmed"
        assert {row["status"] for row in _bookings(admin, e["id"])} == {"confirmed", "pending"}

        cancelled = api.post(f"/event-requests/{e['id']}/venue-cancellation", headers=k, json=_body(e))
        assert cancelled.status_code == 200, (
            f"{cancelled.text} -- check the S-89 SQL is applied and event_requests has VENUES_SERVICE_URL"
        )
        body = cancelled.json()
        assert body["released_bookings"] == 3
        assert body["notified_attendees"] == 3
        assert body["cancellation_completed"] is True

        row = _stored(admin, e["id"])
        assert row["status"] == "cancelled"
        assert row["venue_cancellation_reason"] == REASON
        assert row["venue_cancellation_completed_at"]
        statuses = [booking["status"] for booking in _bookings(admin, e["id"])]
        assert sorted(statuses) == ["released", "released", "released"]
        [closure] = admin.schema("bookings").table("closed_events").select("state") \
            .eq("event_id", e["id"]).execute().data
        assert closure["state"] == "closed"
        [entry] = admin.schema("events").table("event_history").select("*").eq("event_id", e["id"]) \
            .eq("action", "cancelled_venue_unavailable").execute().data
        assert entry["details"]["reason"] == REASON
        assert entry["actor_id"] == world["k"]["id"]

        [organiser_row] = _notified(admin, e["id"], world["o"]["id"])
        assert REASON in organiser_row["message"]
        for name in ("a1", "a2", "w1"):
            [attendee_row] = _notified(admin, e["id"], world[name]["id"])
            assert attendee_row["message"].endswith("It will not take place.")

        equipment = api.get("/equipment-requirements/availability", headers=t, params={
            "start_date": DAY.isoformat(), "start_time": "09:00",
            "end_date": DAY.isoformat(), "end_time": "21:00", "type": world["item_type"],
        })
        assert equipment.status_code == 200, equipment.text
        [item] = equipment.json()["items"]
        assert item["available"] == 10

        again = api.post(f"/event-requests/{e['id']}/venue-cancellation", headers=k, json=_body(e))
        assert again.status_code == 200, again.text
        assert len(_notified(admin, e["id"], world["o"]["id"])) == 1
        for name in ("a1", "a2", "w1"):
            assert len(_notified(admin, e["id"], world[name]["id"])) == 1


# --- TC-EVENTREQUESTS-451 ----------------------------------------------------
def test_unaffected_or_unassigned_events_stay_untouched(admin, auth_client, world):
    k, d, s = (_cookie(auth_client, world[name]) for name in ("k", "d", "s"))
    e, g = world["e"], world["g"]

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=30.0) as api:
        _mark_v1_unavailable(api, s, world)

        refused = api.post(f"/event-requests/{g['id']}/venue-cancellation", headers=k, json=_body(g))
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"] == NOT_AFFECTED

        stranger = api.post(f"/event-requests/{e['id']}/venue-cancellation", headers=d, json=_body(e))
        assert stranger.status_code == 404, stranger.text

    assert _stored(admin, g["id"])["status"] == "planning"
    assert _stored(admin, e["id"])["status"] == "confirmed"
    assert [row["status"] for row in _bookings(admin, g["id"])] == ["confirmed"]
    assert all(row["status"] != "released" for row in _bookings(admin, e["id"]))
    # Refused attempts leave the bookings open.
    for event in (e, g):
        assert admin.schema("bookings").table("closed_events").select("event_id") \
            .eq("event_id", event["id"]).execute().data == []
    for event in (e, g):
        rows = admin.schema("notifications").table("notifications").select("id") \
            .eq("event_id", event["id"]).eq("kind", "event_cancelled").execute().data
        assert rows == []
