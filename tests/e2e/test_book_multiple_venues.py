"""TC-E2E-232 -- a Coordinator adds a second venue to one event and sees both (S-79).

The per-booking checks are TC-VENUEBOOKINGS-061..066 and 109's job and are not
restaged here. This proves the "Add another venue" link reaches the request
screen through Kong, and that both requests survive a reload on the event.
"""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


def add_venue(admin, staff, name, capacity):
    # Attributed to the staff member, so make_user's teardown deletes it.
    admin.schema("venues").table("venues").insert(
        {
            "name": name,
            "location": "10 Anson Road",
            "capacity": capacity,
            "room_layouts": ["theatre"],
            "facilities": ["projector"],
            "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
            "created_by": staff["id"],
        }
    ).execute()


def request_venue(page, event_id, venue_name, start, end):
    page.wait_for_url(re.compile(rf"/coordinator/events/{event_id}/request-venue$"), timeout=20000)
    venue_row = page.get_by_role("list", name="Venues").get_by_role("listitem").filter(has_text=venue_name)
    venue_row.get_by_text("Fits", exact=True).wait_for(timeout=20000)
    venue_row.get_by_role("radio").check()
    page.get_by_label("Date", exact=True).fill("2026-11-12")
    page.get_by_label("From", exact=True).fill(start)
    page.get_by_label("To", exact=True).fill(end)
    page.get_by_role("button", name="Send request").click()
    page.wait_for_url(re.compile(rf"/coordinator/events/{event_id}$"), timeout=20000)
    page.get_by_text("Venue request sent to Venue Staff.").wait_for(timeout=20000)


# --- TC-E2E-232 -----------------------------------------------------------
def test_a_coordinator_adds_a_second_venue_and_sees_both_with_their_status(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    hall = f"spm-e2e Hall {suffix}"
    studio = f"spm-e2e Studio {suffix}"
    add_venue(admin, staff, hall, 300)
    add_venue(admin, staff, studio, 150)
    event = (
        admin.schema("events")
        .table("events")
        .insert(
            {
                "organiser_id": organiser["id"],
                "status": "planning",
                "assigned_coordinator_id": coordinator["id"],
                "name": f"spm-e2e Event {suffix}",
                "purpose": "Annual conference with breakouts",
                "start_date": "2026-11-12",
                "start_time": "08:00",
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
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")

    page.get_by_role("link", name="Request venue").click()
    request_venue(page, event["id"], hall, "09:00", "17:00")

    page.get_by_role("link", name="Add another venue").click()
    request_venue(page, event["id"], studio, "13:00", "15:00")

    page.reload()
    sent = page.get_by_role("list", name="Venue requests sent")
    sent.wait_for(timeout=20000)
    assert sent.get_by_role("listitem").count() == 2
    for venue_name, times in ((hall, "09:00–17:00"), (studio, "13:00–15:00")):
        row = sent.get_by_role("listitem").filter(has_text=venue_name)
        for text in ("12 Nov 2026", times, "Pending"):
            row.get_by_text(text, exact=False).first.wait_for()
    page.get_by_role("link", name="Add another venue").wait_for()
