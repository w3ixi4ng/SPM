"""TC-E2E-243: S-18 assigned-event editing and fresh safety lifecycle."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def test_coordinator_updates_event_and_restarts_safety_lifecycle(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    support = make_user("technical_support")
    venue_staff = make_user("venue_staff")
    officer = make_user("safety_officer")
    suffix = uuid.uuid4().hex[:6]
    event_name = f"S-18 Planning Update {suffix}"

    venue = admin.schema("venues").table("venues").insert({
        "name": f"S-18 Hall {suffix}", "location": "Building A", "capacity": 200,
        "facilities": ["projector"], "accessibility": ["wheelchair_access"],
        "room_layouts": ["theatre"],
        "operating_hours": [{"day": "wed", "open": "08:00:00", "close": "18:00:00"}],
        "created_by": venue_staff["id"],
    }).execute().data[0]
    item = admin.schema("equipment").table("equipment").insert({
        "type": f"S-18 microphone {suffix}", "description": "Wireless microphone",
        "total_quantity": 12, "created_by": support["id"],
    }).execute().data[0]
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"], "assigned_coordinator_id": coordinator["id"],
        "status": "preparation", "name": event_name, "purpose": "Original description",
        "contact_name": "Original contact", "contact_email": "contact@example.com",
        "contact_phone": "+65 6000 0000", "internal_notes": "Original note",
        "start_date": "2026-11-18", "start_time": "09:00", "end_date": "2026-11-18",
        "end_time": "12:00", "expected_attendance": 100, "venue": venue["name"],
        "room_layout": "theatre", "required_facilities": ["projector"],
        "required_accessibility": ["wheelchair_access"], "decision": "approved",
        "decided_at": "2026-10-01T00:00:00Z", "submitted_at": "2026-09-30T00:00:00Z",
        "equipment_preparation_status": "ready",
        "equipment_preparation_updated_by": support["id"],
        "equipment_preparation_updated_at": "2026-10-02T00:00:00Z",
        "technical_support_required": True, "assigned_technical_support_id": support["id"],
        "technical_support_assigned_at": "2026-10-01T01:00:00Z",
        "safety_decision": "approved", "safety_officer_id": officer["id"],
        "safety_decided_at": "2026-10-02T02:00:00Z",
        "safety_review_history": [{
            "review_number": 1, "decision": "approved", "reason": None,
            "safety_officer_id": officer["id"], "decided_at": "2026-10-02T02:00:00Z",
        }],
    }).execute().data[0]
    requirement = admin.schema("equipment").table("requirements").insert({
        "event_id": event["id"], "equipment_item_id": item["id"],
        "required_quantity": 4, "recorded_by_coordinator_id": coordinator["id"],
    }).execute().data[0]
    booking = admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"], "venue_id": venue["id"],
        "coordinator_id": coordinator["id"], "coordinator_name": "E2E Tester",
        "coordinator_email": coordinator["email"], "status": "confirmed",
        "booking_date": "2026-11-18", "start_time": "09:00", "end_time": "12:00",
        "event_name": event_name, "event_purpose": "Original description",
        "expected_attendance": 100, "required_accessibility": ["wheelchair_access"],
        "required_facilities": ["projector"], "room_layout": "theatre",
        "venue_name": venue["name"], "decided_by": venue_staff["id"],
        "decided_at": "2026-10-02T00:00:00Z",
    }).execute().data[0]

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    expect(page.get_by_role("heading", name=event_name)).to_be_visible(timeout=20000)

    page.get_by_role("button", name="Edit event information").click()
    page.get_by_label("Contact phone").fill("+65 6111 1111")
    page.get_by_label("Internal notes (Coordinator only)").fill("Call supplier on Monday")
    page.get_by_role("button", name="Review changes").click()
    expect(page.get_by_text("Event information saved.", exact=True)).to_be_visible(timeout=20000)
    page.reload()
    expect(page.get_by_text("+65 6111 1111", exact=True)).to_be_visible(timeout=20000)
    expect(page.get_by_text("Call supplier on Monday", exact=True)).to_be_visible()

    page.get_by_role("button", name="Edit event information").click()
    page.get_by_label("Expected attendance").fill("120")
    page.get_by_label("End time").fill("13:00")
    page.get_by_role("button", name="Review changes").click()
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_contain_text("expected attendance")
    expect(dialog).to_contain_text("end time")
    dialog.get_by_role("button", name="Go back").click()
    unchanged = admin.schema("events").table("events").select(
        "status,expected_attendance,end_time"
    ).eq("id", event["id"]).single().execute().data
    assert unchanged["status"] == "preparation"
    assert unchanged["expected_attendance"] == 100
    assert str(unchanged["end_time"]).startswith("12:00")

    page.get_by_role("button", name="Review changes").click()
    page.get_by_role("button", name="Accept and save").click()
    expect(page.get_by_text("Event information saved.", exact=True)).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Submit for fresh safety check")).to_be_visible()
    expect(page.get_by_text(venue["name"], exact=False).first).to_be_visible(timeout=20000)
    expect(page.get_by_text(item["type"], exact=False).first).to_be_visible(timeout=20000)
    page.get_by_role("button", name="Submit for fresh safety check").click()
    expect(page.get_by_text(
        "Revised event submitted for a fresh Operational Safety Check.", exact=True
    )).to_be_visible(timeout=20000)

    stored = admin.schema("events").table("events").select(
        "status,expected_attendance,end_time,equipment_preparation_status,"
        "assigned_technical_support_id,safety_recheck_required,safety_decision,"
        "safety_review_history,edit_version,edit_history"
    ).eq("id", event["id"]).single().execute().data
    assert stored["status"] == "confirmed"
    assert stored["expected_attendance"] == 120
    assert str(stored["end_time"]).startswith("13:00")
    assert stored["equipment_preparation_status"] == "ready"
    assert stored["assigned_technical_support_id"] == support["id"]
    assert stored["safety_recheck_required"] is False
    assert stored["safety_decision"] is None
    assert len(stored["safety_review_history"]) == 1
    assert stored["safety_review_history"][0]["review_number"] == 1
    assert stored["safety_review_history"][0]["decision"] == "approved"
    assert stored["safety_review_history"][0]["safety_officer_id"] == officer["id"]
    assert stored["edit_version"] == 2
    assert [sorted(entry["changes"]) for entry in stored["edit_history"]] == [
        ["contact_phone", "internal_notes"], ["end_time", "expected_attendance"]
    ]
    assert all(entry["changed_by"] == coordinator["id"] for entry in stored["edit_history"])
    assert all(entry["changed_at"] for entry in stored["edit_history"])
    assert admin.schema("bookings").table("bookings").select("id,status").eq(
        "id", booking["id"]
    ).single().execute().data["status"] == "confirmed"
    assert admin.schema("equipment").table("requirements").select("id,required_quantity").eq(
        "id", requirement["id"]
    ).single().execute().data["required_quantity"] == 4
