"""TC-E2E-260 -- Technical Support records and uses equipment storage metadata."""

import re
import uuid
from datetime import date, timedelta

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


def test_storage_location_is_recorded_edited_and_shown_in_availability(
    admin, page, make_user, sign_in
):
    support = make_user("technical_support")
    suffix = uuid.uuid4().hex[:6]
    item_type = f"spm-e2e S92 Projector {suffix}"
    item_id = None

    try:
        sign_in(support)
        page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
        page.get_by_role("link", name="Add equipment").click()
        page.wait_for_url(re.compile(r"/equipment/new$"), timeout=20000)

        page.get_by_label("Type or name (required)").fill(item_type)
        page.get_by_label("Description (optional)").fill("Portable laser projector")
        page.get_by_label("Storage location (optional)").fill("Store B, Shelf 4")
        page.get_by_label("Total quantity (required)").fill("3")
        page.get_by_role("button", name="Add equipment").click()

        page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
        catalogue = page.get_by_role("list", name="Equipment catalogue")
        row = catalogue.get_by_role("listitem").filter(has_text=item_type)
        expect(row).to_contain_text("Stored at Store B, Shelf 4", timeout=20000)

        stored = (
            admin.schema("equipment")
            .table("equipment")
            .select("id")
            .eq("type", item_type)
            .execute()
            .data[0]
        )
        item_id = stored["id"]

        row.get_by_role("link", name=f"Edit {item_type}").click()
        page.wait_for_url(re.compile(rf"/equipment/{item_id}/edit$"), timeout=20000)
        location = page.get_by_label("Storage location (optional)")
        expect(location).to_have_value("Store B, Shelf 4")
        location.fill("AV Cage, Rack 2")
        page.get_by_role("button", name="Save changes").click()

        page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
        row = page.get_by_role("list", name="Equipment catalogue").get_by_role(
            "listitem"
        ).filter(has_text=item_type)
        expect(row).to_contain_text("Stored at AV Cage, Rack 2", timeout=20000)

        page.get_by_role("link", name="Check availability").click()
        page.wait_for_url(re.compile(r"/equipment/availability$"), timeout=20000)
        event_day = date.today() + timedelta(days=3)
        page.get_by_label("Start date").fill(event_day.isoformat())
        page.get_by_label("Start time").fill("09:00")
        page.get_by_label("End date").fill(event_day.isoformat())
        page.get_by_label("End time").fill("12:00")
        page.get_by_label("Equipment type (optional)").fill(item_type)
        page.get_by_role("button", name="Check availability").click()

        result = page.get_by_role("list", name="Equipment availability").get_by_role(
            "listitem"
        ).filter(has_text=item_type)
        expect(result).to_contain_text("Stored at AV Cage, Rack 2", timeout=20000)
        expect(result).to_contain_text("3 of 3 available")
    finally:
        if item_id:
            admin.schema("equipment").table("equipment").delete().eq(
                "id", item_id
            ).execute()
