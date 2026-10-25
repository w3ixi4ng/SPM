"""TC-REGISTRATIONS-101..102. Run after backend/sql/registrations.sql on .env.test."""

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


# --- TC-REGISTRATIONS-102 -------------------------------------------------
def test_a_place_reads_back_by_event_and_by_attendee(admin):
    first_event, second_event = str(uuid.uuid4()), str(uuid.uuid4())
    attendee_a, attendee_b = str(uuid.uuid4()), str(uuid.uuid4())
    table = admin.schema("registrations").table("registrations")
    try:
        created = []
        for event_id, attendee_id in (
            (first_event, attendee_a), (first_event, attendee_b), (second_event, attendee_a)
        ):
            response = httpx.post(
                f"{BASE_URL}/registrations",
                json={"event_id": event_id, "attendee_id": attendee_id},
                timeout=20,
            )
            assert response.status_code == 201, response.text
            created.append(response.json()["id"])

        by_event = httpx.get(f"{BASE_URL}/registrations/events/{first_event}", timeout=20)
        assert by_event.status_code == 200, by_event.text
        assert [row["id"] for row in by_event.json()] == created[:2]

        by_attendee = httpx.get(f"{BASE_URL}/registrations/attendees/{attendee_a}", timeout=20)
        assert by_attendee.status_code == 200, by_attendee.text
        assert [row["id"] for row in by_attendee.json()] == [created[0], created[2]]
    finally:
        table.delete().in_("event_id", [first_event, second_event]).execute()
    assert table.select("id").in_("event_id", [first_event, second_event]).execute().data == []
