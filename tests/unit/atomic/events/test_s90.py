"""S-90: the event history records a restore being asked for and decided.

TC-EVENTS-209. The venue_bookings composite writes these through the S-82
internal route; the events service only checks the action is one it knows.
"""

import pytest

from .test_s82 import E, db, events, recorded, tables  # noqa: F401 -- fixtures

RESTORE = {
    "actor_role": "event_coordinator",
    "actor_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "details": {"venue_name": "Studio B", "replacement_venue_name": "Hall C"},
}


# --- TC-EVENTS-209 --------------------------------------------------------
@pytest.mark.parametrize(
    "action", ["venue_restore_requested", "venue_restore_confirmed", "venue_restore_declined"]
)
def test_the_history_accepts_the_three_restore_steps(client, tables, action):
    entry = {**RESTORE, "action": action}
    events(tables, select=[[{"id": E}]])
    tables["event_history"].responses = {
        "insert": [[{**entry, "id": 7, "event_id": E, "category": "venue",
                     "occurred_at": "2026-11-01T02:00:00Z"}]]
    }

    response = client.post(f"/internal/events/{E}/history", json=entry)

    assert response.status_code == 201, response.text
    assert recorded(tables) == [{**entry, "event_id": E, "category": "venue"}]
    refused = client.post(f"/internal/events/{E}/history", json={**entry, "action": "venue_restored_somehow"})
    assert refused.status_code == 422
