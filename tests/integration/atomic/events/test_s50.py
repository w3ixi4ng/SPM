"""TC-EVENTS-184. Run after the S-50 block of events.sql on .env.test."""

from datetime import datetime, timedelta, timezone

import httpx

from .conftest import BASE_URL, requires_env

pytestmark = requires_env

SGT = timezone(timedelta(hours=8))


# --- TC-EVENTS-184 --------------------------------------------------------
def test_closing_and_reopening_registration_is_saved(admin, organiser_session):
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    table = admin.schema("events").table("events")
    now = datetime.now(SGT).replace(tzinfo=None, second=0, microsecond=0)
    start = now + timedelta(days=10)
    event_id = table.insert({
        "organiser_id": organiser_session["user_id"],
        "status": "confirmed",
        "name": "spm-test S-50 close registration",
        "purpose": "Prove the S-50 column",
        "start_date": start.date().isoformat(),
        "start_time": "18:00",
        "end_date": start.date().isoformat(),
        "end_time": "21:00",
        "expected_attendance": 40,
        "submitted_at": "2026-10-01T00:00:00Z",
        "decision": "approved",
        "decided_at": "2026-10-02T00:00:00Z",
        "safety_decision": "approved",
        "safety_officer_id": organiser_session["user_id"],
        "safety_decided_at": "2026-10-03T00:00:00Z",
        "registration_required": True,
        "registration_opens_at": (now - timedelta(days=1)).isoformat(),
        "registration_closes_at": (now + timedelta(days=1)).isoformat(),
    }).execute().data[0]["id"]
    organiser_session["event_ids"].append(event_id)
    closure = f"{BASE_URL}/events/{event_id}/registration-closure"
    published = f"{BASE_URL}/internal/events/published/{event_id}"

    closed = httpx.put(closure, headers=headers, timeout=20)
    assert closed.status_code == 200, closed.text
    read = httpx.get(published, timeout=20)
    assert read.status_code == 200, read.text
    assert read.json()["registration_closed_at"] is not None
    assert read.json()["expected_attendance"] == 40

    reopened = httpx.delete(closure, headers=headers, timeout=20)
    assert reopened.status_code == 200, reopened.text
    assert httpx.get(published, timeout=20).json()["registration_closed_at"] is None

    table.delete().eq("id", event_id).execute()
    organiser_session["event_ids"].remove(event_id)
    assert table.select("id").eq("id", event_id).execute().data == []
