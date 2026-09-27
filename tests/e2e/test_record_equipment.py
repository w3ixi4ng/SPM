"""TC-E2E-211 -- Coordinator records equipment and Technical Support sees it."""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


# --- TC-E2E-211 -----------------------------------------------------------
def test_coordinator_records_required_equipment_visible_to_technical_support(admin, page, make_user, sign_in):
    coordinator = make_user("event_coordinator")
    support = make_user("technical_support")
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    item_type = f"spm-e2e Wireless Microphone {suffix}"

    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "status": "planning",
        "assigned_coordinator_id": coordinator["id"],
        "name": f"spm-e2e Equipment Event {suffix}",
        "purpose": "Prove the S-40 browser journey",
        "start_date": "2026-11-12",
        "start_time": "09:00",
        "end_date": "2026-11-12",
        "end_time": "12:00",
        "expected_attendance": 80,
        "decision": "approved",
        "decided_at": "2026-10-01T00:00:00+00:00",
        "submitted_at": "2026-09-30T00:00:00+00:00",
    }).execute().data[0]

    sign_in(support)
    page.wait_for_url(re.compile(r"/dashboard/technical-support"), timeout=20000)
    page.get_by_role("link", name="Add equipment").click()
    page.get_by_label("Type or name (required)").fill(item_type)
    page.get_by_label("Description (optional)").fill("E2E requirement item")
    page.get_by_label("Total quantity (required)").fill("12")
    page.get_by_role("button", name="Add equipment").click()
    page.wait_for_url(re.compile(r"/dashboard/technical-support"), timeout=20000)
    page.get_by_text(f"{item_type} was added to the equipment catalogue.").wait_for(timeout=20000)
    item = admin.schema("equipment").table("equipment").select("*").eq("type", item_type).execute().data[0]
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    page.get_by_role("heading", name="Required equipment").wait_for(timeout=20000)
    page.get_by_label(f"{item_type} quantity").fill("6")
    editor = page.get_by_role("list", name="Equipment requirements editor")
    editor.get_by_role("listitem").filter(has_text=item_type).get_by_role("button", name="Save").click()
    page.get_by_text("Equipment requirement saved.").wait_for(timeout=20000)

    page.goto("/dashboard/event-coordinator")
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login"), timeout=20000)

    sign_in(support)
    page.wait_for_url(re.compile(r"/dashboard/technical-support"), timeout=20000)
    requirements = page.get_by_role("list", name="Equipment requirements")
    row = requirements.get_by_role("listitem").filter(has_text=item_type)
    row.wait_for(timeout=20000)
    row.get_by_text("×6", exact=True).wait_for()
    row.get_by_text(f"Event {event['id']}", exact=True).wait_for()

    stored = admin.schema("equipment").table("requirements").select("*").eq(
        "event_id", event["id"]
    ).eq("equipment_item_id", item["id"]).execute().data
    assert len(stored) == 1
    assert stored[0]["required_quantity"] == 6
    assert stored[0]["recorded_by_coordinator_id"] == coordinator["id"]
