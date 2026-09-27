"""S-28 browser journeys: TC-E2E-210 and TC-E2E-211."""
import re
import uuid

import pytest
from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env


@pytest.fixture
def editable_venue(admin, make_user):
    creator = make_user("venue_staff")
    return admin.schema("venues").table("venues").insert({
        "name": f"spm-e2e Edit {uuid.uuid4().hex[:8]}",
        "location": "Block A", "capacity": 250,
        "facilities": ["projector"], "accessibility": ["wheelchair_access"],
        "room_layouts": ["theatre"],
        "operating_hours": [{"day": "mon", "open": "09:00", "close": "18:00"}],
        "created_by": creator["id"],
    }).execute().data[0]


def test_staff_edit_refreshes_catalogue_and_persists(page, make_user, sign_in, editable_venue):
    sign_in(make_user("venue_staff"))
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
    name = editable_venue["name"]
    page.get_by_role("link", name=f"Edit {name}", exact=True).click()
    form = page.get_by_role("form", name="Edit venue", exact=True)
    expect(form).to_be_visible(timeout=20000)
    expect(form.locator("#location")).to_have_value("Block A")
    expect(form.locator("#capacity")).to_have_value("250")
    for selector in ("#name", "#description", 'input[name="room_layouts"]', 'input[name="mon-open"]'):
        expect(form.locator(selector)).to_have_count(0)
    form.locator("#location").fill("Block B")
    form.locator("#capacity").fill("0")
    form.get_by_role("button", name="Save venue").click()
    expect(form.locator("#capacity-error")).to_be_visible()
    form.locator("#capacity").fill("100")
    form.get_by_label("Projector", exact=True).uncheck()
    form.get_by_label("Wi-Fi", exact=True).check()
    form.get_by_label("Wheelchair access", exact=True).uncheck()
    form.get_by_label("Lift", exact=True).check()
    form.get_by_role("button", name="Save venue").click()
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=30000)
    row = page.get_by_role("list", name="Venues", exact=True).get_by_role("listitem").filter(has_text=name)
    for text in ("Block B", "Capacity 100", "Wi-Fi", "Lift"):
        expect(row).to_contain_text(text, timeout=20000)
    expect(row).not_to_contain_text("Projector")
    expect(row).not_to_contain_text("Wheelchair access")
    page.reload()
    expect(row).to_contain_text("Capacity 100", timeout=20000)
    page.get_by_role("link", name=f"Edit {name}", exact=True).click()
    expect(form.locator("#location")).to_have_value("Block B", timeout=20000)
    expect(form.get_by_label("Wi-Fi", exact=True)).to_be_checked()
    form.locator("#location").fill("Unsaved location")
    form.get_by_role("link", name="Cancel", exact=True).click()
    expect(row).to_contain_text("Block B", timeout=20000)
    expect(row).not_to_contain_text("Unsaved location")


def test_coordinator_cannot_open_edit(page, make_user, sign_in, editable_venue):
    sign_in(make_user("event_coordinator"))
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    expect(page.get_by_role("list", name="Venues", exact=True)).to_contain_text(editable_venue["name"], timeout=20000)
    expect(page.get_by_role("link", name=re.compile(r"^Edit "))).to_have_count(0)
    page.goto(f"/venues/{editable_venue['id']}/edit")
    page.wait_for_url(re.compile(r"/dashboard/event-coordinator$"), timeout=20000)
    expect(page.get_by_role("form", name="Edit venue", exact=True)).to_have_count(0)
