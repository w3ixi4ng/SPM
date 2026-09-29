"""TC-E2E-219 -- a Coordinator narrows the Venues tab with filters (S-34).

The matching rules are TC-FRONTEND-057 to 064. This proves the filters are
wired to the list on the dashboard, update it on every change, and clear.
"""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


def _hours(day, open_, close):
    return {"day": day, "open": f"{open_}:00", "close": f"{close}:00"}


# --- TC-E2E-219 -----------------------------------------------------------
def test_a_coordinator_narrows_the_venues_tab_with_filters(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    staff = make_user("venue_staff")
    suffix = uuid.uuid4().hex[:6]
    harbour = f"Harbour Hall {suffix}"
    studio = f"Studio B {suffix}"
    suite = f"Anson Suite {suffix}"

    # Attributed to the staff member, so make_user's teardown deletes them.
    for venue in (
        {
            "name": harbour, "location": "1 Harbourfront Walk", "capacity": 250,
            "room_layouts": ["theatre", "banquet"], "facilities": ["projector", "stage"],
            "accessibility": ["lift"],
            "operating_hours": [_hours("mon", "09:00", "18:00"), _hours("thu", "08:00", "20:00")],
        },
        {
            "name": studio, "location": "10 Anson Road", "capacity": 80,
            "room_layouts": ["classroom", "boardroom"], "facilities": ["projector"],
            "accessibility": [],
            "operating_hours": [_hours("thu", "08:00", "20:00")],
        },
        {
            "name": suite, "location": "12 Anson Road", "capacity": 150,
            "room_layouts": ["theatre", "cocktail"], "facilities": ["stage"],
            "accessibility": ["lift", "hearing_loop"],
            "operating_hours": [_hours("sat", "10:00", "16:00")],
        },
    ):
        admin.schema("venues").table("venues").insert({**venue, "created_by": staff["id"]}).execute()

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.get_by_role("tab", name="Venues").click()

    panel = page.locator("#panel-venues")
    ours = (harbour, studio, suite)

    def shown():
        # Other venues may exist in the test project; only ours are compared.
        items = panel.get_by_role("list", name="Venues").get_by_role("listitem")
        texts = items.all_inner_texts() if items.count() else []
        return [name for name in ours if any(name in text for text in texts)]

    def expect(names):
        page.wait_for_function(
            "([names, all]) => all.every(n => names.includes(n) === "
            "[...document.querySelectorAll('#panel-venues li')].some(li => li.innerText.includes(n)))",
            arg=[list(names), list(ours)],
            timeout=20000,
        )
        assert shown() == list(names)

    expect(ours)

    search = panel.get_by_label("Search by name or location")
    search.fill("anson")
    expect((studio, suite))

    panel.get_by_label("Holds at least").fill("100")
    expect((suite,))

    panel.get_by_role("group", name="Facilities").get_by_label("Stage", exact=True).check()
    expect((suite,))

    panel.get_by_label("Open on").fill("2026-11-12")
    expect(())

    panel.get_by_role("button", name="Clear filters").click()
    expect(ours)
    assert search.input_value() == ""
