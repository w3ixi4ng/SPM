"""TC-REGISTRATIONS-101. Run after backend/sql/registrations.sql on .env.test."""

import uuid

import httpx

from .conftest import BASE_URL, requires_env

pytestmark = requires_env


# --- TC-REGISTRATIONS-101 -------------------------------------------------
def test_register_refuse_a_duplicate_and_read_it_back(admin):
    event_id = str(uuid.uuid4())
    attendee_id = str(uuid.uuid4())
    table = admin.schema("registrations").table("registrations")
    body = {"event_id": event_id, "attendee_id": attendee_id}
    try:
        created = httpx.post(f"{BASE_URL}/registrations", json=body, timeout=20)
        assert created.status_code == 201, created.text

        again = httpx.post(f"{BASE_URL}/registrations", json=body, timeout=20)
        assert again.status_code == 409, again.text
        assert again.json()["detail"] == "You're already registered for this event."

        read = httpx.get(
            f"{BASE_URL}/registrations/events/{event_id}/attendees/{attendee_id}", timeout=20
        )
        assert read.status_code == 200, read.text
        assert read.json()["id"] == created.json()["id"]
    finally:
        table.delete().eq("event_id", event_id).execute()
    assert table.select("id").eq("event_id", event_id).execute().data == []
