"""TC-E2E-205 and TC-E2E-206 -- adding and viewing venues (S-27).

Browser -> Kong -> venues service -> the `venues` schema and back, and the one
check that `frontend/src/lib/access.js` agrees with the venues service's
authorization.py on who may add a venue and who may only look.
"""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


# --- TC-E2E-205 -----------------------------------------------------------
def test_venue_staff_add_a_venue_and_see_it_listed(page, make_user, sign_in):
    user = make_user("venue_staff")
    sign_in(user)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)

    name = f"spm-e2e Venue {uuid.uuid4().hex[:6]}"

    page.get_by_role("link", name="Add venue").click()
    page.wait_for_url(re.compile(r"/venues/new$"), timeout=20000)
    form = page.get_by_role("form", name="New venue")
    form.wait_for(timeout=20000)

    form.locator("#name").fill(name)
    form.locator("#location").fill("1 Harbourfront Walk, Singapore 098585")
    form.locator("#capacity").fill("250")
    form.locator("#description").fill("Waterfront hall")

    for label in ("Projector", "Wi-Fi", "Wheelchair access", "Theatre", "Banquet"):
        form.get_by_label(label, exact=True).check()

    form.get_by_label("Monday", exact=True).check()
    form.get_by_label("Monday opening time").fill("09:00")
    form.get_by_label("Monday closing time").fill("18:00")

    form.get_by_role("button", name="Save venue").click()

    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=30000)
    page.get_by_text("Venue saved.").wait_for(timeout=20000)

    # Really stored, not just echoed: a fresh load reads it back through Kong.
    page.reload()
    row = page.get_by_role("list", name="Venues").get_by_role("listitem").filter(has_text=name)
    row.wait_for(timeout=20000)
    row.get_by_text("Capacity 250").wait_for(timeout=20000)


# --- TC-E2E-206 -----------------------------------------------------------
def test_event_coordinator_can_view_but_not_add_venues(admin, page, make_user, sign_in):
    staff = make_user("venue_staff")
    coordinator = make_user("event_coordinator")
    name = f"spm-e2e Venue {uuid.uuid4().hex[:6]}"
    # Attributed to the staff user, so make_user's teardown deletes it.
    admin.schema("venues").table("venues").insert(
        {
            "name": name,
            "location": "10 Anson Road, Singapore 079903",
            "capacity": 30,
            "room_layouts": ["boardroom"],
            "operating_hours": [{"day": "tue", "open": "08:00", "close": "17:00"}],
            "created_by": staff["id"],
        }
    ).execute()

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)

    page.get_by_role("list", name="Venues").get_by_text(name).wait_for(timeout=20000)
    assert page.get_by_role("link", name="Add venue").count() == 0

    # Typed straight into the address bar: the add page is refused too.
    page.goto("/venues/new")
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
