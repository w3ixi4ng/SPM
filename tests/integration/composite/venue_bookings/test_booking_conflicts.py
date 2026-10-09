"""TC-VENUEBOOKINGS-108 (S-76): an overlapping approval is refused by name, and
a confirmed clash stays listed for review, through Kong."""

import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env
from .test_availability import more_events  # noqa: F401 -- a fixture
from .test_setup_turnaround import DAY, seed

pytestmark = requires_env


def test_an_overlapping_approval_is_refused_by_name_and_the_clash_stays_listed(
    admin, auth_client, world, more_events,
):
    staff = cookie_for(auth_client, world["staff"])
    event_b, event_c = more_events
    # Valid at 0/0: none of these overlap by their own times.
    a = seed(admin, world, world["event_id"], "confirmed", "10:00", "12:00")
    c = seed(admin, world, event_c, "confirmed", "13:00", "14:00")
    b = seed(admin, world, event_b, "pending", "12:00", "12:45")

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=20.0) as api:
        # 1. Staff set the venue's times.
        saved = api.patch(f"/venues/{world['venue_id']}", headers=staff,
                          json={"setup_minutes": 30, "turnaround_minutes": 45})
        assert saved.status_code == 200, saved.text

        # 2. Approving B is refused, naming A and its occupied period. The
        #    venue name is the one saved on the booking, as in every refusal.
        refused = api.post(f"/venue-bookings/{b['id']}/decision", headers=staff, json={"decision": "approved"})
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"] == (
            f"Can't confirm this booking: it overlaps {a['event_name']} (confirmed), which occupies "
            f"{a['venue_name']} on 12 Nov 2026 from 09:30 to 12:45 "
            "(event 10:00–12:00, 30 min setup, 45 min turnaround)."
        )

        # 3. The A-C pair, both confirmed, is listed for review.
        listed = api.get("/venue-bookings/clashes", headers=staff)
        assert listed.status_code == 200, listed.text
        [ours] = [venue for venue in listed.json()["venues"] if venue["venue_id"] == world["venue_id"]]
        assert [{pair["first"]["id"], pair["second"]["id"]} for pair in ours["pairs"]] == [{a["id"], c["id"]}]

    stored = admin.schema("bookings").table("bookings").select("id,status").in_(
        "id", [a["id"], b["id"], c["id"]]).execute().data
    assert {row["id"]: row["status"] for row in stored} == {
        a["id"]: "confirmed", b["id"]: "pending", c["id"]: "confirmed",
    }
    assert DAY == "2026-11-12"
