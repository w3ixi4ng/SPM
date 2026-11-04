"""S-78 revision AC3: confirming a restore to the original venue never
replans the event. TC-VENUEBOOKINGS-409.

Uses the S-90 restore fakes unchanged: the restore keeps the venue the
event's safety check already covered.
"""

from .conftest import fake_response
from .test_s90 import O, O_ID, R, REQUESTED, STAFF, services  # noqa: F401 -- `services` is the fixture

COOKIE = {"sb_access_token": "token"}


# --- TC-VENUEBOOKINGS-409 ----------------------------------------------------
def test_confirming_a_restore_never_replans(client, services):
    services.role, services.user_id = "venue_staff", STAFF
    services.event_status = "confirmed"
    services.original = dict(REQUESTED)
    resolved = {**O, "alternative_resolution_note": "Restored to the original venue"}
    services.answer = fake_response(200, {"booking": resolved, "withdrawn": [{**R, "status": "withdrawn"}]})

    response = client.post(f"/venue-bookings/{O_ID}/restore-decision",
                           json={"decision": "approved"}, cookies=COOKIE)

    assert response.status_code == 200, response.text
    replans = [call for call in services.events.post.call_args_list
               if call.args[0].endswith("/venue-replanning")]
    assert replans == []
    notices = [row for call in services.notifications.post.call_args_list
               for row in call.kwargs.get("json", {}).get("notifications", [])]
    assert not any("is back in planning" in row.get("message", "") for row in notices)
