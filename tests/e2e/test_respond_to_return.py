"""TC-E2E-207 -- an organiser responds to a returned request (S-13).

The one thing only a browser proves here: the organiser sees what the
coordinator asked for on the page, amends the form, and resubmits it through
Kong as the same request. That the stored record is right, and that a failed
resubmission changes nothing, is TC-EVENTREQUESTS-105/106's job.
"""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env

REASON = "Expected attendance exceeds the venue's capacity"
COMMENT = "Reduce attendance to 80 or choose a larger venue"


# --- TC-E2E-207 -----------------------------------------------------------
def test_an_organiser_responds_to_a_returned_request_and_resubmits(admin, page, make_user, sign_in):
    organiser = make_user("event_organiser")
    coordinator = make_user("event_coordinator")
    name = f"spm-e2e Returned {uuid.uuid4().hex[:6]}"
    # Attributed to the organiser, so make_user's teardown deletes it. The
    # return is written directly: the coordinator's decision is S-14's to
    # prove, and this journey starts from a request that has come back.
    event = (
        admin.schema("events")
        .table("events")
        .insert(
            {
                "organiser_id": organiser["id"],
                "assigned_coordinator_id": coordinator["id"],
                "name": name,
                "purpose": "Welcome new students to the faculty",
                "start_date": "2026-11-19",
                "start_time": "09:00",
                "end_date": "2026-11-19",
                "end_time": "11:00",
                "expected_attendance": 120,
                "venue": "Seminar Room 3",
                "submitted_at": "2026-09-18T09:00:00+00:00",
                "status": "returned",
                "decision": "returned",
                "decision_reason": REASON,
                "decision_comment": COMMENT,
                "decided_at": "2026-09-20T10:00:00+00:00",
            }
        )
        .execute()
        .data[0]
    )

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard"), timeout=20000)

    request_link = page.get_by_role("link").filter(has_text=name)
    request_link.get_by_text("Action required").wait_for(timeout=20000)
    request_link.click()
    page.wait_for_url(re.compile(rf"/events/{event['id']}$"), timeout=20000)

    page.get_by_text("This request was returned for amendment").wait_for(timeout=20000)
    page.get_by_text(f"Reason: {REASON}").wait_for()
    page.get_by_text(f"Note from the coordinator: {COMMENT}").wait_for()

    page.locator("#event-attendance").fill("80")
    page.get_by_role("button", name="Resubmit request").click()

    page.get_by_text("Request submitted.").wait_for(timeout=30000)
    assert re.search(rf"/events/{event['id']}$", page.url)
    assert page.get_by_text("This request was returned for amendment").count() == 0

    page.goto("/dashboard")
    rows = page.get_by_role("link").filter(has_text=name)
    rows.first.get_by_text("Under review").wait_for(timeout=20000)
    assert rows.count() == 1
