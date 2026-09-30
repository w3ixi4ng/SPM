"""TC-E2E-222 -- Technical Support checks equipment availability (S-44).

The counting rules are TC-EQUIPMENTREQUIREMENTS-012 onward. This proves the
page is reachable through Kong and the SPA fallback, shows what is reserved
and by whom, and shows a change on the next check.
"""

import re
import uuid
from datetime import date, timedelta

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def d(days: int) -> date:
    # The browser runs on this machine, so its today is this today.
    return date.today() + timedelta(days=days)


def test_technical_support_checks_a_window_and_rechecks_after_a_change(admin, page, make_user, sign_in):
    support = make_user("technical_support")
    organiser = make_user("event_organiser")
    item_type = f"spm-e2e S44 Mic {uuid.uuid4().hex[:6]}"
    item = admin.schema("equipment").table("equipment").insert({
        "type": item_type, "total_quantity": 10, "created_by": support["id"],
    }).execute().data[0]
    event_day = d(3)
    events = []

    def hold(label, quantity):
        # Attributed to the organiser, so make_user's teardown deletes the event.
        event = admin.schema("events").table("events").insert({
            "organiser_id": organiser["id"], "assigned_coordinator_id": organiser["id"],
            "status": "planning", "decision": "approved", "name": f"spm-e2e S44 {label} {item_type[-6:]}",
            "purpose": "Availability check", "start_date": event_day.isoformat(), "start_time": "10:00",
            "end_date": event_day.isoformat(), "end_time": "11:00", "expected_attendance": 10,
            "submitted_at": "2026-09-30T00:00:00Z", "decided_at": "2026-10-01T00:00:00Z",
        }).execute().data[0]
        events.append(event)
        admin.schema("equipment").table("requirements").insert({
            "event_id": event["id"], "equipment_item_id": item["id"],
            "required_quantity": quantity, "recorded_by_coordinator_id": organiser["id"],
        }).execute()
        return event

    try:
        first = hold("First", 7)

        # 1. From the dashboard to the page, which survives a reload.
        sign_in(support)
        page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
        page.get_by_role("link", name="Check availability").click()
        page.wait_for_url(re.compile(r"/equipment/availability$"), timeout=20000)
        page.reload()
        page.get_by_role("heading", name="Check equipment availability").wait_for(timeout=20000)
        expect(page.get_by_role("link", name="Back to dashboard")).to_be_visible()
        expect(page.get_by_label("Start date")).to_have_attribute("min", d(0).isoformat())

        # 2. Check the window with a type and a quantity.
        page.get_by_label("Start date").fill(event_day.isoformat())
        page.get_by_label("Start time").fill("09:00")
        page.get_by_label("End date").fill(event_day.isoformat())
        page.get_by_label("End time").fill("12:00")
        page.get_by_label("Equipment type (optional)").fill(item_type)
        page.get_by_label("Quantity needed (optional)").fill("4")
        page.get_by_role("button", name="Check availability").click()

        results = page.get_by_role("list", name="Equipment availability")
        row = results.get_by_role("listitem").filter(has_text=item_type).first
        expect(row).to_contain_text("3 of 10 available", timeout=20000)
        expect(row).to_contain_text("7 reserved")
        expect(row).to_contain_text("Not enough — 3 available")
        expect(page.get_by_role("status")).to_contain_text("Checked at")
        first_checked = page.get_by_role("status").inner_text()

        # 3. Expand to see which event holds it.
        row.get_by_role("button", name=re.compile(r"Show the event holding it")).click()
        holders = page.get_by_role("list", name=f"Events holding {item_type}")
        expect(holders).to_contain_text(first["name"])
        expect(holders).to_contain_text("10:00–11:00")
        expect(holders).to_contain_text("Planning")

        # 4. Another event claims 2 more; the next check shows it.
        hold("Second", 2)
        page.get_by_role("button", name="Check availability").click()
        expect(row).to_contain_text("1 of 10 available", timeout=20000)
        expect(row).to_contain_text("9 reserved")
        assert page.get_by_role("status").inner_text() >= first_checked
    finally:
        for event in events:
            admin.schema("equipment").table("requirements").delete().eq("event_id", event["id"]).execute()
        admin.schema("equipment").table("equipment").delete().eq("id", item["id"]).execute()
