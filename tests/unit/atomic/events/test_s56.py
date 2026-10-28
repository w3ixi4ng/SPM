"""S-56: the Attendee read says whether an event's details are confirmed.

TC-EVENTS-187. Supabase filters by status, so the fake checks which statuses
the route asks for and that only the published columns, plus status, are
selected.
"""

from types import SimpleNamespace

from .conftest import EVENT_ID

ATTENDEE_VIEW = f"/internal/events/attendee-view/{EVENT_ID}"
PUBLISHED_KEYS = {
    "id", "name", "purpose", "start_date", "start_time", "end_date", "end_time",
    "registration_required", "registration_opens_at", "registration_closes_at",
    "expected_attendance", "registration_closed_at",
}


def _row(status):
    return {
        "id": EVENT_ID,
        "name": "Alumni networking evening",
        "purpose": "Reconnect alumni with current students",
        "start_date": "2026-11-20",
        "start_time": "18:00:00",
        "end_date": "2026-11-20",
        "end_time": "21:00:00",
        "registration_required": True,
        "registration_opens_at": "2026-11-01T09:00:00",
        "registration_closes_at": "2026-11-15T18:00:00",
        "expected_attendance": 50,
        "registration_closed_at": None,
        "status": status,
    }


def _answers(db, rows):
    select = db.schema.return_value.table.return_value.select
    select.return_value.eq.return_value.in_.return_value.execute.return_value = (
        SimpleNamespace(data=rows)
    )
    return select


# --- TC-EVENTS-187 ----------------------------------------------------------
def test_the_attendee_read_says_whether_the_details_are_confirmed(client, db):
    select = _answers(db, [_row("planning")])

    result = client.get(ATTENDEE_VIEW)

    assert result.status_code == 200
    body = result.json()
    assert set(body) == PUBLISHED_KEYS | {"status"}
    assert body["status"] == "planning"
    columns = set(select.call_args.args[0].split(","))
    assert columns == PUBLISHED_KEYS | {"status"}
    for internal in ("organiser_id", "assigned_coordinator_id", "safety_decision_reason", "edit_history"):
        assert internal not in columns
    select.return_value.eq.assert_called_once_with("id", EVENT_ID)
    statuses = select.return_value.eq.return_value.in_.call_args.args
    assert statuses[0] == "status"
    assert sorted(statuses[1]) == sorted(
        ["confirmed", "planning", "pending_safety_check", "safety_changes_requested"]
    )


def test_an_event_attendees_may_not_see_is_not_found(client, db):
    _answers(db, [])

    result = client.get(ATTENDEE_VIEW)

    assert result.status_code == 404
    assert result.json()["detail"] == "Event not found."
