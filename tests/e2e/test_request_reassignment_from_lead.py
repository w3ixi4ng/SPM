"""TC-E2E-249: Coordinator request, scoped Lead review, S-84, outcome."""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


def test_coordinator_request_is_actioned_after_lead_reassignment(page, make_user, sign_in, admin):
    organiser = make_user("event_organiser")
    lead = make_user("event_coordinator_lead")
    former = make_user("event_coordinator")
    replacement = make_user("event_coordinator")
    event_name = f"S-88 Forum {uuid.uuid4().hex[:6]}"
    reason = "Cannot cover the November event"
    admin.schema("users").table("users").update({"name": "Alex Coordinator"}).eq("id", former["id"]).execute()
    admin.schema("users").table("users").update({"name": "Blair Coordinator"}).eq("id", replacement["id"]).execute()
    admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"], "status": "submitted",
        "assigned_coordinator_id": former["id"], "assigning_lead_id": lead["id"],
        "name": event_name, "purpose": "S-88 browser journey",
        "start_date": "2026-11-18", "start_time": "09:00",
        "end_date": "2026-11-18", "end_time": "12:00",
        "expected_attendance": 25, "submitted_at": "2026-10-25T00:00:00Z",
    }).execute()

    sign_in(former)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.get_by_role("tab", name="Events").click()
    page.get_by_role("link", name=re.compile(event_name)).click()
    page.get_by_label("Reason", exact=True).fill(reason)
    page.get_by_role("button", name="Send request").click()
    page.get_by_text("Request sent to the responsible Lead.").wait_for(timeout=20000)
    page.get_by_text("Pending", exact=True).wait_for(timeout=20000)
    page.reload()
    page.get_by_text(reason, exact=True).wait_for(timeout=20000)
    page.goto("/dashboard/event-coordinator")
    page.get_by_role("button", name="Sign out").click()

    sign_in(lead)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator-lead$"), timeout=20000)
    requests = page.get_by_role("heading", name="Reassignment requests").locator("..")
    requests.get_by_text(event_name, exact=True).wait_for(timeout=20000)
    requests.get_by_text(reason, exact=True).wait_for(timeout=20000)
    card = page.get_by_role("listitem").filter(has_text=event_name).filter(has=page.get_by_role("button", name="Reassign event"))
    card.get_by_label(f"New Event Coordinator for {event_name}").select_option(replacement["id"])
    card.get_by_role("button", name="Reassign event").click()
    page.get_by_text(f"{event_name} was reassigned to Blair Coordinator.", exact=True).wait_for(timeout=30000)
    requests.get_by_text("Actioned", exact=False).wait_for(timeout=20000)
    page.get_by_role("button", name="Sign out").click()

    sign_in(former)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.get_by_role("tab", name="Events").click()
    history = page.get_by_role("heading", name="Reassignment requests").locator("..")
    history.get_by_text(event_name, exact=True).wait_for(timeout=20000)
    history.get_by_text("Actioned", exact=True).wait_for(timeout=20000)
    page.reload()
    page.get_by_text("Actioned", exact=True).wait_for(timeout=20000)


def test_lead_request_empty_error_and_retry_states(page, make_user, sign_in):
    lead = make_user("event_coordinator_lead")
    sign_in(lead)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator-lead$"), timeout=20000)
    section = page.get_by_role("heading", name="Reassignment requests").locator("..")
    section.get_by_text("No reassignment requests in your scope.").wait_for(timeout=20000)

    route_pattern = "**/api/event-requests/reassignment-requests/lead"
    page.route(route_pattern, lambda route: route.fulfill(
        status=502, content_type="application/json",
        body='{"detail":"Events service unavailable"}',
    ))
    page.reload()
    section = page.get_by_role("heading", name="Reassignment requests").locator("..")
    section.get_by_role("alert").get_by_text("Reassignment requests are unavailable. Try again.").wait_for(timeout=20000)
    page.unroute(route_pattern)
    section.get_by_role("button", name="Try again").click()
    section.get_by_text("No reassignment requests in your scope.").wait_for(timeout=20000)
