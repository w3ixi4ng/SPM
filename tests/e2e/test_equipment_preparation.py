"""TC-E2E-239: Technical Support preparation status reaches the Coordinator,
and stays read-only until the Safety Officer approves the event (S-26 AC2)."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def test_support_updates_preparation_and_coordinator_sees_it(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    support = make_user("technical_support")
    suffix = uuid.uuid4().hex[:6]
    planning = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "assigned_coordinator_id": coordinator["id"],
        "status": "planning",
        "name": f"S-26 Not yet approved {suffix}",
        "purpose": "Prove S-26 AC2 in the browser",
        "start_date": "2026-11-21",
        "start_time": "13:00",
        "end_date": "2026-11-21",
        "end_time": "16:00",
        "expected_attendance": 60,
        "decision": "approved",
        "decided_at": "2026-10-01T00:00:00Z",
        "submitted_at": "2026-09-30T00:00:00Z",
        "technical_support_required": True,
        "assigned_technical_support_id": support["id"],
        "technical_support_assigned_at": "2026-10-01T01:00:00Z",
    }).execute().data[0]
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "assigned_coordinator_id": coordinator["id"],
        "status": "confirmed",
        "safety_decision": "approved",
        "safety_officer_id": str(uuid.uuid4()),
        "safety_decided_at": "2026-10-03T00:00:00Z",
        "name": f"S-26 Preparation {suffix}",
        "purpose": "Prove the S-26 browser workflow",
        "start_date": "2026-11-21",
        "start_time": "09:00",
        "end_date": "2026-11-21",
        "end_time": "12:00",
        "expected_attendance": 60,
        "decision": "approved",
        "decided_at": "2026-10-01T00:00:00Z",
        "submitted_at": "2026-09-30T00:00:00Z",
        "technical_support_required": True,
        "technical_support_details": "Prepare microphones and projector",
        "assigned_technical_support_id": support["id"],
        "technical_support_assigned_at": "2026-10-01T01:00:00Z",
    }).execute().data[0]

    sign_in(support)
    page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
    assigned = page.get_by_role("list", name="Assigned events")

    # S-26 AC2: before the Safety Officer's approval there is nothing to change.
    not_yet = assigned.get_by_role("listitem").filter(has_text=planning["name"])
    expect(not_yet.get_by_text(
        "Equipment preparation opens once the Safety Officer approves the event."
    )).to_be_visible(timeout=20000)
    expect(not_yet.get_by_label("Equipment preparation")).to_have_count(0)

    card = assigned.get_by_role("listitem").filter(has_text=event["name"])
    preparation = card.get_by_label("Equipment preparation")
    expect(preparation).to_have_value("not_started")
    preparation.select_option("in_progress")
    page.get_by_text("Equipment preparation is now In Progress.").wait_for(timeout=20000)
    expect(preparation).to_have_value("in_progress")
    preparation.select_option("ready")
    page.get_by_text("Equipment preparation is now Ready.").wait_for(timeout=20000)
    page.reload()
    expect(card.get_by_label("Equipment preparation")).to_have_value("ready")

    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=30000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    readiness = page.get_by_label("Equipment preparation readiness")
    readiness.get_by_text("Ready", exact=True).wait_for(timeout=20000)
    expect(readiness.get_by_role("combobox")).to_have_count(0)

    stored = admin.schema("events").table("events").select(
        "equipment_preparation_status,equipment_preparation_updated_by,equipment_preparation_updated_at"
    ).eq("id", event["id"]).execute().data[0]
    assert stored["equipment_preparation_status"] == "ready"
    assert stored["equipment_preparation_updated_by"] == support["id"]
    assert stored["equipment_preparation_updated_at"] is not None
    untouched = admin.schema("events").table("events").select(
        "equipment_preparation_status"
    ).eq("id", planning["id"]).execute().data[0]
    assert untouched["equipment_preparation_status"] == "not_started"
