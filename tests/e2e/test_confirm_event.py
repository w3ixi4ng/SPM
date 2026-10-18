"""TC-E2E-243 — S-17: a Coordinator submits a fully arranged event for the
Operational Safety Check; once the Safety Officer approves it, the Organiser
sees Confirmed.

What only a browser proves: the outstanding list the page shows is the
server's, there is no override control, the new routes work through Kong, and
each role sees the new stage under its own name."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def sign_out(page):
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=30000)


def test_submit_for_safety_check_to_confirmed(admin, page, make_user, sign_in):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    support = make_user("technical_support")
    venue_staff = make_user("venue_staff")
    officer = make_user("safety_officer")
    suffix = uuid.uuid4().hex[:6]
    event_name = f"Confirm Event {suffix}"
    hall = f"Hall A {suffix}"

    venue = admin.schema("venues").table("venues").insert({
        "name": hall,
        "location": "Building A",
        "capacity": 200,
        "facilities": ["projector"],
        "accessibility": [],
        "room_layouts": ["theatre"],
        "operating_hours": [{"day": "fri", "open": "08:00:00", "close": "18:00:00"}],
        "created_by": venue_staff["id"],
    }).execute().data[0]
    item = admin.schema("equipment").table("equipment").insert({
        "type": f"Projector {suffix}",
        "total_quantity": 5,
        "created_by": support["id"],
    }).execute().data[0]
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "assigned_coordinator_id": coordinator["id"],
        "status": "planning",
        "name": event_name,
        "purpose": "Exercise the S-17 browser workflow",
        "start_date": "2026-11-20",
        "start_time": "09:00",
        "end_date": "2026-11-20",
        "end_time": "17:00",
        "expected_attendance": 120,
        "room_layout": "theatre",
        "decision": "approved",
        "decided_at": "2026-10-01T00:00:00Z",
        "submitted_at": "2026-09-30T00:00:00Z",
        "technical_support_required": True,
        "assigned_technical_support_id": support["id"],
        "technical_support_assigned_at": "2026-10-01T01:00:00Z",
    }).execute().data[0]
    admin.schema("equipment").table("requirements").insert({
        "event_id": event["id"],
        "equipment_item_id": item["id"],
        "required_quantity": 2,
        "recorded_by_coordinator_id": coordinator["id"],
    }).execute()
    booking = admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"],
        "venue_id": venue["id"],
        "coordinator_id": coordinator["id"],
        "coordinator_name": "E2E Tester",
        "coordinator_email": coordinator["email"],
        "status": "pending",
        "booking_date": "2026-11-20",
        "start_time": "09:00",
        "end_time": "17:00",
        "event_name": event_name,
        "event_purpose": "Exercise the S-17 browser workflow",
        "expected_attendance": 120,
        "room_layout": "theatre",
        "venue_name": hall,
    }).execute().data[0]

    # 1. Blocked: every outstanding item listed, no way round it.
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    panel = page.get_by_role("region", name="Operational Safety Check")
    panel.get_by_role("button", name="Submit for safety check").click()
    outstanding = panel.get_by_role("list", name="Outstanding arrangements")
    for label in (
        f"{hall} on 20 Nov 2026 is waiting for Venue Staff",
        "Technical Support has not approved the equipment arrangements",
        "Equipment preparation is Not Started",
    ):
        expect(outstanding.get_by_text(label, exact=True)).to_be_visible(timeout=20000)
    expect(panel.get_by_role("alert")).to_contain_text("outstanding arrangements")
    expect(page.get_by_role("checkbox")).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile("override|anyway", re.I))).to_have_count(0)
    stored = admin.schema("events").table("events").select("status").eq("id", event["id"]).single().execute().data
    assert stored["status"] == "planning"
    sign_out(page)

    # 2. Venue Staff's approval is S-33's journey; here it is a fact.
    admin.schema("bookings").table("bookings").update({
        "status": "confirmed",
        "decided_by": venue_staff["id"],
        "decided_at": "2026-10-03T00:00:00Z",
    }).eq("id", booking["id"]).execute()

    sign_in(support)
    page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
    card = page.get_by_role("list", name="Assigned events").get_by_role("listitem").filter(has_text=event_name)
    card.get_by_role("button", name="Approve equipment").click()
    page.get_by_text("Approved by Technical Support.").wait_for(timeout=20000)
    card.get_by_label("Equipment preparation").select_option("ready")
    page.get_by_text("Equipment preparation is now Ready.").wait_for(timeout=20000)
    sign_out(page)

    # 3. Submitted.
    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    panel = page.get_by_role("region", name="Operational Safety Check")
    expect(panel.get_by_text("Every mandatory arrangement is complete")).to_be_visible(timeout=20000)
    panel.get_by_role("button", name="Submit for safety check").click()
    expect(page.get_by_role("status").filter(has_text="Submitted for the Operational Safety Check")).to_be_visible(
        timeout=20000
    )
    sign_out(page)

    # 4. The Organiser sees the real stage.
    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard"), timeout=20000)
    row = page.get_by_role("listitem").filter(has_text=event_name)
    expect(row).to_contain_text("Pending Safety Check", timeout=20000)
    sign_out(page)

    # 5. The Safety Officer approves.
    sign_in(officer)
    page.wait_for_url(re.compile(r"/dashboard/safety-officer$"), timeout=20000)
    page.get_by_role("link", name=re.compile(event_name)).click()
    page.get_by_role("radio", name="Approve", exact=True).check()
    page.get_by_role("button", name="Record safety decision").click()
    expect(page.get_by_role("status")).to_contain_text("Event status: confirmed", timeout=20000)
    page.get_by_role("link", name="Back to safety checks").click()
    sign_out(page)

    # 6. Confirmed, for the Organiser.
    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard"), timeout=20000)
    row = page.get_by_role("listitem").filter(has_text=event_name)
    expect(row).to_contain_text("Confirmed", timeout=20000)
