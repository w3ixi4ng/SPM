"""TC-E2E-216 -- explicit Technical Support auto-assignment journey."""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


# --- TC-E2E-216 -----------------------------------------------------------
def test_coordinator_requests_support_and_sees_the_assignment(
    admin, page, make_user, sign_in
):
    coordinator = make_user("event_coordinator")
    organiser = make_user("event_organiser")
    make_user("technical_support")
    suffix = uuid.uuid4().hex[:6]
    event = (
        admin.schema("events")
        .table("events")
        .insert(
            {
                "organiser_id": organiser["id"],
                "status": "planning",
                "assigned_coordinator_id": coordinator["id"],
                "name": f"spm-e2e S43 Event {suffix}",
                "purpose": "Prove automatic Technical Support assignment",
                "start_date": "2026-11-13",
                "start_time": "09:00",
                "end_date": "2026-11-13",
                "end_time": "12:00",
                "expected_attendance": 40,
                "decision": "approved",
                "decided_at": "2026-09-29T08:30:00+00:00",
                "submitted_at": "2026-09-29T08:00:00+00:00",
            }
        )
        .execute()
        .data[0]
    )

    sign_in(coordinator)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    page.goto(f"/coordinator/events/{event['id']}")
    page.get_by_role("heading", name="Technical support").wait_for(timeout=20000)
    page.get_by_text("Technical Support has not been requested for this event.").wait_for()
    page.get_by_label("Support details (optional)").fill(
        "Wireless microphone setup and sound check"
    )
    page.get_by_role("button", name="Request technical support").click()
    page.get_by_text("Technical Support assigned", exact=True).wait_for(timeout=20000)

    stored = (
        admin.schema("events")
        .table("events")
        .select("*")
        .eq("id", event["id"])
        .execute()
        .data[0]
    )
    assert stored["technical_support_required"] is True
    assert stored["technical_support_details"] == (
        "Wireless microphone setup and sound check"
    )
    assert stored["assigned_technical_support_id"] is not None
    assigned_profile = (
        admin.schema("users")
        .table("users")
        .select("email")
        .eq("id", stored["assigned_technical_support_id"])
        .execute()
        .data[0]
    )
    page.get_by_text(assigned_profile["email"], exact=False).wait_for()

    page.reload()
    page.get_by_role("heading", name="Technical support").wait_for(timeout=20000)
    page.get_by_text("Technical Support assigned", exact=True).wait_for(timeout=20000)
    page.get_by_text(assigned_profile["email"], exact=False).wait_for()
    assert page.get_by_label("Support details (optional)").input_value() == (
        "Wireless microphone setup and sound check"
    )
