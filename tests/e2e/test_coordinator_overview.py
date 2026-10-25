"""TC-E2E-238 and TC-E2E-237 -- Lead oversight, integrity, and reassignment."""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


def test_lead_overview_tracks_reassignment(page, make_user, sign_in, admin):
    organiser = make_user("event_organiser")
    lead = make_user("event_coordinator_lead")
    former = make_user("event_coordinator")
    new = make_user("event_coordinator")
    event_name = f"Oversight Forum {uuid.uuid4().hex[:6]}"

    for user, name in (
        (organiser, "Ada Organiser"),
        (former, "Alex Coordinator"),
        (new, "Blair Coordinator"),
    ):
        admin.schema("users").table("users").update({"name": name}).eq(
            "id", user["id"]
        ).execute()

    admin.schema("events").table("events").insert(
        {
            "organiser_id": organiser["id"],
            "status": "submitted",
            "assigned_coordinator_id": former["id"],
            "assigning_lead_id": lead["id"],
            "name": event_name,
            "purpose": "Exercise the S-85 browser workflow",
            "start_date": "2026-11-18",
            "start_time": "09:00",
            "end_date": "2026-11-18",
            "end_time": "12:00",
            "expected_attendance": 120,
            "submitted_at": "2026-10-09T00:00:00Z",
        }
    ).execute()

    sign_in(lead)
    page.wait_for_url(
        re.compile(r"/dashboard/event-coordinator-lead$"), timeout=20000
    )
    page.get_by_role("heading", name="Unassigned event requests").wait_for(
        timeout=20000
    )
    page.get_by_role("heading", name="Coordinator oversight").wait_for(
        timeout=20000
    )

    former_group = page.get_by_role(
        "article", name="Alex Coordinator coordinator overview"
    )
    new_group = page.get_by_role(
        "article", name="Blair Coordinator coordinator overview"
    )
    former_group.get_by_text("1 active assignment", exact=True).wait_for(
        timeout=20000
    )
    new_group.get_by_text("0 active assignments", exact=True).wait_for(
        timeout=20000
    )
    new_group.get_by_text("No active events assigned.", exact=True).wait_for()

    event = former_group.get_by_role("listitem").filter(has_text=event_name)
    event.get_by_text(event_name, exact=True).wait_for()
    event.get_by_text("Submitted", exact=True).wait_for()
    event.get_by_text("2026-11-18 09:00 – 2026-11-18 12:00", exact=True).wait_for()
    event.get_by_text("Organiser: Ada Organiser", exact=True).wait_for()
    event.get_by_text("Current Coordinator: Alex Coordinator", exact=True).wait_for()

    event.get_by_label(f"New Event Coordinator for {event_name}").select_option(
        new["id"]
    )
    event.get_by_role("button", name="Reassign event").click()
    page.get_by_text(
        f"{event_name} was reassigned to Blair Coordinator.", exact=True
    ).wait_for(timeout=30000)

    former_group.get_by_text("0 active assignments", exact=True).wait_for(
        timeout=20000
    )
    former_group.get_by_text("No active events assigned.", exact=True).wait_for()
    new_group.get_by_text("1 active assignment", exact=True).wait_for(timeout=20000)
    moved = new_group.get_by_role("listitem").filter(has_text=event_name)
    moved.get_by_text("Current Coordinator: Blair Coordinator", exact=True).wait_for()

    page.reload()
    refreshed_new_group = page.get_by_role(
        "article", name="Blair Coordinator coordinator overview"
    )
    refreshed_new_group.get_by_text("1 active assignment", exact=True).wait_for(
        timeout=20000
    )
    refreshed_new_group.get_by_text(event_name, exact=True).wait_for()
    page.get_by_role(
        "article", name="Alex Coordinator coordinator overview"
    ).get_by_text("0 active assignments", exact=True).wait_for()


def test_lead_sees_profileless_coordinator_and_invalid_assignment_separately(
    page, make_user, sign_in, admin
):
    organiser = make_user("event_organiser")
    lead = make_user("event_coordinator_lead")
    former = make_user("event_coordinator")
    profileless = make_user("event_coordinator")
    admin.schema("users").table("users").update({"name": "Alex Coordinator"}).eq(
        "id", former["id"]
    ).execute()
    admin.schema("users").table("users").delete().eq(
        "id", profileless["id"]
    ).execute()

    deleted = admin.auth.admin.create_user({
        "email": f"spm-e2e-{uuid.uuid4().hex[:12]}@example.com",
        "password": "correct-horse-battery-staple",
        "email_confirm": True,
        "app_metadata": {"role": "event_coordinator"},
    }).user
    deleted_id = str(deleted.id)
    admin.auth.admin.delete_user(deleted_id)

    valid_name = f"S-85 valid {uuid.uuid4().hex[:6]}"
    orphan_name = f"S-85 orphan {uuid.uuid4().hex[:6]}"
    def seed(name, owner_id):
        return admin.schema("events").table("events").insert({
            "organiser_id": organiser["id"],
            "status": "submitted",
            "assigned_coordinator_id": owner_id,
            "assigning_lead_id": lead["id"],
            "name": name,
            "purpose": "S-85 browser integrity regression",
            "start_date": "2026-11-18",
            "start_time": "09:00",
            "end_date": "2026-11-18",
            "end_time": "12:00",
            "expected_attendance": 20,
            "submitted_at": "2026-10-09T00:00:00Z",
        }).execute().data[0]

    valid = seed(valid_name, former["id"])
    seed(orphan_name, deleted_id)
    sign_in(lead)
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator-lead$"), timeout=20000)

    former_group = page.get_by_role("article", name="Alex Coordinator coordinator overview")
    new_group = page.get_by_role(
        "article", name=f"{profileless['email']} coordinator overview"
    )
    former_group.get_by_text("1 active assignment", exact=True).wait_for(timeout=20000)
    new_group.get_by_text("0 active assignments", exact=True).wait_for(timeout=20000)
    warning = page.get_by_role("alert").filter(has_text="Assignment data needs review")
    warning.get_by_text(orphan_name, exact=False).wait_for(timeout=20000)
    assert page.locator("article").filter(has_text=orphan_name).count() == 0

    event = former_group.get_by_role("listitem").filter(has_text=valid_name)
    assert event.get_by_label(
        f"New Event Coordinator for {valid_name}"
    ).locator(f"option[value='{profileless['id']}']").inner_text() == profileless["email"]
    event.get_by_label(f"New Event Coordinator for {valid_name}").select_option(
        profileless["id"]
    )
    event.get_by_role("button", name="Reassign event").click()
    former_group.get_by_text("0 active assignments", exact=True).wait_for(timeout=30000)
    new_group.get_by_text("1 active assignment", exact=True).wait_for(timeout=30000)
    new_group.get_by_text(valid_name, exact=True).wait_for()

    page.reload()
    page.get_by_role(
        "article", name=f"{profileless['email']} coordinator overview"
    ).get_by_text("1 active assignment", exact=True).wait_for(timeout=20000)
    page.get_by_role("heading", name="Unassigned event requests").wait_for()
    page.get_by_role("alert").filter(
        has_text="Assignment data needs review"
    ).get_by_text(orphan_name, exact=False).wait_for()
