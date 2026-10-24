"""TC-EVENTREGISTRATIONS-101. Run with the whole .env.test stack up."""

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
        assert early.json()["detail"].startswith("Registration opens on ")

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
