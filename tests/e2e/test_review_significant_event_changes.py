"""S-60: a Coordinator accepts a proposal, resolves owner-backed impacts, and resubmits safety."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env


pytestmark = requires_env


def sign_out(page):
    page.goto("/dashboard")
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=30000)


def test_proposal_review_resolution_requires_fresh_safety_check(page, make_user, sign_in, admin):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    unrelated = make_user("event_coordinator")
    technician = make_user("technical_support")
    venue_staff = make_user("venue_staff")
    tag = uuid.uuid4().hex[:8]
    name = f"S60 Impact Forum {tag}"
    item = admin.schema("equipment").table("equipment").insert({
        "type": f"S60 Projector {tag}", "total_quantity": 10,
        "created_by": technician["id"],
    }).execute().data[0]
    venues = []
    for label, capacity, layouts in (("Small", 130, ["theatre"]),
                                     ("Large", 220, ["theatre", "banquet"]),
                                     ("Replacement", 200, ["banquet"])):
        venues.append(admin.schema("venues").table("venues").insert({
            "name": f"S60 {label} {tag}", "location": "10 Anson Road",
            "capacity": capacity, "room_layouts": layouts,
            "operating_hours": [{"day": "wed", "open": "08:00:00", "close": "20:00:00"}],
            "created_by": venue_staff["id"],
        }).execute().data[0])
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"], "assigned_coordinator_id": coordinator["id"],
        "status": "confirmed", "name": name, "purpose": "Review revised arrangements",
        "start_date": "2026-11-18", "start_time": "09:00",
        "end_date": "2026-11-18", "end_time": "12:00",
        "expected_attendance": 120, "room_layout": "theatre",
        "submitted_at": "2026-10-01T00:00:00Z", "decision": "approved",
        "decided_at": "2026-10-02T00:00:00Z", "safety_decision": "approved",
        "safety_officer_id": technician["id"], "safety_decided_at": "2026-10-03T00:00:00Z",
        "technical_support_required": True,
        "assigned_technical_support_id": technician["id"],
        "technical_support_assigned_at": "2026-10-02T00:00:00Z",
        "technical_signoff_decision": "approved", "technical_signoff_by": technician["id"],
        "technical_signoff_at": "2026-10-03T00:00:00Z",
        "equipment_preparation_status": "ready",
    }).execute().data[0]
    requirement = admin.schema("equipment").table("requirements").insert({
        "event_id": event["id"], "equipment_item_id": item["id"],
        "required_quantity": 2, "recorded_by_coordinator_id": coordinator["id"],
    }).execute().data[0]
    bookings = []
    for venue in venues[:2]:
        bookings.append(admin.schema("bookings").table("bookings").insert({
            "event_id": event["id"], "venue_id": venue["id"],
            "coordinator_id": coordinator["id"], "coordinator_name": "E2E Tester",
            "coordinator_email": coordinator["email"], "booking_date": "2026-11-18",
            "start_time": "09:00", "end_time": "12:00", "event_name": name,
            "event_purpose": event["purpose"], "expected_attendance": 120,
            "venue_name": venue["name"], "status": "confirmed",
            "decided_by": venue_staff["id"], "decided_at": "2026-10-03T00:00:00Z",
        }).execute().data[0])

    try:
        sign_in(organiser)
        page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
        page.goto(f"/events/{event['id']}")
        page.get_by_role("link", name="Request Changes").click()
        page.get_by_role("heading", name="Request Changes").wait_for(timeout=20000)
        page.get_by_label("Expected attendance").fill("150")
        page.get_by_label("Room layout").select_option("banquet")
        page.get_by_label(f"{item['type']} quantity").fill("3")
        page.get_by_role("button", name="Submit change request").click()
        expect(page.get_by_role("status")).to_contain_text("Change request submitted", timeout=20000)
        assert admin.schema("events").table("events").select("expected_attendance").eq("id", event["id"]).single().execute().data["expected_attendance"] == 120
        sign_out(page)

        sign_in(unrelated)
        page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
        page.goto(f"/coordinator/events/{event['id']}")
        assert page.get_by_role("region", name="Change impact review").count() == 0
        sign_out(page)

        sign_in(coordinator)
        page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
        page.goto(f"/coordinator/events/{event['id']}")
        review = page.get_by_role("region", name="Change impact review")
        expect(review).to_contain_text("Accepted when requested", timeout=20000)
        expect(review).to_contain_text("150")
        expect(review).to_contain_text(bookings[0]["id"])
        expect(review).not_to_contain_text(bookings[1]["id"])
        expect(review).to_contain_text(item["id"])
        accept_url = f"**/api/event-requests/{event['id']}/change-requests/*/accept"
        page.route(accept_url, lambda route: route.fulfill(
            status=502, content_type="application/json",
            body='{"detail":"Equipment batch incomplete; retry acceptance"}',
        ))
        review.get_by_label("I reviewed every impact and proposed next action.").check()
        review.get_by_role("button", name="Accept significant changes").click()
        expect(review.get_by_role("alert")).to_contain_text("Equipment batch incomplete", timeout=20000)
        assert admin.schema("events").table("events").select("expected_attendance").eq(
            "id", event["id"]).single().execute().data["expected_attendance"] == 120
        page.unroute(accept_url)
        review.get_by_role("button", name="Accept significant changes").click()
        expect(review).to_contain_text("Change accepted", timeout=20000)
        page.reload()
        review = page.get_by_role("region", name="Change impact review")
        expect(review).to_contain_text("Change accepted", timeout=20000)
        stored = admin.schema("events").table("events").select("status,expected_attendance,safety_decision,technical_signoff_decision").eq("id", event["id"]).single().execute().data
        assert stored == {"status": "planning", "expected_attendance": 150,
                          "safety_decision": None, "technical_signoff_decision": "approved"}
        assert admin.schema("equipment").table("requirements").select("required_quantity").eq("id", requirement["id"]).single().execute().data["required_quantity"] == 3
        assert len(admin.schema("bookings").table("bookings").select("id").eq("event_id", event["id"]).execute().data) == 2
        blocked = page.request.post(f"/api/safety-checks/coordinator/events/{event['id']}/submit")
        assert blocked.status == 409
        assert any(row["code"] == "change_impact" for row in blocked.json()["outstanding"])

        requested = page.request.post("/api/venue-bookings", data={
            "event_id": event["id"], "venue_id": venues[2]["id"],
            "booking_date": "2026-11-18", "start_time": "09:00", "end_time": "12:00",
        })
        assert requested.status == 201, requested.text()
        replacement_id = requested.json()["id"]
        sign_out(page)

        sign_in(venue_staff)
        page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
        decision = page.request.post(f"/api/venue-bookings/{replacement_id}/decision", data={"decision": "approved"})
        assert decision.status == 200, decision.text()
        sign_out(page)

        sign_in(technician)
        page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
        signoff = page.request.post(f"/api/equipment-requirements/{event['id']}/sign-off", data={"decision": "approved"})
        assert signoff.status == 200, signoff.text()
        prepared = page.request.put(f"/api/events/support-assigned/{event['id']}/equipment-preparation",
                                    data={"status": "ready"})
        assert prepared.status == 200, prepared.text()
        sign_out(page)

        sign_in(coordinator)
        page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
        page.goto(f"/coordinator/events/{event['id']}")
        review = page.get_by_role("region", name="Change impact review")
        expect(review).to_contain_text("arrangement impacts remain outstanding", timeout=20000)
        for reason in ("holds 130", "does not offer"):
            row = review.get_by_role("listitem").filter(has_text=f"venue booking {bookings[0]['id']}").filter(has_text=reason)
            row.get_by_label("Confirmed booking reviewed").select_option(replacement_id)
            row.get_by_role("button", name="Record re-review and resolve").click()
            expect(row).to_contain_text("Status: resolved", timeout=20000)
        for kind, identity in (("equipment", item["id"]), ("technical support", technician["id"])):
            row = review.get_by_role("listitem").filter(has_text=f"{kind} {identity}")
            row.get_by_role("button", name="Record re-review and resolve").click()
            expect(row).to_contain_text("Status: resolved", timeout=20000)
        page.reload()
        expect(page.get_by_role("region", name="Change impact review")).not_to_contain_text("arrangement impacts remain outstanding", timeout=20000)
        panel = page.get_by_role("region", name="Operational Safety Check")
        panel.get_by_role("button", name="Submit for safety check").click()
        expect(page.get_by_role("status").filter(has_text="Submitted for the Operational Safety Check")).to_be_visible(timeout=20000)
        latest = admin.schema("events").table("events").select("status,safety_decision").eq("id", event["id"]).single().execute().data
        assert latest == {"status": "pending_safety_check", "safety_decision": None}

        sign_out(page)
        sign_in(organiser)
        page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
        current = admin.schema("events").table("events").select("*").eq(
            "id", event["id"]).single().execute().data
        next_values = {field: current.get(field) for field in (
            "start_date", "start_time", "end_date", "end_time", "venue",
            "special_requirements", "room_layout", "required_facilities", "required_accessibility",
        )}
        submitted_again = page.request.post(
            f"/api/event-requests/{event['id']}/change-requests",
            data={"values": {**next_values, "expected_attendance": 160},
                  "equipment": [{"equipment_item_id": item["id"], "required_quantity": 3}]},
        )
        assert submitted_again.status == 201, submitted_again.text()
        sign_out(page)

        sign_in(coordinator)
        page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
        page.goto(f"/coordinator/events/{event['id']}")
        review = page.get_by_role("region", name="Change impact review")
        review.get_by_label("Reason for rejection").fill("Venue unavailable for the larger group")
        review.get_by_role("button", name="Reject request").click()
        expect(review).to_contain_text("Request rejected: Venue unavailable for the larger group", timeout=20000)
        assert admin.schema("events").table("events").select("expected_attendance").eq(
            "id", event["id"]).single().execute().data["expected_attendance"] == 150
    finally:
        admin.schema("equipment").table("change_operations").delete().eq("event_id", event["id"]).execute()
        admin.schema("events").table("change_requests").delete().eq("event_id", event["id"]).execute()
        admin.schema("equipment").table("requirement_changes").delete().eq("event_id", event["id"]).execute()
