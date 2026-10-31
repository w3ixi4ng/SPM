"""TC-E2E-267: a returned decision appears in the owning Organiser's inbox."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def test_an_organiser_sees_an_actionable_returned_event_notice(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    other_organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    name = f"spm-e2e S-63 {uuid.uuid4().hex[:6]}"
    reason = "Missing contact details"
    comment = "Add a telephone number"
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "assigned_coordinator_id": coordinator["id"],
        "status": "submitted",
        "name": name,
        "purpose": "Prove the organiser notification journey",
        "start_date": "2026-11-18",
        "start_time": "09:00",
        "end_date": "2026-11-18",
        "end_time": "12:00",
        "expected_attendance": 40,
        "venue": "Seminar Room 3",
        "submitted_at": "2026-10-01T00:00:00Z",
    }).execute().data[0]

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    page.get_by_role("heading", name="Record your decision").wait_for(timeout=20000)
    page.get_by_role("radio", name="Return for amendment").click()
    page.locator("#decision-reason").fill(reason)
    page.locator("#decision-comment").fill(comment)
    page.get_by_role("button", name="Record decision").click()
    expect(page.get_by_text("Action Required", exact=True).first).to_be_visible(
        timeout=20000
    )
    page.goto("/dashboard/event-coordinator")
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=30000)

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    inbox = page.get_by_role("region", name="Notifications")
    expect(inbox).to_contain_text(name, timeout=20000)
    expect(inbox).to_contain_text("returned for amendment")
    expect(inbox).to_contain_text(reason)
    expect(inbox).to_contain_text(comment)
    expect(inbox).to_contain_text("resubmit")
    page.reload()
    expect(page.get_by_role("region", name="Notifications")).to_contain_text(
        name, timeout=20000
    )
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=30000)

    sign_in(other_organiser)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    expect(page.get_by_role("region", name="Notifications")).not_to_contain_text(name)
