"""TC-E2E-209 -- a Coordinator's venue request shows up on Venue Staff's dashboard (S-36).

The suitability rules are TC-VENUEBOOKINGS-008..016's job and are not
restaged here. This proves the request screen posts through Kong, and that Venue
Staff's dashboard renders the pending list after a fresh sign-in.
"""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


# --- TC-E2E-209 -----------------------------------------------------------
def test_a_coordinators_venue_request_shows_up_for_venue_staff(admin, page, make_user, sign_in):
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
                "venue": "Studio B",
                "decision": "approved",
                "decided_at": "2026-10-01T00:00:00+00:00",
                "submitted_at": "2026-09-30T00:00:00+00:00",
            }
        )
        .execute()
        .data[0]
    )

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")

    page.get_by_role("link", name="Request venue").click()
    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}/request-venue$"), timeout=20000)
    page.get_by_role("heading", name="Request a venue").wait_for(timeout=20000)
    page.get_by_label("Venue", exact=True).select_option(label=f"{venue_name} — holds 150")
    page.get_by_label("Date", exact=True).fill("2026-11-12")
    page.get_by_label("From", exact=True).fill("09:00")
    page.get_by_label("To", exact=True).fill("12:00")
    page.get_by_label("Room layout", exact=True).select_option(label="Theatre")
    page.get_by_role("button", name="Send request").click()

    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}$"), timeout=20000)
    page.get_by_text("Venue request sent to Venue Staff.").wait_for(timeout=20000)

    page.goto("/dashboard/event-coordinator")
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)

    sign_in(staff)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff"), timeout=20000)
    pending = page.get_by_role("list", name="Pending booking requests")
    row = pending.get_by_role("listitem").filter(has_text=event_name)
    row.wait_for(timeout=20000)
    for text in (venue_name, "12 Nov 2026", "09:00–12:00", "120 expected", "Theatre", "E2E Tester", "Pending"):
        row.get_by_text(text, exact=False).first.wait_for()
