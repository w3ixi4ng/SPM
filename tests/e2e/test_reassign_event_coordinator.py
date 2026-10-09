"""TC-E2E-227 -- Lead reassignment, access transfer, and notifications."""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


def test_lead_reassigns_event_and_transfers_access(
    page, make_user, sign_in, admin
):
    organiser = make_user("event_organiser")
    lead = make_user("event_coordinator_lead")
    former = make_user("event_coordinator")
    new = make_user("event_coordinator")
    event_name = f"Reassignment Forum {uuid.uuid4().hex[:6]}"

    admin.schema("users").table("users").update({"name": "Alex Coordinator"}).eq(
        "id", former["id"]
    ).execute()
    admin.schema("users").table("users").update({"name": "Blair Coordinator"}).eq(
        "id", new["id"]
    ).execute()
    admin.schema("events").table("events").insert(
        {
            "organiser_id": organiser["id"],
            "status": "submitted",
            "assigned_coordinator_id": new["id"],
            "name": "Overlapping coordinator work",
            "purpose": "Prove overlap does not block reassignment",
            "start_date": "2026-11-18",
            "start_time": "10:00",
            "end_date": "2026-11-18",
            "end_time": "11:00",
            "expected_attendance": 5,
            "submitted_at": "2026-10-08T00:00:00Z",
        }
    ).execute()
    admin.schema("events").table("events").insert(
        {
            "organiser_id": organiser["id"],
            "status": "submitted",
            "assigned_coordinator_id": former["id"],
            "name": event_name,
            "purpose": "Exercise the S-84 browser workflow",
            "start_date": "2026-11-18",
            "start_time": "09:00",
            "end_date": "2026-11-18",
            "end_time": "12:00",
            "expected_attendance": 120,
            "submitted_at": "2026-10-08T00:00:00Z",
        }
    ).execute()

    sign_in(lead)
    page.wait_for_url(
        re.compile(r"/dashboard/event-coordinator-lead$"), timeout=20000
    )
    card = page.get_by_role("listitem").filter(has_text=event_name)
    card.get_by_text("Current Coordinator: Alex Coordinator", exact=True).wait_for(
        timeout=20000
    )
    card.get_by_label(f"New Event Coordinator for {event_name}").select_option(
        new["id"]
    )
    card.get_by_role("button", name="Reassign event").click()
    page.get_by_text(
        f"{event_name} was reassigned to Blair Coordinator.", exact=True
    ).wait_for(timeout=30000)
    card.get_by_text("Current Coordinator: Blair Coordinator", exact=True).wait_for(
        timeout=20000
    )
    page.get_by_role("button", name="Sign out").click()

    sign_in(former)
    former_message = (
        f"{event_name} has been reassigned to Blair Coordinator. "
        "You are no longer the assigned Event Coordinator."
    )
    page.get_by_text(former_message, exact=True).wait_for(timeout=20000)
    page.reload()
    page.get_by_text(former_message, exact=True).wait_for(timeout=20000)
    page.get_by_role("tab", name="Events").click()
    page.get_by_text("No event requests have been routed to you yet.").wait_for(
        timeout=20000
    )
    assert page.get_by_text(event_name, exact=True).count() == 0
    page.get_by_role("button", name="Sign out").click()

    sign_in(new)
    new_message = f"You have been assigned to {event_name}."
    page.get_by_text(new_message, exact=True).wait_for(timeout=20000)
    page.get_by_role("tab", name="Events").click()
    page.get_by_text(event_name, exact=True).wait_for(timeout=20000)
    page.reload()
    page.get_by_text(new_message, exact=True).wait_for(timeout=20000)
    page.get_by_role("button", name="Sign out").click()

    sign_in(organiser)
    organiser_message = (
        f"{event_name} has been reassigned from Alex Coordinator to Blair Coordinator."
    )
    page.get_by_text(organiser_message, exact=True).wait_for(timeout=20000)
    page.reload()
    page.get_by_text(organiser_message, exact=True).wait_for(timeout=20000)
