"""TC-E2E-210 -- a too-small venue is warned about and blocked (S-35).

TC-FRONTEND-036 covers the wording. This proves the warning appears on
selection and that Send request is disabled until a venue that fits is
chosen, which only a browser can show.
"""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


def _venue(name, capacity, created_by):
    return {
        "name": name,
        "location": "10 Anson Road",
        "capacity": capacity,
        "room_layouts": ["theatre"],
        "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
        "created_by": created_by,
    }


# --- TC-E2E-210 -----------------------------------------------------------
def test_a_too_small_venue_is_warned_about_and_blocked(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    small = f"spm-e2e Small {suffix}"
    large = f"spm-e2e Large {suffix}"

    # Attributed to the staff member and the organiser, so make_user's
    # teardown deletes them; the booking goes with the coordinator.
    venues = admin.schema("venues").table("venues")
    venues.insert(_venue(small, 80, staff["id"])).execute()
    venues.insert(_venue(large, 150, staff["id"])).execute()
    event = (
        admin.schema("events")
        .table("events")
        .insert(
            {
                "organiser_id": organiser["id"],
                "status": "planning",
                "assigned_coordinator_id": coordinator["id"],
                "name": f"spm-e2e Event {suffix}",
                "purpose": "Reconnect graduates with faculty",
                "start_date": "2026-11-12",
                "start_time": "09:00",
                "end_date": "2026-11-12",
                "end_time": "18:00",
                "expected_attendance": 100,
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
    page.goto(f"/coordinator/events/{event['id']}/request-venue")

    send = page.get_by_role("button", name="Send request")
    send.wait_for(timeout=20000)
    warning = f"{small} holds 80 people; this event expects 100. Choose a larger venue."
    assert page.get_by_text(warning).count() == 0
    assert send.is_enabled()

    venue_list = page.get_by_role("list", name="Venues")
    venue_list.get_by_role("listitem").filter(has_text=small).get_by_role("radio").check()
    page.get_by_text(warning).wait_for(timeout=20000)
    assert send.is_disabled()

    venue_list.get_by_role("listitem").filter(has_text=large).get_by_role("radio").check()
    page.get_by_text(warning).wait_for(state="detached", timeout=20000)
    assert send.is_enabled()

    page.get_by_label("From", exact=True).fill("09:00")
    page.get_by_label("To", exact=True).fill("12:00")
    send.click()
    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}$"), timeout=20000)
    page.get_by_text("Venue request sent to Venue Staff.").wait_for(timeout=20000)
