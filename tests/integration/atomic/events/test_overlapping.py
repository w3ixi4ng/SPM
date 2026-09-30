"""TC-EVENTS-108 (S-44): POST /events/overlapping against the real table."""

import httpx

from .conftest import BASE_URL, requires_env

pytestmark = requires_env

# Far from every other test's dates, so only these rows can match.
DAY = "2031-03-04"


def seed(admin, session, status, start, end):
    decided = {"decision": "rejected", "decision_reason": "spm-test"} if status == "rejected" else {"decision": "approved"}
    row = admin.schema("events").table("events").insert({
        "organiser_id": session["user_id"],
        "assigned_coordinator_id": session["user_id"],
        "status": status,
        "name": f"spm-test S44 {status} {start}",
        "purpose": "Overlapping-events check",
        "start_date": DAY, "start_time": start, "end_date": DAY, "end_time": end,
        "expected_attendance": 10,
        "submitted_at": "2026-09-30T00:00:00Z",
        "decided_at": "2026-10-01T00:00:00Z",
        **decided,
    }).execute().data[0]
    session["event_ids"].append(row["id"])
    return row["id"]


def test_the_overlapping_events_query_works_against_the_real_table(admin, organiser_session):
    planning = seed(admin, organiser_session, "planning", "10:00", "11:00")
    confirmed = seed(admin, organiser_session, "confirmed", "11:30", "13:00")
    rejected = seed(admin, organiser_session, "rejected", "10:00", "11:00")
    back_to_back = seed(admin, organiser_session, "planning", "12:00", "13:00")

    response = httpx.post(f"{BASE_URL}/events/overlapping", json={
        "start_date": DAY, "start_time": "09:00", "end_date": DAY, "end_time": "12:00",
    }, timeout=15.0)

    assert response.status_code == 200, response.text
    ids = [event["id"] for event in response.json()]
    ours = [event_id for event_id in ids if event_id in organiser_session["event_ids"]]
    assert ours == [planning, confirmed]
    assert rejected not in ids and back_to_back not in ids
