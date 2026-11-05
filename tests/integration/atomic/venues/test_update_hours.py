"""TC-VENUES-105 (S-28 reopened): edited opening hours against the real table."""
import uuid

import httpx

from .conftest import BASE_URL, requires_env

pytestmark = requires_env

WEEKDAYS = [{"day": d, "open": "08:00:00", "close": "20:00:00"} for d in ("mon", "tue", "wed", "thu", "fri")]


def test_edited_opening_hours_are_stored_and_read_back(admin, make_session, venue_ids):
    staff = make_session("venue_staff")
    venue = admin.schema("venues").table("venues").insert({
        "name": f"spm-test S28 {uuid.uuid4().hex[:8]}", "location": "10 Anson Road", "capacity": 50,
        "room_layouts": ["theatre"], "operating_hours": WEEKDAYS, "created_by": staff["user_id"],
    }).execute().data[0]
    venue_ids.append(venue["id"])

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=staff["headers"]) as api:
        updated = api.patch(f"/venues/{venue['id']}",
                            json={"operating_hours": [{"day": "thu", "open": "10:00", "close": "16:00"}]})
        assert updated.status_code == 200, updated.text
        read = api.get(f"/venues/{venue['id']}")

    assert read.status_code == 200, read.text
    body = read.json()
    assert body["operating_hours"] == [{"day": "thu", "open": "10:00:00", "close": "16:00:00"}]
    for field in ("name", "location", "capacity", "room_layouts", "setup_minutes", "turnaround_minutes"):
        assert body[field] == venue[field]
