"""TC-E2E-247, TC-E2E-248 -- S-51: anyone reads a confirmed event's public
page; an Attendee registers while registration is open, and is told when it
isn't. TC-E2E-252 -- S-48: the registration then shows on the Attendee's
dashboard and on the Organiser's own event page. TC-E2E-256 -- S-49: the
Attendee's dashboard shows a confirmation of the registration.

What only a browser proves: the public routes need no session, Kong serves
the new composite, and an Attendee's place survives a page load."""

import re
import uuid
from datetime import datetime, timedelta, timezone

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env

SGT = timezone(timedelta(hours=8))
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _now():
    return datetime.now(SGT).replace(tzinfo=None, second=0, microsecond=0)


def _words(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    meridiem = "am" if moment.hour < 12 else "pm"
    return f"{moment.day} {MONTHS[moment.month - 1]} {moment.year}, {hour}:{moment:%M} {meridiem}"


def _confirmed_event(admin, organiser, name, *, opens, closes):
    start = _now() + timedelta(days=14)
    return admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "status": "confirmed",
        "name": name,
        "purpose": "Reconnect alumni with current students",
        "start_date": start.date().isoformat(),
        "start_time": "18:00",
        "end_date": start.date().isoformat(),
        "end_time": "21:00",
        "expected_attendance": 120,
        "submitted_at": "2026-10-01T00:00:00Z",
        "decision": "approved",
        "decided_at": "2026-10-02T00:00:00Z",
        "safety_decision": "approved",
        "safety_officer_id": organiser["id"],
        "safety_decided_at": "2026-10-03T00:00:00Z",
        "registration_required": True,
        "registration_opens_at": opens.isoformat(),
        "registration_closes_at": closes.isoformat(),
    }).execute().data[0]


# --- TC-E2E-247 -----------------------------------------------------------
def test_a_visitor_reads_a_confirmed_event_then_registers_as_an_attendee(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    venue_staff = make_user("venue_staff")
    attendee = make_user("attendee")
    suffix = uuid.uuid4().hex[:6]
    name = f"Alumni Evening {suffix}"
    hall = f"Seminar Room {suffix}"
    now = _now()
    event = _confirmed_event(
        admin, organiser, name, opens=now - timedelta(days=1), closes=now + timedelta(days=7)
    )
    venue = admin.schema("venues").table("venues").insert({
        "name": hall,
        "location": "Building A",
        "capacity": 200,
        "facilities": [],
        "accessibility": [],
        "room_layouts": ["theatre"],
        "operating_hours": [{"day": "fri", "open": "08:00:00", "close": "22:00:00"}],
        "created_by": venue_staff["id"],
    }).execute().data[0]
    admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"],
        "venue_id": venue["id"],
        "coordinator_id": coordinator["id"],
        "coordinator_name": "E2E Tester",
        "coordinator_email": coordinator["email"],
        "status": "confirmed",
        "decided_by": venue_staff["id"],
        "decided_at": "2026-10-03T00:00:00Z",
        "booking_date": event["start_date"],
        "start_time": "18:00",
        "end_time": "21:00",
        "event_name": name,
        "event_purpose": "Reconnect alumni with current students",
        "expected_attendance": 120,
        "venue_name": hall,
    }).execute()

    page.goto(f"/public/events/{event['id']}")
    expect(page.get_by_role("heading", name=name)).to_be_visible(timeout=20000)
    expect(page.get_by_text("Reconnect alumni with current students")).to_be_visible()
    expect(page.get_by_text(hall)).to_be_visible()
    period = (
        f"Registration opens {_words(now - timedelta(days=1))} "
        f"and closes {_words(now + timedelta(days=7))}."
    )
    expect(page.get_by_text(period)).to_be_visible()

    page.get_by_role("button", name="Register").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=20000)

    sign_in(attendee)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    page.goto(f"/public/events/{event['id']}")
    page.get_by_role("button", name="Register").click()
    expect(page.get_by_text("You're registered for this event.")).to_be_visible(timeout=20000)

    page.reload()
    expect(page.get_by_text("You're registered for this event.")).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Register")).to_have_count(0)


