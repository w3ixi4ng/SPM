"""TC-E2E-259 -- S-56: a registered Attendee sees when and where their event
is, and "to be confirmed" while a significant change is re-checked.

What only a browser proves: the dashboard card built from the real composite
through Kong shows the primary venue and nothing internal, and follows the
event's status on reload."""

import re
import uuid
from datetime import datetime, timedelta, timezone

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env

SGT = timezone(timedelta(hours=8))
WHEN = "4 Dec 2026, 6:00 pm to 9:00 pm"
PENDING = (
    "Details to be confirmed. The date, time and venue will show here once the "
    "event is confirmed again."
)
PURPOSE = "Reconnect alumni with current students"


def _event(admin, organiser, name):
    now = datetime.now(SGT).replace(tzinfo=None, second=0, microsecond=0)
    return admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "status": "confirmed",
        "name": name,
        "purpose": PURPOSE,
        "start_date": "2026-12-04",
        "start_time": "18:00",
        "end_date": "2026-12-04",
        "end_time": "21:00",
        "expected_attendance": 137,
        "submitted_at": "2026-10-01T00:00:00Z",
        "decision": "approved",
        "decided_at": "2026-10-02T00:00:00Z",
        "safety_decision": "approved",
        "safety_officer_id": organiser["id"],
        "safety_decided_at": "2026-10-03T00:00:00Z",
        "registration_required": True,
        "registration_opens_at": (now - timedelta(days=1)).isoformat(),
        "registration_closes_at": (now + timedelta(days=7)).isoformat(),
    }).execute().data[0]


def _confirmed_booking(admin, organiser, event, venue_name, submitted_at):
    """Venues and bookings are owned by the Organiser so the fixture's
    cleanup removes them."""
    venue_id = admin.schema("venues").table("venues").insert({
        "name": venue_name, "location": "10 Anson Road", "capacity": 300,
        "room_layouts": ["theatre"], "facilities": [], "operating_hours": [{"day": "fri", "open": "08:00:00", "close": "22:00:00"}],
        "created_by": organiser["id"],
    }).execute().data[0]["id"]
    admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"], "venue_id": venue_id, "coordinator_id": organiser["id"],
        "coordinator_name": "spm-e2e Coordinator", "coordinator_email": organiser["email"],
        "booking_date": "2026-12-04", "start_time": "18:00", "end_time": "21:00",
        "event_name": event["name"], "event_purpose": PURPOSE,
        "expected_attendance": 137, "venue_name": venue_name, "status": "confirmed",
        "decided_by": organiser["id"], "decided_at": "2026-10-04T00:00:00Z",
        "submitted_at": submitted_at,
    }).execute()


# --- TC-E2E-259 -----------------------------------------------------------
def test_an_attendee_sees_when_and_where_and_to_be_confirmed_while_rechecked(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    attendee = make_user("attendee")
    tag = uuid.uuid4().hex[:6]
    name = f"Alumni Evening {tag}"
    primary, other = f"Hall One {tag}", f"Room Two {tag}"
    event = _event(admin, organiser, name)
    # The second venue is inserted first: the order of rows is not what
    # decides the primary venue.
    _confirmed_booking(admin, organiser, event, other, "2026-10-03T00:00:00Z")
    _confirmed_booking(admin, organiser, event, primary, "2026-10-01T00:00:00Z")
    admin.schema("registrations").table("registrations").insert(
        {"event_id": event["id"], "attendee_id": attendee["id"]}
    ).execute()
    events = admin.schema("events").table("events")

    sign_in(attendee)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    card = page.get_by_role("region", name="Your registrations").get_by_role(
        "listitem"
    ).filter(has_text=name)
    expect(card.get_by_text(WHEN)).to_be_visible(timeout=20000)
    expect(card.get_by_text(primary)).to_be_visible()
    expect(card.get_by_text(other)).to_have_count(0)
    for internal in (PURPOSE, "137", organiser["email"], "spm-e2e Coordinator"):
        expect(card.get_by_text(internal)).to_have_count(0)

    # A significant S-18 change sends the event back for re-checking.
    events.update({
        "status": "planning", "safety_recheck_required": True, "safety_decision": None,
        "safety_decision_reason": None, "safety_officer_id": None, "safety_decided_at": None,
    }).eq("id", event["id"]).execute()
    page.reload()
    expect(card.get_by_text(PENDING)).to_be_visible(timeout=20000)
    expect(card.get_by_text(WHEN)).to_have_count(0)
    expect(card.get_by_text(primary)).to_have_count(0)
    expect(card.get_by_text(other)).to_have_count(0)

    events.update({
        "status": "confirmed", "safety_recheck_required": False, "safety_decision": "approved",
        "safety_officer_id": organiser["id"], "safety_decided_at": "2026-10-20T00:00:00Z",
    }).eq("id", event["id"]).execute()
    page.reload()
    expect(card.get_by_text(WHEN)).to_be_visible(timeout=20000)
    expect(card.get_by_text(primary)).to_be_visible()
    expect(card.get_by_text(PENDING)).to_have_count(0)
