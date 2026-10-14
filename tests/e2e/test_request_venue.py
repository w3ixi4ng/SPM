"""TC-E2E-209 -- a Coordinator's venue request stays on the event and shows up for Venue Staff (S-36).

The suitability rules are TC-VENUEBOOKINGS-008..016's job and are not
restaged here. This proves the request screen posts through Kong, and that Venue
Staff's dashboard renders the pending list after a fresh sign-in.
"""

import re
import uuid

from .conftest import open_request, requires_env

pytestmark = requires_env


# --- TC-E2E-209 -----------------------------------------------------------
def test_a_coordinators_venue_request_stays_on_the_event_and_shows_up_for_venue_staff(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    venue_name = f"spm-e2e Venue {suffix}"
    event_name = f"spm-e2e Event {suffix}"

    # Attributed to the staff member and the organiser, so make_user's
    # teardown deletes both; the booking goes with the coordinator.
    admin.schema("venues").table("venues").insert(
        {
            "name": venue_name,
            "location": "10 Anson Road",
            "capacity": 150,
            "room_layouts": ["theatre"],
            "facilities": ["projector"],
            "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
            "created_by": staff["id"],
        }
    ).execute()
    event = (
        admin.schema("events")
        .table("events")
        .insert(
            {
                "organiser_id": organiser["id"],
                "status": "planning",
                "assigned_coordinator_id": coordinator["id"],
                "name": event_name,
                "purpose": "Reconnect graduates with faculty",
                "start_date": "2026-11-12",
                "start_time": "09:00",
                "end_date": "2026-11-12",
                "end_time": "18:00",
                "expected_attendance": 120,
                "room_layout": "theatre",
                "required_facilities": ["projector"],
                "decision": "approved",
                "decided_at": "2026-10-01T00:00:00+00:00",
                "submitted_at": "2026-09-30T00:00:00+00:00",
            }
        )
        .execute()
        .data[0]
    )

    sign_in(coordinator)
    # The coordinator's own dashboard, not just any /dashboard URL: the app
    # passes through /dashboard while it resolves the session, and leaving
    # before that settles can open the next page signed out.
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")

    page.get_by_role("link", name="Request venue").click()
    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}/request-venue$"), timeout=20000)
    page.get_by_role("heading", name="Request a venue").wait_for(timeout=20000)
    needs = page.get_by_role("region", name="What the event needs")
    needs.get_by_text("Theatre").wait_for(timeout=20000)
    needs.get_by_text("Projector").wait_for()
    assert needs.locator("input, select, textarea").count() == 0
    venue_row = page.get_by_role("list", name="Venues").get_by_role("listitem").filter(has_text=venue_name)
    venue_row.get_by_text("Fits", exact=True).wait_for(timeout=20000)
    venue_row.get_by_role("radio").check()
    page.get_by_label("Date", exact=True).fill("2026-11-12")
    page.get_by_label("From", exact=True).fill("09:00")
    page.get_by_label("To", exact=True).fill("12:00")
    page.get_by_role("button", name="Send request").click()

    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}$"), timeout=20000)
    page.get_by_text("Venue request sent to Venue Staff.").wait_for(timeout=20000)

    page.reload()
    sent = page.get_by_role("list", name="Venue requests sent")
    sent.wait_for(timeout=20000)
    assert page.get_by_text("Venue request sent to Venue Staff.").count() == 0
    sent_row = sent.get_by_role("listitem").filter(has_text=venue_name)
    for text in ("12 Nov 2026", "09:00–12:00", "Pending"):
        sent_row.get_by_text(text, exact=False).first.wait_for()

    page.goto("/dashboard/event-coordinator")
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)

    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff"), timeout=20000)
    pending = page.get_by_role("list", name="Pending booking requests")
    row = pending.get_by_role("listitem").filter(has_text=event_name)
    row.wait_for(timeout=20000)
    # S-75: the dashboard row is compact; the full request is on its own page.
    for text in (venue_name, "12 Nov 2026", "09:00–12:00", "Pending"):
        row.get_by_text(text, exact=False).first.wait_for()
    open_request(page, event_name)
    for text in (venue_name, "12 Nov 2026", "09:00–12:00", "120", "Theatre", "E2E Tester", "Pending"):
        page.get_by_text(text, exact=False).first.wait_for()
