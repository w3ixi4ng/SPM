"""TC-EVENTS-130 (S-62): a cancellation request is stored with the event
through Kong, and the event's status does not change."""

import uuid

import httpx

from .conftest import GATEWAY_BASE_URL, requires_env

pytestmark = requires_env

REASON = "Keynote speaker withdrew"


def test_a_cancellation_request_is_stored_with_the_event_through_kong(admin, organiser_session):
    event = admin.schema("events").table("events").insert({
        "organiser_id": organiser_session["user_id"],
        "status": "planning",
        "name": f"spm-test cancellation {uuid.uuid4().hex[:8]}",
        "purpose": "Connect alumni with graduating students",
        "start_date": "2026-11-12",
        "start_time": "09:00",
        "end_date": "2026-11-12",
        "end_time": "18:00",
        "expected_attendance": 120,
        "decision": "approved",
        "decided_at": "2026-10-01T00:00:00Z",
        "submitted_at": "2026-09-30T00:00:00Z",
    }).execute().data[0]
    organiser_session["event_ids"].append(event["id"])
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}

    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0, headers=headers) as api:
        # 1. The request is accepted.
        sent = api.post(f"/events/{event['id']}/cancellation-request", json={"reason": REASON})
        assert sent.status_code == 200, sent.text

        # 2. It comes back with the event, whose status is unchanged.
        read = api.get(f"/events/{event['id']}")
        assert read.status_code == 200, read.text
        body = read.json()
        assert body["status"] == "planning"
        assert body["cancellation_reason"] == REASON
        assert body["cancellation_requested_by"] == organiser_session["user_id"]
        assert body["cancellation_requested_at"]

        # 3. A second request is refused.
        again = api.post(f"/events/{event['id']}/cancellation-request", json={"reason": "Changed my mind"})
        assert again.status_code == 409, again.text

    row = admin.schema("events").table("events").select(
        "status,cancellation_reason,cancellation_requested_by,cancellation_requested_at"
    ).eq("id", event["id"]).execute().data[0]
    assert row["status"] == "planning"
    assert row["cancellation_reason"] == REASON
    assert row["cancellation_requested_by"] == organiser_session["user_id"]
    assert row["cancellation_requested_at"]
