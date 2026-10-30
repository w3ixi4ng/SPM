"""TC-REGISTRATIONS-101..106. Run after backend/sql/registrations.sql on .env.test."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

from .conftest import BASE_URL, requires_env

pytestmark = requires_env


# --- TC-REGISTRATIONS-101 -------------------------------------------------
def test_register_refuse_a_duplicate_and_read_it_back(admin):
    event_id = str(uuid.uuid4())
    attendee_id = str(uuid.uuid4())
    table = admin.schema("registrations").table("registrations")
    body = {"event_id": event_id, "attendee_id": attendee_id, "capacity": 50}
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
                json={"event_id": event_id, "attendee_id": attendee_id, "capacity": 50},
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


def _register(event_id, attendee_id, capacity):
    return httpx.post(
        f"{BASE_URL}/registrations",
        json={"event_id": event_id, "attendee_id": attendee_id, "capacity": capacity},
        timeout=20,
    )


# --- TC-REGISTRATIONS-103 -------------------------------------------------
def test_the_cap_holds_even_under_simultaneous_registrations(admin):
    in_turn, at_once = str(uuid.uuid4()), str(uuid.uuid4())
    table = admin.schema("registrations").table("registrations")
    try:
        statuses = [_register(in_turn, str(uuid.uuid4()), 2) for _ in range(3)]
        assert [r.status_code for r in statuses] == [201, 201, 409], [r.text for r in statuses]
        assert statuses[2].json()["detail"] == "This event is full."

        with ThreadPoolExecutor(max_workers=6) as pool:
            racing = list(pool.map(lambda _: _register(at_once, str(uuid.uuid4()), 3), range(6)))
        codes = sorted(r.status_code for r in racing)
        assert codes == [201, 201, 201, 409, 409, 409], [r.text for r in racing]

        assert len(table.select("id").eq("event_id", in_turn).execute().data) == 2
        assert len(table.select("id").eq("event_id", at_once).execute().data) == 3
    finally:
        table.delete().in_("event_id", [in_turn, at_once]).execute()


# --- TC-REGISTRATIONS-104 -------------------------------------------------
def test_a_waiting_list_entry_is_saved_and_read_back(admin):
    event_id, attendee_id = str(uuid.uuid4()), str(uuid.uuid4())
    table = admin.schema("registrations").table("waiting_list")
    body = {"event_id": event_id, "attendee_id": attendee_id}
    try:
        joined = httpx.post(f"{BASE_URL}/registrations/waiting-list", json=body, timeout=20)
        assert joined.status_code == 201, joined.text
        again = httpx.post(f"{BASE_URL}/registrations/waiting-list", json=body, timeout=20)
        assert again.status_code == 409, again.text

        listed = httpx.get(f"{BASE_URL}/registrations/waiting-list/events/{event_id}", timeout=20)
        assert listed.status_code == 200, listed.text
        assert [row["attendee_id"] for row in listed.json()] == [attendee_id]

        one = httpx.get(
            f"{BASE_URL}/registrations/waiting-list/events/{event_id}/attendees/{attendee_id}",
            timeout=20,
        )
        assert one.status_code == 200, one.text
    finally:
        table.delete().eq("event_id", event_id).execute()
    assert table.select("id").eq("event_id", event_id).execute().data == []


# --- TC-REGISTRATIONS-105 -------------------------------------------------
def test_waiting_list_order_and_an_attendees_entries(admin):
    event_e, event_f = str(uuid.uuid4()), str(uuid.uuid4())
    attendee_b, attendee_c = str(uuid.uuid4()), str(uuid.uuid4())
    table = admin.schema("registrations").table("waiting_list")
    try:
        for event_id, attendee_id in [(event_e, attendee_b), (event_e, attendee_c), (event_f, attendee_b)]:
            joined = httpx.post(
                f"{BASE_URL}/registrations/waiting-list",
                json={"event_id": event_id, "attendee_id": attendee_id},
                timeout=20,
            )
            assert joined.status_code == 201, joined.text

        listed = httpx.get(f"{BASE_URL}/registrations/waiting-list/events/{event_e}", timeout=20)
        assert listed.status_code == 200, listed.text
        assert [row["attendee_id"] for row in listed.json()] == [attendee_b, attendee_c]

        mine = httpx.get(f"{BASE_URL}/registrations/waiting-list/attendees/{attendee_b}", timeout=20)
        assert mine.status_code == 200, mine.text
        assert [row["event_id"] for row in mine.json()] == [event_e, event_f]
    finally:
        table.delete().in_("event_id", [event_e, event_f]).execute()
    assert table.select("id").in_("event_id", [event_e, event_f]).execute().data == []


# --- TC-REGISTRATIONS-107 -------------------------------------------------
# S-55 retired TC-REGISTRATIONS-106: a freed place is now offered, not given.
def test_a_freed_place_is_held_for_the_first_in_line_until_they_answer(admin):
    event_id = str(uuid.uuid4())
    attendee_a, attendee_b, attendee_c, attendee_d = (str(uuid.uuid4()) for _ in range(4))
    places = admin.schema("registrations").table("registrations")
    waiting = admin.schema("registrations").table("waiting_list")

    def post(path, attendee_id, **extra):
        return httpx.post(
            f"{BASE_URL}/registrations{path}",
            json={"event_id": event_id, "attendee_id": attendee_id, **extra},
            timeout=20,
        )

    def listed(path):
        found = httpx.get(f"{BASE_URL}/registrations/{path}/{event_id}", timeout=20)
        assert found.status_code == 200, found.text
        return found.json()

    try:
        assert post("", attendee_a, capacity=1).status_code == 201
        for attendee_id in (attendee_b, attendee_c):
            joined = post("/waiting-list", attendee_id)
            assert joined.status_code == 201, joined.text

        freed = post("/withdrawals", attendee_a, capacity=1)
        assert freed.status_code == 200, (
            f"{freed.text} -- check the S-55 block of registrations.sql is applied"
        )
        assert freed.json()["withdrawn"]["attendee_id"] == attendee_a
        assert freed.json()["offered"]["attendee_id"] == attendee_b
        assert freed.json()["offered"]["offered_at"]

        # B is invited, not registered, and holds the place.
        assert listed("events") == []
        line = listed("waiting-list/events")
        assert [row["attendee_id"] for row in line] == [attendee_b, attendee_c]
        assert line[0]["offered_at"] and line[1]["offered_at"] is None

        newcomer = post("", attendee_d, capacity=1)
        assert newcomer.status_code == 409, newcomer.text
        assert newcomer.json()["detail"] == "This event is full."

        jumped = post("/offers/acceptances", attendee_c)
        assert jumped.status_code == 404, jumped.text
        assert jumped.json()["detail"] == "You don't have a place on offer for this event."

        declined = post("/offers/declines", attendee_b, capacity=1)
        assert declined.status_code == 200, declined.text
        assert declined.json()["declined"]["attendee_id"] == attendee_b
        assert declined.json()["offered"]["attendee_id"] == attendee_c

        accepted = post("/offers/acceptances", attendee_c)
        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["attendee_id"] == attendee_c

        assert [row["attendee_id"] for row in listed("events")] == [attendee_c]
        assert listed("waiting-list/events") == []
    finally:
        places.delete().eq("event_id", event_id).execute()
        waiting.delete().eq("event_id", event_id).execute()
    assert places.select("id").eq("event_id", event_id).execute().data == []
    assert waiting.select("id").eq("event_id", event_id).execute().data == []
