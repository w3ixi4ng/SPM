"""TC-E2E-212 -- Technical Support edits an equipment catalogue item."""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env


# --- TC-E2E-212 -----------------------------------------------------------
def test_technical_support_updates_equipment_and_sees_it_immediately(
    admin, page, make_user, sign_in
):
    support = make_user("technical_support")
    suffix = uuid.uuid4().hex[:6]
    original_type = f"spm-e2e S41 Microphone {suffix}"
    updated_type = f"spm-e2e S41 Radio Microphone {suffix}"
    item = (
        admin.schema("equipment")
        .table("equipment")
        .insert(
            {
                "type": original_type,
                "description": "Before browser edit",
                "total_quantity": 12,
                "operational_status": "available",
                "lifecycle_status": "active",
                "created_by": support["id"],
            }
        )
        .execute()
        .data[0]
    )

    sign_in(support)
    page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
    page.get_by_role("link", name=f"Edit {original_type}").click()
    page.wait_for_url(re.compile(rf"/equipment/{item['id']}/edit$"), timeout=20000)

    type_input = page.get_by_label("Type or name (required)")
    type_input.wait_for(timeout=20000)
    assert type_input.input_value() == original_type
    assert page.get_by_label("Description (optional)").input_value() == "Before browser edit"
    assert page.get_by_label("Total quantity (required)").input_value() == "12"
    assert page.get_by_label("Operational status (required)").input_value() == "available"

    type_input.fill(updated_type)
    page.get_by_label("Description (optional)").fill("Updated in browser")
    page.get_by_label("Total quantity (required)").fill("18")
    page.get_by_label("Operational status (required)").select_option("maintenance")
    page.get_by_role("button", name="Save changes").click()

    page.wait_for_url(re.compile(r"/dashboard/technical-support$"), timeout=20000)
    page.get_by_text(f"{updated_type} was updated in the equipment catalogue.").wait_for(
        timeout=20000
    )
    catalogue = page.get_by_role("list", name="Equipment catalogue")
    row = catalogue.get_by_role("listitem").filter(has_text=updated_type)
    row.wait_for(timeout=20000)
    row.get_by_text("Updated in browser", exact=True).wait_for()
    row.get_by_text("18 total", exact=True).wait_for()
    row.get_by_text("Maintenance · Active", exact=True).wait_for()

    stored = (
        admin.schema("equipment")
        .table("equipment")
        .select("*")
        .eq("id", item["id"])
        .execute()
        .data[0]
    )
    assert stored["type"] == updated_type
    assert stored["description"] == "Updated in browser"
    assert stored["total_quantity"] == 18
    assert stored["operational_status"] == "maintenance"
    assert stored["lifecycle_status"] == "active"
