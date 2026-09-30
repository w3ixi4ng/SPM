"""S-44: POST /events/overlapping, the live events overlapping a window.

Composite-only, like /events/coordinator-load: no session, no Kong route.
"""

from types import SimpleNamespace

import pytest

WINDOW = {"start_date": "2026-11-12", "start_time": "09:00", "end_date": "2026-11-12", "end_time": "12:00"}


def window_query(db):
    """The storage chain: .select().in_(status).lte(start_date).gte(end_date)."""
    return db.schema.return_value.table.return_value.select.return_value.in_.return_value.lte.return_value.gte.return_value


def row(event_id, status, start_date, start_time, end_date, end_time):
    return {
        "id": event_id, "name": f"Event {event_id[:2]}", "status": status,
        "start_date": start_date, "start_time": start_time, "end_date": end_date, "end_time": end_time,
    }


E1 = row("e1e1e1e1-0000-4000-8000-000000000001", "planning", "2026-11-12", "10:00:00", "2026-11-12", "11:00:00")
E2 = row("e2e2e2e2-0000-4000-8000-000000000002", "confirmed", "2026-11-12", "11:30:00", "2026-11-12", "13:00:00")
E4 = row("e4e4e4e4-0000-4000-8000-000000000004", "planning", "2026-11-12", "12:00:00", "2026-11-12", "14:00:00")
E5 = row("e5e5e5e5-0000-4000-8000-000000000005", "planning", "2026-11-11", "18:00:00", "2026-11-12", "09:30:00")
E6 = row("e6e6e6e6-0000-4000-8000-000000000006", "confirmed", "2026-11-12", "07:00:00", "2026-11-12", "09:00:00")


# --- TC-EVENTS-105 --------------------------------------------------------
def test_overlapping_planning_and_confirmed_events_are_returned_in_start_order(client, db):
    window_query(db).execute.return_value = SimpleNamespace(data=[E2, E4, E1, E6, E5])

    response = client.post("/events/overlapping", json=WINDOW)

    assert response.status_code == 200, response.text
    assert [event["id"] for event in response.json()] == [E5["id"], E1["id"], E2["id"]]
    assert set(response.json()[0]) == {"id", "name", "status", "start_date", "start_time", "end_date", "end_time"}
    select = db.schema.return_value.table.return_value.select
    select.return_value.in_.assert_called_once_with("status", ["planning", "confirmed"])
    select.return_value.in_.return_value.lte.assert_called_once_with("start_date", "2026-11-12")
    select.return_value.in_.return_value.lte.return_value.gte.assert_called_once_with("end_date", "2026-11-12")


# --- TC-EVENTS-106 --------------------------------------------------------
def test_only_planning_and_confirmed_events_are_asked_for(client, db):
    window_query(db).execute.return_value = SimpleNamespace(data=[])

    client.post("/events/overlapping", json=WINDOW)

    statuses = db.schema.return_value.table.return_value.select.return_value.in_.call_args.args[1]
    assert sorted(statuses) == ["confirmed", "planning"]
    for excluded in ("draft", "submitted", "returned", "rejected"):
        assert excluded not in statuses


# --- TC-EVENTS-107 --------------------------------------------------------
@pytest.mark.parametrize("changes", [
    {"end_time": "09:00"},
    {"end_date": "2026-11-11"},
    {"end_time": None},
])
def test_an_invalid_window_is_refused(client, db, changes):
    body = {key: value for key, value in {**WINDOW, **changes}.items() if value is not None}

    response = client.post("/events/overlapping", json=body)

    assert response.status_code == 422
    db.schema.assert_not_called()