# --- TC-E2E-248 -----------------------------------------------------------
def test_an_attendee_is_told_registration_hasnt_opened_yet(admin, page, make_user, sign_in):
    organiser = make_user("event_organiser")
    attendee = make_user("attendee")
    now = _now()
    opens = now + timedelta(days=7)
    closes = now + timedelta(days=10)
    event = _confirmed_event(
        admin, organiser, f"Later Evening {uuid.uuid4().hex[:6]}",
        opens=opens, closes=closes,
    )

    sign_in(attendee)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    page.goto(f"/public/events/{event['id']}")
    message = (
        f"Registration hasn't opened yet. It's open from {_words(opens)} to {_words(closes)}."
    )
    expect(page.get_by_text(message)).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Register")).to_have_count(0)


# --- TC-E2E-252 -----------------------------------------------------------
def test_a_registration_shows_on_the_attendees_dashboard_and_the_organisers_event(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    attendee = make_user("attendee")
    admin.schema("users").table("users").update({"name": "S-48 E2E Attendee"}).eq(
        "id", attendee["id"]
    ).execute()
    now = _now()
    name = f"Careers Evening {uuid.uuid4().hex[:6]}"
    event = _confirmed_event(
        admin, organiser, name, opens=now - timedelta(days=1), closes=now + timedelta(days=7)
    )

    sign_in(attendee)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    mine = page.get_by_role("region", name="Your registrations")
    expect(mine.get_by_text("You haven't registered for any events yet.")).to_be_visible(
        timeout=20000
    )

    page.goto(f"/public/events/{event['id']}")
    page.get_by_role("button", name="Register").click()
    expect(page.get_by_text("You're registered for this event.")).to_be_visible(timeout=20000)

    page.goto("/dashboard")
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    link = mine.get_by_role("link", name=name)
    expect(link).to_be_visible(timeout=20000)
    expect(link).to_have_attribute("href", f"/public/events/{event['id']}")
    expect(mine.get_by_text(_words(datetime.fromisoformat(
        f"{event['start_date']}T18:00"
    )), exact=False)).to_be_visible()

    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=20000)
    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/"), timeout=20000)
    page.goto(f"/events/{event['id']}")
    attendees = page.get_by_role("region", name="Registered attendees")
    expect(attendees.get_by_text("1 attendee registered")).to_be_visible(timeout=20000)
    expect(attendees.get_by_text("S-48 E2E Attendee")).to_be_visible()
    expect(attendees.get_by_text(attendee["email"])).to_be_visible()


# --- TC-E2E-256 -----------------------------------------------------------
def test_an_attendee_sees_the_confirmation_on_their_dashboard_after_registering(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    attendee = make_user("attendee")
    admin.schema("users").table("users").update({"name": "S-49 E2E Attendee"}).eq(
        "id", attendee["id"]
    ).execute()
    now = _now()
    name = f"Welcome Evening {uuid.uuid4().hex[:6]}"
    event = _confirmed_event(
        admin, organiser, name, opens=now - timedelta(days=1), closes=now + timedelta(days=7)
    )

    sign_in(attendee)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    inbox = page.get_by_role("region", name="Notifications")
    expect(inbox.get_by_text("No notifications yet.")).to_be_visible(timeout=20000)

    page.goto(f"/public/events/{event['id']}")
    page.get_by_role("button", name="Register").click()
    expect(page.get_by_text("You're registered for this event.")).to_be_visible(timeout=20000)

    page.goto("/dashboard")
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    day = _words(datetime.fromisoformat(f"{event['start_date']}T18:00"))
    expect(inbox.get_by_text(
        f"Registration confirmed: {name}, {day} – 9:00 pm, venue to be confirmed. "
        f"Name: S-49 E2E Attendee. Email: {attendee['email']}."
    )).to_be_visible(timeout=20000)
