"""TC-E2E-270: a registered Attendee sees a confirmed reschedule."""

import re
import uuid

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def sign_out(page):
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=30000)


def test_registered_attendee_sees_reschedule_only_after_final_approval(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    officer = make_user("safety_officer")
    attendee = make_user("attendee")
    unrelated = make_user("attendee")
    name = f"spm-e2e S-68 {uuid.uuid4().hex[:6]}"
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "assigned_coordinator_id": coordinator["id"],
        "status": "pending_safety_check",
        "name": name,
        "purpose": "Prove confirmed attendee reschedule notification",
        "start_date": "2026-11-20",
        "start_time": "13:00",
        "end_date": "2026-11-20",
        "end_time": "16:00",
        "expected_attendance": 30,
        "decision": "approved",
        "decided_at": "2026-09-30T09:00:00Z",
        "submitted_at": "2026-09-29T09:00:00Z",
        "safety_review_history": [{
            "review_number": 1,
            "decision": "approved",
            "reason": None,
            "safety_officer_id": officer["id"],
            "decided_at": "2026-10-01T09:00:00Z",
        }],
    }).execute().data[0]
    admin.schema("events").table("event_history").insert({
        "event_id": event["id"],
        "actor_id": coordinator["id"],
        "actor_role": "event_coordinator",
        "category": "edit",
        "action": "edited",
        "details": {"changes": {
            "start_date": {"before": "2026-11-18", "after": "2026-11-20"},
            "start_time": {"before": "09:00:00", "after": "13:00:00"},
            "end_date": {"before": "2026-11-18", "after": "2026-11-20"},
            "end_time": {"before": "12:00:00", "after": "16:00:00"},
        }},
        "occurred_at": "2026-10-05T09:00:00Z",
    }).execute()
    admin.schema("registrations").table("registrations").insert({
        "event_id": event["id"],
        "attendee_id": attendee["id"],
    }).execute()

    # Internal planning and pending review are not attendee announcements.
    sign_in(attendee)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    expect(page.get_by_role("region", name="Notifications")).not_to_contain_text(name)
    sign_out(page)

    sign_in(officer)
    page.wait_for_url(re.compile(r"/dashboard/safety-officer$"), timeout=20000)
    page.get_by_role("link", name=re.compile(name)).click()
    page.get_by_role("radio", name="Approve", exact=True).check()
    page.get_by_role("button", name="Record safety decision").click()
    expect(page.get_by_role("status")).to_contain_text(
        "Event status: confirmed", timeout=20000
    )
    page.get_by_role("link", name="Back to safety checks").click()
    sign_out(page)

    sign_in(attendee)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    inbox = page.get_by_role("region", name="Notifications")
    expect(inbox).to_contain_text(name, timeout=20000)
    expect(inbox).to_contain_text("Event rescheduled")
    expect(inbox).to_contain_text("20 Nov 2026, 1:00 pm to 4:00 pm")
    expect(inbox).to_contain_text("registration is still active")
    page.reload()
    expect(page.get_by_role("region", name="Notifications")).to_contain_text(
        name, timeout=20000
    )
    sign_out(page)

    sign_in(unrelated)
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
    expect(page.get_by_role("region", name="Notifications")).not_to_contain_text(name)
