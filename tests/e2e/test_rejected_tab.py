"""TC-E2E-208 -- rejected requests sit in their own tab (S-13).

The grouping and labels are TC-FRONTEND-026/027's job. This proves the tabs
render and switch in a real browser, and that a rejected row still opens the
locked form rather than being a dead end.
"""

import re
import uuid

from .conftest import requires_env

pytestmark = requires_env

REASON = "The venue is closed for renovation that week"


def _event(organiser_id, name, **status_fields):
    return {
        "organiser_id": organiser_id,
        "name": name,
        "purpose": "Faculty open house",
        "start_date": "2026-11-26",
        "start_time": "09:00",
        "end_date": "2026-11-26",
        "end_time": "11:00",
        "expected_attendance": 40,
        "venue": "Seminar Room 3",
        "submitted_at": "2026-09-18T09:00:00+00:00",
        **status_fields,
    }


# --- TC-E2E-208 -----------------------------------------------------------
def test_rejected_requests_sit_in_their_own_tab_and_open_read_only(admin, page, make_user, sign_in):
    organiser = make_user("event_organiser")
    suffix = uuid.uuid4().hex[:6]
    active_name = f"spm-e2e Active {suffix}"
    rejected_name = f"spm-e2e Rejected {suffix}"
    # Attributed to the organiser, so make_user's teardown deletes both.
    events = admin.schema("events").table("events")
    events.insert(_event(organiser["id"], active_name, status="submitted")).execute()
    rejected = (
        events.insert(
            _event(
                organiser["id"],
                rejected_name,
                status="rejected",
                decision="rejected",
                decision_reason=REASON,
                decided_at="2026-09-20T10:00:00+00:00",
            )
        )
        .execute()
        .data[0]
    )

    sign_in(organiser)
    page.wait_for_url(re.compile(r"/dashboard"), timeout=20000)

    active_tab = page.get_by_role("tab", name="Active (1)")
    active_tab.wait_for(timeout=20000)
    assert active_tab.get_attribute("aria-selected") == "true"
    panel = page.get_by_role("tabpanel")
    panel.get_by_role("link").filter(has_text=active_name).get_by_text("Under review").wait_for()
    assert panel.get_by_text(rejected_name).count() == 0

    page.get_by_role("tab", name="Rejected (1)").click()
    rejected_row = panel.get_by_role("link").filter(has_text=rejected_name)
    rejected_row.get_by_text("Rejected", exact=True).wait_for(timeout=20000)
    assert panel.get_by_text(active_name).count() == 0
    assert panel.get_by_role("link").count() == 1

    rejected_row.click()
    page.wait_for_url(re.compile(rf"/events/{rejected['id']}$"), timeout=20000)
    page.get_by_text("This request has been rejected and is closed.").wait_for(timeout=20000)
    page.get_by_text(f"Reason: {REASON}").wait_for()
    assert page.locator("#event-attendance").is_disabled()
