"""TC-VENUEBOOKINGS-136. Run after the S-90 SQL on .env.test."""
import httpx

from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env
from .test_replacement_venue import flagged_booking, more, row_for  # noqa: F401 -- more is a fixture

pytestmark = requires_env


# --- TC-VENUEBOOKINGS-136 --------------------------------------------------
def test_a_restore_is_asked_for_confirmed_and_recorded_through_kong(admin, auth_client, world, more):
    add_venue, _ = more
    admin.schema("venues").table("venues").update(
        {"setup_minutes": 30, "turnaround_minutes": 45}
    ).eq("id", world["venue_id"]).execute()
    w = add_venue("W")
    coordinator = cookie_for(auth_client, world["coordinator"])
    staff = cookie_for(auth_client, world["staff"])

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=30.0) as api:
        o = flagged_booking(api, world, coordinator, staff)

        # 1. The replacement waits for Venue Staff.
        sent = api.post(f"/venue-bookings/{o}/replacement", headers=coordinator, json={"venue_id": w})
        assert sent.status_code == 201, sent.text
        r = sent.json()["id"]

        # 2. The period still covers O's window, so the venue isn't free.
        refused = api.post(f"/venue-bookings/{o}/restore", headers=coordinator)
        assert refused.status_code == 409, refused.text
        assert " is unavailable from " in refused.json()["detail"]

        # 3. Venue Staff delete the period.
        [block] = admin.schema("bookings").table("blocks").select("id").eq(
            "venue_id", world["venue_id"]).execute().data
        removed = api.delete(f"/venue-bookings/blocks/{block['id']}", headers=staff)
        assert removed.status_code == 204, removed.text

        # 4. Now it is.
        asked = api.post(f"/venue-bookings/{o}/restore", headers=coordinator)
        assert asked.status_code == 200, (
            f"{asked.text} -- check the S-90 block of bookings.sql is applied"
        )

        # 5. Venue Staff see and confirm it.
        listed = api.get("/venue-bookings/restores", headers=staff)
        assert listed.status_code == 200, listed.text
        [row] = [item for item in listed.json() if item["id"] == o]
        assert row["replacement"]["id"] == r
        decided = api.post(f"/venue-bookings/{o}/restore-decision", headers=staff,
                           json={"decision": "approved"})
        assert decided.status_code == 200, decided.text

        # 6. The event keeps its first-choice venue.
        original = row_for(api, coordinator, world, o)
        assert original["status"] == "confirmed"
        assert original["requires_alternative_arrangements"] is False
        assert original["alternative_resolution_note"] == "Restored to the original venue"
        assert row_for(api, coordinator, world, r)["status"] == "withdrawn"

        history = api.get(f"/event-requests/{world['event_id']}/history", headers=coordinator)
        assert history.status_code == 200, history.text
        actions = [entry["action"] for entry in history.json()["entries"]]
        assert "venue_restore_requested" in actions
        assert "venue_restore_confirmed" in actions
