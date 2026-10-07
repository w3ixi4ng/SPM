"""TC-VENUES-104 (S-75): setup and turnaround against the real table."""
import uuid

import httpx

from .conftest import BASE_URL, requires_env

pytestmark = requires_env


def test_times_are_stored_default_to_zero_and_can_be_updated(admin, make_session, venue_ids):
    staff = make_session("venue_staff")
    # Inserted directly, as a venue from before S-75 would be: no times given.
    venue = admin.schema("venues").table("venues").insert({
        "name": f"spm-test S75 {uuid.uuid4().hex[:8]}", "location": "10 Anson Road", "capacity": 50,
        "room_layouts": ["theatre"], "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
        "created_by": staff["user_id"],
    }).execute().data[0]
    venue_ids.append(venue["id"])

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=staff["headers"]) as api:
        read = api.get(f"/venues/{venue['id']}")
        assert read.status_code == 200, read.text
        assert (read.json()["setup_minutes"], read.json()["turnaround_minutes"]) == (0, 0)

        updated = api.patch(f"/venues/{venue['id']}", json={"setup_minutes": 30, "turnaround_minutes": 45})
        assert updated.status_code == 200, updated.text

        refused = api.patch(f"/venues/{venue['id']}", json={"setup_minutes": -5})
        assert refused.status_code == 422

    stored = admin.schema("venues").table("venues").select("setup_minutes,turnaround_minutes").eq(
        "id", venue["id"]).execute().data[0]
    assert stored == {"setup_minutes": 30, "turnaround_minutes": 45}
