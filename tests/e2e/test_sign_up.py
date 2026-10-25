"""TC-E2E-201, TC-E2E-253 -- sign up, and land where the chosen role says you should.

The one journey that goes through the real sign-up form rather than seeding an
account. That is the point: it proves the users service stamps
`app_metadata.role`, that `/users/me` reads it back, and that the route guard
sends the browser to the dashboard for that role -- the whole role-assignment
path, which no other test covers in one pass.
"""

import re

import pytest
from playwright.sync_api import expect

from .conftest import PASSWORD, requires_env, unique_email

pytestmark = requires_env


@pytest.fixture
def signed_up(admin):
    """Delete whatever the sign-up form created, addressed by email."""
    emails: list[str] = []
    yield emails

    for email in emails:
        rows = (
            admin.schema("users")
            .table("users")
            .select("id")
            .eq("email", email)
            .execute()
        )
        for row in rows.data or []:
            admin.schema("events").table("events").delete().eq(
                "organiser_id", row["id"]
            ).execute()
            admin.auth.admin.delete_user(row["id"])


# --- TC-E2E-201 -----------------------------------------------------------
def test_sign_up_lands_on_the_organiser_dashboard(page, signed_up):
    email = unique_email()
    signed_up.append(email)

    page.goto("/signup")
    page.fill("#signup-first-name", "Ada")
    page.fill("#signup-last-name", "Lovelace")
    page.fill("#signup-email", email)
    page.fill("#signup-password", PASSWORD)
    page.fill("#signup-confirm-password", PASSWORD)
    page.get_by_role("button", name=re.compile(r"^Event Organiser")).click()
    page.click("button[type=submit]")

    # Either outcome is a working service; which one depends on a project
    # setting rather than on the code.
    page.wait_for_url(re.compile(r"/(dashboard|login)"), timeout=30000)

    if "/login" in page.url:
        pytest.skip(
            "sign-up returned no session: turn off Authentication -> Providers "
            "-> Email -> Confirm email in the TEST Supabase project"
        )

    # Event Organiser was the role chosen, so this is the dashboard the role
    # policy has to resolve to.
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)


# --- TC-E2E-253 -----------------------------------------------------------
def test_an_attendee_sign_up_lands_on_the_attendee_dashboard(page, signed_up):
    email = unique_email()
    signed_up.append(email)

    page.goto("/signup")
    attendee = page.get_by_role("button", name=re.compile(r"^Attendee"))
    organiser = page.get_by_role("button", name=re.compile(r"^Event Organiser"))
    expect(attendee).to_have_attribute("aria-pressed", "false")
    expect(organiser).to_have_attribute("aria-pressed", "false")

    page.fill("#signup-first-name", "Ada")
    page.fill("#signup-last-name", "Lovelace")
    page.fill("#signup-email", email)
    page.fill("#signup-password", PASSWORD)
    page.fill("#signup-confirm-password", PASSWORD)
    page.click("button[type=submit]")

    expect(
        page.get_by_text(
            "Choose whether you're signing up as an Attendee or an Event Organiser."
        )
    ).to_be_visible()
    assert page.url.endswith("/signup")

    attendee.click()
    expect(attendee).to_have_attribute("aria-pressed", "true")
    page.click("button[type=submit]")

    page.wait_for_url(re.compile(r"/(dashboard|login)"), timeout=30000)
    if "/login" in page.url:
        pytest.skip(
            "sign-up returned no session: turn off Authentication -> Providers "
            "-> Email -> Confirm email in the TEST Supabase project"
        )
    page.wait_for_url(re.compile(r"/dashboard/attendee$"), timeout=20000)
