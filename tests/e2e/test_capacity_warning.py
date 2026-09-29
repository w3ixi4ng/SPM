"""TC-E2E-210 -- a venue that doesn't suit the event is warned about and blocked (S-35).

TC-FRONTEND-039 covers the wording. This proves the warning appears on
selection and that Send request is disabled until a venue that fits is
chosen, which only a browser can show.
"""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


def _venue(name, capacity, facilities, created_by):
    return {
        "name": name,
        "location": "10 Anson Road",
        "capacity": capacity,
        "facilities": facilities,
        "room_layouts": ["theatre"],
        "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
        "created_by": created_by,
    }


# --- TC-E2E-210 -----------------------------------------------------------
def test_a_venue_that_does_not_suit_the_event_is_warned_about_and_blocked(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    small = f"spm-e2e Small {suffix}"
    bare = f"spm-e2e Bare {suffix}"
    large = f"spm-e2e Large {suffix}"

    # Attributed to the staff member and the organiser, so make_user's
    # teardown deletes them; the booking goes with the coordinator.
    venues = admin.schema("venues").table("venues")
    venues.insert(_venue(small, 80, ["projector"], staff["id"])).execute()
    venues.insert(_venue(bare, 150, [], staff["id"])).execute()
    venues.insert(_venue(large, 150, ["projector"], staff["id"])).execute()
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
    page.goto(f"/coordinator/events/{event['id']}/request-venue")

    send = page.get_by_role("button", name="Send request")
    send.wait_for(timeout=20000)
    warning = page.locator("#venue-warning")
    assert warning.count() == 0
    assert send.is_enabled()

    # S-34: the list opens filtered to what the event needs, so only the
    # venue that fits is shown until the filters are cleared.
    venue_list = page.get_by_role("list", name="Venues")
    venue_list.get_by_role("listitem").filter(has_text=large).wait_for(timeout=20000)
    assert venue_list.get_by_role("listitem").filter(has_text=small).count() == 0
    assert venue_list.get_by_role("listitem").filter(has_text=bare).count() == 0
    page.get_by_role("button", name="Clear filters").click()
    venue_list.get_by_role("listitem").filter(has_text=small).wait_for(timeout=20000)
    venue_list.get_by_role("listitem").filter(has_text=bare).wait_for(timeout=20000)

    def choose(name):
        venue_list.get_by_role("listitem").filter(has_text=name).get_by_role("radio").check()

    choose(small)
    warning.wait_for(timeout=20000)
    assert small in warning.inner_text()
    assert "Too small: holds 80, event expects 100" in warning.inner_text()
    assert send.is_disabled()

    choose(bare)
    warning.filter(has_text=bare).wait_for(timeout=20000)
    assert "Missing: Projector" in warning.inner_text()
    assert send.is_disabled()

    choose(large)
    warning.wait_for(state="detached", timeout=20000)
    assert send.is_enabled()

    page.get_by_label("From", exact=True).fill("09:00")
    page.get_by_label("To", exact=True).fill("12:00")
    send.click()
    page.wait_for_url(re.compile(rf"/coordinator/events/{event['id']}$"), timeout=20000)
    page.get_by_text("Venue request sent to Venue Staff.").wait_for(timeout=20000)
