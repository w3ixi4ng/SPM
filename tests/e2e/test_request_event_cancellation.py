"""TC-E2E-233 -- an Organiser confirms a cancellation request, and the event is
not shown as cancelled (S-62).

Eligibility, validation and failure handling are TC-EVENTS-123..129 and
TC-FRONTEND-104/105's job and are not restaged here. This proves the confirm
step, the gateway route, and that the request survives a reload without the
status changing.
"""

import re
import uuid
from datetime import date

from playwright.sync_api import expect

from .conftest import requires_env

pytestmark = requires_env

REASON = "Keynote speaker withdrew"


def stored(admin, event_id):
    return admin.schema("events").table("events").select(
        "status,cancellation_reason,cancellation_requested_at"
    ).eq("id", event_id).execute().data[0]


# --- TC-E2E-233 -----------------------------------------------------------
def test_an_organiser_confirms_a_cancellation_request_and_the_event_is_not_cancelled(
    admin, page, make_user, sign_in
):
    organiser = make_user("event_organiser")
    # Attributed to the organiser, so make_user's teardown deletes it.
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser["id"],
        "status": "planning",
        "name": f"spm-e2e Cancel {uuid.uuid4().hex[:6]}",
        "purpose": "Reconnect graduates with faculty",
        "start_date": "2026-11-12",
        "start_time": "09:00",
        "end_date": "2026-11-12",
        "end_time": "18:00",
        "expected_attendance": 120,
        "decision": "approved",
        "decided_at": "2026-10-01T00:00:00+00:00",
        "submitted_at": "2026-09-30T00:00:00+00:00",
    }).execute().data[0]

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)
    page.goto(f"/events/{event['id']}")
    panel = page.get_by_role("dialog")

    # 1-2. Reviewing and then keeping the event sends nothing.
    page.get_by_role("button", name="Request cancellation").click()
    panel.get_by_label("Why does this event need to be cancelled?").fill(REASON)
    panel.get_by_role("button", name="Review request").click()
    expect(panel.get_by_role("heading", name="Cancel this event?")).to_be_visible(timeout=20000)
    expect(panel.get_by_text(REASON)).to_be_visible()
    panel.get_by_role("button", name="Keep event").click()
    expect(panel).to_have_count(0)
    assert stored(admin, event["id"])["cancellation_requested_at"] is None

    # 3. Confirming sends it.
    page.get_by_role("button", name="Request cancellation").click()
    panel.get_by_label("Why does this event need to be cancelled?").fill(REASON)
    panel.get_by_role("button", name="Review request").click()
    panel.get_by_role("button", name="Send cancellation request").click()
    expect(page.get_by_text(
        "Cancellation request sent. Your event stays in planning until it has been reviewed."
    )).to_be_visible(timeout=20000)

    # 4. After a reload: still Planning, the request shown, no second button.
    page.reload()
    today = date.today().strftime("%d %b %Y").lstrip("0")
    expect(page.get_by_text(f"Cancellation requested on {today}")).to_be_visible(timeout=20000)
    expect(page.get_by_text(REASON)).to_be_visible()
    expect(page.get_by_text("Planning", exact=True)).to_be_visible()
    expect(page.get_by_text("Cancelled", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Request cancellation")).to_have_count(0)

    row = stored(admin, event["id"])
    assert row["status"] == "planning"
    assert row["cancellation_reason"] == REASON
