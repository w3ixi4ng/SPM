"""S-59: Organiser proposal stays separate and reaches the assigned Coordinator."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def test_organiser_proposes_changes_and_coordinator_sees_them(page, make_user, sign_in, admin):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    unrelated = make_user("event_coordinator")
    technician = make_user("technical_support")
    venue_staff = make_user("venue_staff")
    attendee = make_user("attendee")
    tag = uuid.uuid4().hex[:8]

    item = admin.schema("equipment").table("equipment").insert({
        "type": f"S59 Projector {tag}", "total_quantity": 10,
        "created_by": technician["id"],
    }).execute().data[0]
    venue = admin.schema("venues").table("venues").insert({
        "name": f"S59 Hall {tag}", "location": "10 Anson Road", "capacity": 300,
        "room_layouts": ["theatre", "banquet"], "facilities": ["projector"],
        "operating_hours": [{"day": "wed", "open": "08:00:00", "close": "20:00:00"}],
        "created_by": venue_staff["id"],
    }).execute().data[0]
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"], "assigned_coordinator_id": coordinator["id"],
        "status": "confirmed", "name": f"S59 Autumn Forum {tag}",
        "purpose": "Review proposed arrangements", "start_date": "2026-11-18",
        "start_time": "09:00", "end_date": "2026-11-18", "end_time": "12:00",
        "expected_attendance": 120, "room_layout": "theatre",
        "submitted_at": "2026-10-01T00:00:00Z", "decision": "approved",
        "decided_at": "2026-10-02T00:00:00Z", "safety_decision": "approved",
        "safety_officer_id": technician["id"], "safety_decided_at": "2026-10-03T00:00:00Z",
        "technical_support_required": True, "assigned_technical_support_id": technician["id"],
        "technical_support_assigned_at": "2026-10-02T00:00:00Z",
        "technical_signoff_decision": "approved", "technical_signoff_by": technician["id"],
        "technical_signoff_at": "2026-10-03T00:00:00Z",
    }).execute().data[0]
    requirement = admin.schema("equipment").table("requirements").insert({
        "event_id": event["id"], "equipment_item_id": item["id"],
        "required_quantity": 2, "recorded_by_coordinator_id": coordinator["id"],
    }).execute().data[0]
    booking = admin.schema("bookings").table("bookings").insert({
        "event_id": event["id"], "venue_id": venue["id"],
        "coordinator_id": coordinator["id"], "coordinator_name": "E2E Tester",
        "coordinator_email": coordinator["email"], "booking_date": "2026-11-18",
        "start_time": "09:00", "end_time": "12:00", "event_name": event["name"],
        "event_purpose": event["purpose"], "expected_attendance": 120,
        "venue_name": venue["name"], "status": "confirmed",
        "decided_by": venue_staff["id"], "decided_at": "2026-10-03T00:00:00Z",
    }).execute().data[0]
    registration = admin.schema("registrations").table("registrations").insert({
        "event_id": event["id"], "attendee_id": attendee["id"],
    }).execute().data[0]

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    page.goto(f"/events/{event['id']}")
    page.get_by_role("link", name="Request Changes").click()
    page.get_by_role("heading", name="Request Changes").wait_for(timeout=20000)
    expect(page.get_by_label("Expected attendance")).to_have_value("120")
    page.get_by_label("Expected attendance").fill("150")
    page.get_by_label("Room layout").select_option("banquet")
    page.get_by_label(f"{item['type']} quantity").fill("3")
    page.get_by_role("button", name="Submit change request").click()
    expect(page.get_by_role("status")).to_contain_text("Change request submitted", timeout=20000)
    page.reload()
    comparison = page.get_by_role("region", name="Event change request")
    expect(comparison).to_contain_text("Change request: pending", timeout=20000)
    expect(comparison).to_contain_text("Expected attendance")
    expect(comparison).to_contain_text("Expected attendance (changed)")
    expect(comparison).to_contain_text("Room layout (changed)")
    expect(comparison).to_contain_text("Equipment requirements (changed)")
    expect(comparison).to_contain_text("150")
    expect(comparison).to_contain_text("not yet been validated")

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    first_coordinator_read = {"failed": False}

    def fail_coordinator_read_once(route):
        if not first_coordinator_read["failed"]:
            first_coordinator_read["failed"] = True
            route.fulfill(status=502, json={"detail": "Temporary comparison outage"})
        else:
            route.continue_()

    comparison_url = f"**/api/event-requests/{event['id']}/change-requests"
    page.route(comparison_url, fail_coordinator_read_once)
    page.goto(f"/coordinator/events/{event['id']}")
    expect(page.get_by_role("alert")).to_contain_text("Temporary comparison outage", timeout=20000)
    page.get_by_role("button", name="Try again").click()
    expect(page.get_by_role("region", name="Event change request")).to_contain_text("150", timeout=20000)
    page.unroute(comparison_url, fail_coordinator_read_once)
    assert page.get_by_role("button", name="Accept change request").count() == 0

    sign_in(unrelated)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    assert page.get_by_role("region", name="Event change request").count() == 0

    saved = admin.schema("events").table("events").select("status,expected_attendance,room_layout,assigned_technical_support_id,technical_signoff_decision").eq("id", event["id"]).execute().data[0]
    assert saved == {"status": "confirmed", "expected_attendance": 120, "room_layout": "theatre", "assigned_technical_support_id": technician["id"], "technical_signoff_decision": "approved"}
    assert admin.schema("equipment").table("requirements").select("required_quantity").eq("id", requirement["id"]).execute().data[0]["required_quantity"] == 2
    assert admin.schema("bookings").table("bookings").select("status").eq("id", booking["id"]).execute().data[0]["status"] == "confirmed"
    assert admin.schema("registrations").table("registrations").select("attendee_id").eq("id", registration["id"]).execute().data[0]["attendee_id"] == attendee["id"]


def test_change_request_form_recovers_from_loading_and_submission_errors(page, make_user, sign_in):
    organiser = make_user("event_organiser")
    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    event_id = str(uuid.uuid4())
    accepted = {
        "id": event_id, "status": "submitted", "name": "S59 Error Forum",
        "start_date": "2026-11-18", "start_time": "09:00:00",
        "end_date": "2026-11-18", "end_time": "12:00:00",
        "expected_attendance": 120, "venue": None,
        "special_requirements": None, "room_layout": None,
        "required_facilities": [], "required_accessibility": [],
    }
    change_fields = (
        "start_date", "start_time", "end_date", "end_time",
        "expected_attendance", "venue", "special_requirements",
        "room_layout", "required_facilities", "required_accessibility",
    )
    saved_request = {
        "id": str(uuid.uuid4()), "event_id": event_id,
        "status": "pending", "requested_by": organiser["id"],
        "submitted_at": "2026-10-28T09:15:00Z",
        "accepted_values": {key: accepted[key] for key in change_fields},
        "proposed_values": {
            **{key: accepted[key] for key in change_fields},
            "expected_attendance": 150,
        },
        "accepted_equipment": [], "proposed_equipment": [],
    }
    state = {"gets": 0, "posts": 0, "saved": False}

    def serve_change_request(route):
        if route.request.method == "GET":
            state["gets"] += 1
            if state["gets"] == 1:
                route.fulfill(status=502, json={"detail": "Temporary outage"})
                return
            requests = [saved_request] if state["saved"] else []
            route.fulfill(status=200, json={
                "event": accepted, "requests": requests,
                "equipment": [], "equipment_options": [],
            })
            return
        state["posts"] += 1
        status = [422, 409, 502, 201][state["posts"] - 1] if state["posts"] <= 4 else 409
        if status == 201:
            state["saved"] = True
            route.fulfill(status=201, json=saved_request)
        else:
            route.fulfill(status=status, json={"detail": f"Simulated {status} response"})

    page.route(f"**/api/event-requests/{event_id}/change-requests", serve_change_request)
    page.route("**/api/events/options", lambda route: route.fulfill(status=200, json={
        "room_layouts": [], "facilities": [], "accessibility": [],
    }))
    page.goto(f"/events/{event_id}/change-request")
    expect(page.get_by_role("alert")).to_contain_text("Temporary outage", timeout=20000)
    page.get_by_role("button", name="Try again").click()
    expect(page.get_by_label("Expected attendance")).to_have_value("120", timeout=20000)
    expect(page.get_by_role("button", name="Submit change request")).to_be_disabled()
    page.get_by_label("Expected attendance").fill("150")
    expect(page.get_by_role("button", name="Submit change request")).to_be_enabled()

    page.get_by_role("button", name="Submit change request").click()
    expect(page.get_by_role("alert")).to_contain_text("Simulated 422 response")
    page.get_by_role("button", name="Submit change request").click()
    expect(page.get_by_role("alert")).to_contain_text("Reload to see the latest details")
    page.get_by_role("button", name="Submit change request").click()
    expect(page.get_by_role("alert")).to_contain_text("Simulated 502 response")
    assert page.get_by_label("Expected attendance").input_value() == "150"
    page.evaluate("""() => {
      const button = document.querySelector('form[aria-label="Request event changes"] button[type="submit"]')
      button.click()
      button.click()
    }""")
    expect(page.get_by_role("status")).to_contain_text("Change request submitted")
    page.reload()
    expect(page.get_by_role("region", name="Event change request")).to_contain_text("Change request: pending", timeout=20000)
    assert state["posts"] == 4
