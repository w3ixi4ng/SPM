"""TC-EVENTS-175. Run after the S-51 block of events.sql on .env.test."""

import httpx
import pytest
from postgrest.exceptions import APIError

from .conftest import BASE_URL, requires_env

pytestmark = requires_env

OPENS = "2026-11-01T09:00:00"
CLOSES = "2026-11-15T18:00:00"
SUBMITTED = {
    "name": "spm-test S-51 registration",
    "purpose": "Prove the S-51 columns",
    "start_date": "2026-11-20",
    "start_time": "18:00",
    "end_date": "2026-11-20",
    "end_time": "21:00",
    "expected_attendance": 40,
    "registration_required": True,
    "registration_opens_at": OPENS,
    "registration_closes_at": CLOSES,
}


# --- TC-EVENTS-175 --------------------------------------------------------
def test_registration_columns_round_trip_and_are_constrained(admin, organiser_session):
    headers = {"Cookie": f"sb_access_token={organiser_session['access_token']}"}
    table = admin.schema("events").table("events")

    created = httpx.post(f"{BASE_URL}/events/drafts", json=SUBMITTED, headers=headers, timeout=20)
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    organiser_session["event_ids"].append(event_id)

    read = httpx.get(f"{BASE_URL}/events/{event_id}", headers=headers, timeout=20)
    assert read.status_code == 200, read.text
    assert read.json()["registration_required"] is True
    assert read.json()["registration_opens_at"] == OPENS
    assert read.json()["registration_closes_at"] == CLOSES

    with pytest.raises(APIError) as caught:
        table.update({"registration_closes_at": "2026-11-01T08:00:00"}).eq("id", event_id).execute()
    assert caught.value.code == "23514", caught.value

    submitted = httpx.post(
        f"{BASE_URL}/events/{event_id}/submit", json=SUBMITTED, headers=headers, timeout=20
    )
    assert submitted.status_code == 200, submitted.text
    table.update({
        "status": "confirmed",
        "decision": "approved",
        "decided_at": "2026-10-20T00:00:00Z",
        "safety_decision": "approved",
        "safety_officer_id": organiser_session["user_id"],
        "safety_decided_at": "2026-10-21T00:00:00Z",
    }).eq("id", event_id).execute()

    published = httpx.get(f"{BASE_URL}/internal/events/published/{event_id}", timeout=20)
    assert published.status_code == 200, published.text
    assert published.json()["registration_opens_at"] == OPENS
    assert "organiser_id" not in published.json()

    locked = httpx.patch(
        f"{BASE_URL}/events/{event_id}",
        json={"registration_required": False},
        headers=headers,
        timeout=20,
    )
    assert locked.status_code == 409, locked.text

    table.delete().eq("id", event_id).execute()
    organiser_session["event_ids"].remove(event_id)
    assert table.select("id").eq("id", event_id).execute().data == []
