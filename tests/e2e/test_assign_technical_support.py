"""S-43 Technical Support assignment journeys."""

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


# --- TC-E2E-226 -----------------------------------------------------------
def test_support_staff_see_only_their_active_assigned_events_and_equipment(
    admin, page, make_user, sign_in
):
    # Creation order matters to the shared fixture cleanup: requirements are
    # removed with the Coordinator before catalogue items are removed with A.
    coordinator = make_user("event_coordinator")
    organiser = make_user("event_organiser")
    support_a = make_user("technical_support")
    support_b = make_user("technical_support")
    suffix = uuid.uuid4().hex[:6]

    def equipment(label: str) -> dict:
        return (
            admin.schema("equipment")
            .table("equipment")
            .insert(
                {
                    "type": f"spm-e2e S43 {label} {suffix}",
                    "description": "S-43 staff visibility fixture",
                    "total_quantity": 10,
                    "created_by": support_a["id"],
                }
            )
            .execute()
            .data[0]
        )

    def assigned_event(label: str, status: str, support: dict, notes: str) -> dict:
        return (
            admin.schema("events")
            .table("events")
            .insert(
                {
                    "organiser_id": organiser["id"],
                    "assigned_coordinator_id": coordinator["id"],
                    "status": status,
                    "name": f"spm-e2e S43 {label} {suffix}",
                    "purpose": "Prove assigned-event visibility",
                    "start_date": "2026-11-16",
                    "start_time": "09:00",
                    "end_date": "2026-11-16",
                    "end_time": "12:00",
                    "expected_attendance": 50,
                    "decision": "approved",
                    "decided_at": "2026-10-01T00:00:00Z",
                    "submitted_at": "2026-09-30T00:00:00Z",
                    "technical_support_required": True,
                    "technical_support_details": notes,
                    "assigned_technical_support_id": support["id"],
                    "technical_support_assigned_at": "2026-10-01T01:00:00Z",
                }
            )
            .execute()
            .data[0]
        )

    microphone = equipment("A microphone")
    old_speaker = equipment("A old speaker")
    projector = equipment("B projector")
    event_a = assigned_event(
        "A active", "planning", support_a, "A sound-check notes"
    )
    event_a_old = assigned_event(
        "A cancelled", "cancelled", support_a, "A historical notes"
    )
    event_b = assigned_event(
        "B active", "planning", support_b, "B projection notes"
    )

    for event, item, quantity in (
        (event_a, microphone, 2),
        (event_a_old, old_speaker, 3),
        (event_b, projector, 4),
    ):
        admin.schema("equipment").table("requirements").insert(
            {
                "event_id": event["id"],
                "equipment_item_id": item["id"],
                "required_quantity": quantity,
                "recorded_by_coordinator_id": coordinator["id"],
            }
        ).execute()

    sign_in(support_a)
    page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
    catalogue = page.get_by_role("list", name="Equipment catalogue")
    catalogue.get_by_text(microphone["type"], exact=True).wait_for(timeout=20000)
    catalogue.get_by_text(old_speaker["type"], exact=True).wait_for()
    catalogue.get_by_text(projector["type"], exact=True).wait_for()

    assigned = page.get_by_role("list", name="Assigned events")
    assigned.get_by_text(event_a["name"], exact=True).wait_for(timeout=20000)
    assigned.get_by_text("A sound-check notes", exact=False).wait_for()
    assigned.get_by_role(
        "list", name=f"{event_a['name']} equipment requirements"
    ).get_by_text(microphone["type"], exact=True).wait_for()
    assert assigned.get_by_text(event_a_old["name"], exact=True).count() == 0
    assert assigned.get_by_text(event_b["name"], exact=True).count() == 0
    assert assigned.get_by_text(old_speaker["type"], exact=True).count() == 0
    assert assigned.get_by_text(projector["type"], exact=True).count() == 0

    page.reload()
    assigned = page.get_by_role("list", name="Assigned events")
    assigned.get_by_text(event_a["name"], exact=True).wait_for(timeout=20000)
    assigned.get_by_text(microphone["type"], exact=True).wait_for()

    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=20000)
    sign_in(support_b)
    page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
    assigned = page.get_by_role("list", name="Assigned events")
    assigned.get_by_text(event_b["name"], exact=True).wait_for(timeout=20000)
    assigned.get_by_text("B projection notes", exact=False).wait_for()
    assigned.get_by_role(
        "list", name=f"{event_b['name']} equipment requirements"
    ).get_by_text(projector["type"], exact=True).wait_for()
    assert assigned.get_by_text(event_a["name"], exact=True).count() == 0
    assert assigned.get_by_text(microphone["type"], exact=True).count() == 0
