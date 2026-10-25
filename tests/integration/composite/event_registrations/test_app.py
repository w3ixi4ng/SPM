"""TC-EVENTREGISTRATIONS-101..102. Run with the whole .env.test stack up."""

import uuid
from datetime import timedelta

import httpx

from .conftest import GATEWAY_BASE_URL, confirmed_event, requires_env, sgt_now

pytestmark = requires_env


# --- TC-EVENTREGISTRATIONS-101 --------------------------------------------
def test_public_view_blocked_attempt_and_a_real_registration(admin, attendee):
    organiser_id = str(uuid.uuid4())
    now = sgt_now()
    open_event = confirmed_event(
        admin, organiser_id, opens=now - timedelta(days=1), closes=now + timedelta(days=1)
    )
    later_event = confirmed_event(
        admin, organiser_id, opens=now + timedelta(days=7), closes=now + timedelta(days=8)
    )
    events = admin.schema("events").table("events")
    registrations = admin.schema("registrations").table("registrations")
    base = f"{GATEWAY_BASE_URL}/event-registrations/events"
    try:
        public = httpx.get(f"{base}/{open_event}", timeout=20)
        assert public.status_code == 200, public.text
        assert public.json()["registration_required"] is True
        assert public.json()["registration_opens_at"] is not None
        assert "organiser_id" not in public.json()

        early = httpx.post(f"{base}/{later_event}/registration", headers=attendee["headers"], timeout=20)
        assert early.status_code == 409, early.text
        assert early.json()["detail"].startswith("Registration hasn't opened yet. It's open from ")
        assert " to " in early.json()["detail"]

        taken = httpx.post(f"{base}/{open_event}/registration", headers=attendee["headers"], timeout=20)
        assert taken.status_code == 201, taken.text

        mine = httpx.get(f"{base}/{open_event}/registration", headers=attendee["headers"], timeout=20)
        assert mine.status_code == 200, mine.text
        assert mine.json()["registered"] is True
    finally:
        registrations.delete().in_("event_id", [open_event, later_event]).execute()
        events.delete().in_("id", [open_event, later_event]).execute()
    assert events.select("id").in_("id", [open_event, later_event]).execute().data == []
    assert registrations.select("id").in_("event_id", [open_event, later_event]).execute().data == []


# --- TC-EVENTREGISTRATIONS-102 --------------------------------------------
def test_a_registration_shows_for_the_attendee_and_for_the_events_organiser(admin, make_account):
    organiser = make_account("event_organiser", "spm-test S-48 organiser")
    other_organiser = make_account("event_organiser", "spm-test S-48 other organiser")
    attendee = make_account("attendee", "S-48 Test Attendee")
    now = sgt_now()
    event_id = confirmed_event(
        admin, organiser["id"], opens=now - timedelta(days=1), closes=now + timedelta(days=1)
    )
    events = admin.schema("events").table("events")
    registrations = admin.schema("registrations").table("registrations")
    base = f"{GATEWAY_BASE_URL}/event-registrations"
    try:
        taken = httpx.post(
            f"{base}/events/{event_id}/registration", headers=attendee["headers"], timeout=20
        )
        assert taken.status_code == 201, taken.text

        mine = httpx.get(f"{base}/me/registrations", headers=attendee["headers"], timeout=20)
        assert mine.status_code == 200, mine.text
        listed = [item for item in mine.json() if item["event_id"] == event_id]
        assert len(listed) == 1, mine.json()
        assert listed[0]["name"].startswith("spm-test S-51")
        assert listed[0]["registered_at"]

        seen = httpx.get(
            f"{base}/events/{event_id}/attendees", headers=organiser["headers"], timeout=20
        )
        assert seen.status_code == 200, seen.text
        assert seen.json()["count"] == 1
        (row,) = seen.json()["attendees"]
        assert row["attendee_id"] == attendee["id"]
        assert row["name"] == "S-48 Test Attendee"
        assert row["email"] == attendee["email"]

        hidden = httpx.get(
            f"{base}/events/{event_id}/attendees", headers=other_organiser["headers"], timeout=20
        )
        assert hidden.status_code == 404, hidden.text
    finally:
        registrations.delete().eq("event_id", event_id).execute()
        events.delete().eq("id", event_id).execute()
    assert events.select("id").eq("id", event_id).execute().data == []
    assert registrations.select("id").eq("event_id", event_id).execute().data == []
