"""TC-EVENTREGISTRATIONS-101..107. Run with the whole .env.test stack up."""

import uuid
from datetime import timedelta

import httpx

from .conftest import GATEWAY_BASE_URL, confirmed_event, requires_env, sgt_now

pytestmark = requires_env


# --- TC-EVENTREGISTRATIONS-101 --------------------------------------------
def test_public_view_blocked_attempt_and_a_real_registration(admin, attendee):
    organiser_id = str(uuid.uuid4())
    now = sgt_now()
    open_event = confirmed_event(
        admin, organiser_id, opens=now - timedelta(days=1), closes=now + timedelta(days=1)
    )
    later_event = confirmed_event(
        admin, organiser_id, opens=now + timedelta(days=7), closes=now + timedelta(days=8)
    )
    events = admin.schema("events").table("events")
    registrations = admin.schema("registrations").table("registrations")
    base = f"{GATEWAY_BASE_URL}/event-registrations/events"
    try:
        public = httpx.get(f"{base}/{open_event}", timeout=20)
        assert public.status_code == 200, public.text
        assert public.json()["registration_required"] is True
        assert public.json()["registration_opens_at"] is not None
        assert "organiser_id" not in public.json()

        early = httpx.post(f"{base}/{later_event}/registration", headers=attendee["headers"], timeout=20)
        assert early.status_code == 409, early.text
        assert early.json()["detail"].startswith("Registration hasn't opened yet. It's open from ")
        assert " to " in early.json()["detail"]

        taken = httpx.post(f"{base}/{open_event}/registration", headers=attendee["headers"], timeout=20)
        assert taken.status_code == 201, taken.text

        mine = httpx.get(f"{base}/{open_event}/registration", headers=attendee["headers"], timeout=20)
        assert mine.status_code == 200, mine.text
        assert mine.json()["registered"] is True
    finally:
        registrations.delete().in_("event_id", [open_event, later_event]).execute()
        events.delete().in_("id", [open_event, later_event]).execute()
    assert events.select("id").in_("id", [open_event, later_event]).execute().data == []
    assert registrations.select("id").in_("event_id", [open_event, later_event]).execute().data == []


# --- TC-EVENTREGISTRATIONS-102 --------------------------------------------
def test_a_registration_shows_for_the_attendee_and_for_the_events_organiser(admin, make_account):
    organiser = make_account("event_organiser", "spm-test S-48 organiser")
    other_organiser = make_account("event_organiser", "spm-test S-48 other organiser")
    attendee = make_account("attendee", "S-48 Test Attendee")
    now = sgt_now()
    event_id = confirmed_event(
        admin, organiser["id"], opens=now - timedelta(days=1), closes=now + timedelta(days=1)
    )
    events = admin.schema("events").table("events")
    registrations = admin.schema("registrations").table("registrations")
    base = f"{GATEWAY_BASE_URL}/event-registrations"
    try:
        taken = httpx.post(
            f"{base}/events/{event_id}/registration", headers=attendee["headers"], timeout=20
        )
        assert taken.status_code == 201, taken.text

        mine = httpx.get(f"{base}/me/registrations", headers=attendee["headers"], timeout=20)
        assert mine.status_code == 200, mine.text
        listed = [item for item in mine.json() if item["event_id"] == event_id]
        assert len(listed) == 1, mine.json()
        assert listed[0]["name"].startswith("spm-test S-51")
        assert listed[0]["registered_at"]

        seen = httpx.get(
            f"{base}/events/{event_id}/attendees", headers=organiser["headers"], timeout=20
        )
        assert seen.status_code == 200, seen.text
        assert seen.json()["count"] == 1
        (row,) = seen.json()["attendees"]
        assert row["attendee_id"] == attendee["id"]
        assert row["name"] == "S-48 Test Attendee"
        assert row["email"] == attendee["email"]

        hidden = httpx.get(
            f"{base}/events/{event_id}/attendees", headers=other_organiser["headers"], timeout=20
        )
        assert hidden.status_code == 404, hidden.text
    finally:
        registrations.delete().eq("event_id", event_id).execute()
        events.delete().eq("id", event_id).execute()
    assert events.select("id").eq("id", event_id).execute().data == []
    assert registrations.select("id").eq("event_id", event_id).execute().data == []


# --- TC-EVENTREGISTRATIONS-103 --------------------------------------------
def test_a_full_event_turns_the_next_attendee_to_the_waiting_list(admin, make_account):
    organiser = make_account("event_organiser", "spm-test S-50 organiser")
    first = make_account("attendee", "S-50 First Attendee")
    second = make_account("attendee", "S-50 Second Attendee")
    now = sgt_now()
    event_id = confirmed_event(
        admin, organiser["id"], opens=now - timedelta(days=1), closes=now + timedelta(days=1),
        expected_attendance=1,
    )
    events = admin.schema("events").table("events")
    registrations = admin.schema("registrations").table("registrations")
    waiting = admin.schema("registrations").table("waiting_list")
    base = f"{GATEWAY_BASE_URL}/event-registrations"
    register = f"{base}/events/{event_id}/registration"
    try:
        taken = httpx.post(register, headers=first["headers"], timeout=20)
        assert taken.status_code == 201, taken.text

        public = httpx.get(f"{base}/events/{event_id}", timeout=20)
        assert public.status_code == 200, public.text
        assert public.json()["is_full"] is True
        assert "expected_attendance" not in public.json()

        refused = httpx.post(register, headers=second["headers"], timeout=20)
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"] == "This event is full. You can join the waiting list."

        joined = httpx.post(
            f"{base}/events/{event_id}/waiting-list", headers=second["headers"], timeout=20
        )
        assert joined.status_code == 201, joined.text

        status = httpx.get(register, headers=second["headers"], timeout=20)
        assert status.json()["waitlisted"] is True, status.text

        seen = httpx.get(
            f"{base}/events/{event_id}/attendees", headers=organiser["headers"], timeout=20
        )
        assert seen.status_code == 200, seen.text
        assert seen.json()["count"] == 1
        assert [row["attendee_id"] for row in seen.json()["attendees"]] == [first["id"]]
        assert [row["attendee_id"] for row in seen.json()["waiting_list"]] == [second["id"]]

        closed = httpx.put(
            f"{GATEWAY_BASE_URL}/events/{event_id}/registration-closure",
            headers=organiser["headers"],
            timeout=20,
        )
        assert closed.status_code == 200, closed.text
        after_close = httpx.post(register, headers=second["headers"], timeout=20)
        assert after_close.status_code == 409, after_close.text
        assert after_close.json()["detail"] == (
            "The organiser has closed registration for this event."
        )
    finally:
        registrations.delete().eq("event_id", event_id).execute()
        waiting.delete().eq("event_id", event_id).execute()
        events.delete().eq("id", event_id).execute()
    assert events.select("id").eq("id", event_id).execute().data == []
    assert registrations.select("id").eq("event_id", event_id).execute().data == []
    assert waiting.select("id").eq("event_id", event_id).execute().data == []


# --- TC-EVENTREGISTRATIONS-104 --------------------------------------------
def test_waitlisted_attendees_see_their_place_in_line(admin, make_account):
    organiser = make_account("event_organiser", "spm-test S-52 organiser")
    first = make_account("attendee", "S-52 First Attendee")
    second = make_account("attendee", "S-52 Second Attendee")
    third = make_account("attendee", "S-52 Third Attendee")
    now = sgt_now()
    event_id = confirmed_event(
        admin, organiser["id"], opens=now - timedelta(days=1), closes=now + timedelta(days=1),
        expected_attendance=1,
    )
    events = admin.schema("events").table("events")
    registrations = admin.schema("registrations").table("registrations")
    waiting = admin.schema("registrations").table("waiting_list")
    base = f"{GATEWAY_BASE_URL}/event-registrations"
    register = f"{base}/events/{event_id}/registration"
    wait = f"{base}/events/{event_id}/waiting-list"
    try:
        taken = httpx.post(register, headers=first["headers"], timeout=20)
        assert taken.status_code == 201, taken.text

        for account, place in [(second, 1), (third, 2)]:
            joined = httpx.post(wait, headers=account["headers"], timeout=20)
            assert joined.status_code == 201, joined.text
            assert joined.json()["position"] == place

        for account, place in [(second, 1), (third, 2)]:
            status = httpx.get(register, headers=account["headers"], timeout=20)
            assert status.status_code == 200, status.text
            assert status.json()["waitlisted"] is True
            assert status.json()["position"] == place

        waiting_rows = httpx.get(f"{base}/me/registrations", headers=third["headers"], timeout=20)
        assert waiting_rows.status_code == 200, waiting_rows.text
        assert [(row["event_id"], row["status"], row["position"]) for row in waiting_rows.json()] == [
            (event_id, "waitlisted", 2)
        ]

        confirmed_rows = httpx.get(f"{base}/me/registrations", headers=first["headers"], timeout=20)
        assert confirmed_rows.status_code == 200, confirmed_rows.text
        assert [(row["event_id"], row["status"], row["position"]) for row in confirmed_rows.json()] == [
            (event_id, "confirmed", None)
        ]
    finally:
        registrations.delete().eq("event_id", event_id).execute()
        waiting.delete().eq("event_id", event_id).execute()
        events.delete().eq("id", event_id).execute()
    assert events.select("id").eq("id", event_id).execute().data == []
    assert registrations.select("id").eq("event_id", event_id).execute().data == []
    assert waiting.select("id").eq("event_id", event_id).execute().data == []


# --- TC-EVENTREGISTRATIONS-105 --------------------------------------------
def test_registering_puts_one_confirmation_in_the_attendees_notifications(admin, make_account):
    organiser = make_account("event_organiser", "spm-test S-49 organiser")
    attendee = make_account("attendee", "S-49 Test Attendee")
    now = sgt_now()
    event_id = confirmed_event(
        admin, organiser["id"], opens=now - timedelta(days=1), closes=now + timedelta(days=1)
    )
    events = admin.schema("events").table("events")
    registrations = admin.schema("registrations").table("registrations")
    notifications = admin.schema("notifications").table("notifications")
    name = events.select("name").eq("id", event_id).execute().data[0]["name"]
    register = f"{GATEWAY_BASE_URL}/event-registrations/events/{event_id}/registration"
    try:
        taken = httpx.post(register, headers=attendee["headers"], timeout=20)
        assert taken.status_code == 201, taken.text

        again = httpx.post(register, headers=attendee["headers"], timeout=20)
        assert again.status_code == 409, again.text
        assert again.json()["detail"] == "You're already registered for this event."

        inbox = httpx.get(f"{GATEWAY_BASE_URL}/notifications", headers=attendee["headers"], timeout=20)
        assert inbox.status_code == 200, inbox.text
        confirmations = [
            row for row in inbox.json() if row["kind"] == "registration_confirmation"
        ]
        assert len(confirmations) == 1, (
            f"{inbox.json()} -- check notifications.sql's S-49 kind is applied to the test project"
        )
        (row,) = confirmations
        assert row["event_id"] == event_id
        assert row["message"].startswith(f"Registration confirmed: {name}, ")
        assert "venue to be confirmed" in row["message"]
        assert "Name: S-49 Test Attendee." in row["message"]
        assert f"Email: {attendee['email']}." in row["message"]
    finally:
        notifications.delete().eq("event_id", event_id).execute()
        registrations.delete().eq("event_id", event_id).execute()
        events.delete().eq("id", event_id).execute()
    assert notifications.select("id").eq("event_id", event_id).execute().data == []
    assert registrations.select("id").eq("event_id", event_id).execute().data == []
    assert events.select("id").eq("id", event_id).execute().data == []


# --- TC-EVENTREGISTRATIONS-106 --------------------------------------------
def test_withdrawing_frees_the_place_for_the_next_in_line(admin, make_account):
    organiser = make_account("event_organiser", "spm-test S-53 organiser")
    first = make_account("attendee", "S-53 Test Attendee A")
    second = make_account("attendee", "S-53 Test Attendee B")
    third = make_account("attendee", "S-53 Test Attendee C")
    now = sgt_now()
    event_id = confirmed_event(
        admin, organiser["id"], opens=now - timedelta(days=1), closes=now + timedelta(days=1),
        expected_attendance=1,
    )
    events = admin.schema("events").table("events")
    registrations = admin.schema("registrations").table("registrations")
    waiting = admin.schema("registrations").table("waiting_list")
    notifications = admin.schema("notifications").table("notifications")
    name = events.select("name").eq("id", event_id).execute().data[0]["name"]
    base = f"{GATEWAY_BASE_URL}/event-registrations"
    register = f"{base}/events/{event_id}/registration"
    wait = f"{base}/events/{event_id}/waiting-list"

    def promotions(account):
        inbox = httpx.get(f"{GATEWAY_BASE_URL}/notifications", headers=account["headers"], timeout=20)
        assert inbox.status_code == 200, inbox.text
        return [
            row for row in inbox.json()
            if row["kind"] == "waiting_list_promotion" and row["event_id"] == event_id
        ]

    try:
        taken = httpx.post(register, headers=first["headers"], timeout=20)
        assert taken.status_code == 201, taken.text
        for account, place in [(second, 1), (third, 2)]:
            joined = httpx.post(wait, headers=account["headers"], timeout=20)
            assert joined.status_code == 201, joined.text
            assert joined.json()["position"] == place

        withdrawn = httpx.delete(register, headers=first["headers"], timeout=20)
        assert withdrawn.status_code == 200, (
            f"{withdrawn.text} -- check the S-53 block of registrations.sql is applied"
        )
        assert withdrawn.json()["registered"] is False

        status = httpx.get(register, headers=first["headers"], timeout=20)
        assert status.json()["registered"] is False
        assert status.json()["waitlisted"] is False
        mine = httpx.get(f"{base}/me/registrations", headers=first["headers"], timeout=20)
        assert mine.status_code == 200, mine.text
        assert [row for row in mine.json() if row["event_id"] == event_id] == []

        promoted = httpx.get(register, headers=second["headers"], timeout=20)
        assert promoted.json()["registered"] is True
        behind = httpx.get(register, headers=third["headers"], timeout=20)
        assert behind.json()["waitlisted"] is True
        assert behind.json()["position"] == 1

        notices = promotions(second)
        assert len(notices) == 1, (
            f"{notices} -- check notifications.sql's S-53 kind is applied to the test project"
        )
        (row,) = notices
        assert row["message"].startswith(f"A place opened up: you're now registered for {name}, ")
        assert "venue to be confirmed" in row["message"]
        assert "Name: S-53 Test Attendee B." in row["message"]
        assert f"Email: {second['email']}." in row["message"]
        assert promotions(first) == []

        again = httpx.delete(register, headers=first["headers"], timeout=20)
        assert again.status_code == 404, again.text
        assert again.json()["detail"] == "You're not registered for this event."
    finally:
        notifications.delete().eq("event_id", event_id).execute()
        registrations.delete().eq("event_id", event_id).execute()
        waiting.delete().eq("event_id", event_id).execute()
        events.delete().eq("id", event_id).execute()
    assert notifications.select("id").eq("event_id", event_id).execute().data == []
    assert registrations.select("id").eq("event_id", event_id).execute().data == []
    assert waiting.select("id").eq("event_id", event_id).execute().data == []
    assert events.select("id").eq("id", event_id).execute().data == []


# --- TC-EVENTREGISTRATIONS-107 --------------------------------------------
def test_the_attendees_list_shows_the_primary_venue_and_hides_details_while_rechecked(
    admin, make_account
):
    organiser = make_account("event_organiser", "spm-test S-56 organiser")
    attendee = make_account("attendee", "S-56 Test Attendee")
    now = sgt_now()
    event_id = confirmed_event(
        admin, organiser["id"], opens=now - timedelta(days=1), closes=now + timedelta(days=1)
    )
    events = admin.schema("events").table("events")
    venues = admin.schema("venues").table("venues")
    bookings = admin.schema("bookings").table("bookings")
    registrations = admin.schema("registrations").table("registrations")
    notifications = admin.schema("notifications").table("notifications")
    event = events.select("name,start_date").eq("id", event_id).execute().data[0]
    tag = uuid.uuid4().hex[:8]
    venue_ids = []
    try:
        names = {}
        for label in ("V1", "V2"):
            names[label] = f"spm-test S56 {label} {tag}"
            venue_ids.append(venues.insert({
                "name": names[label], "location": "10 Anson Road", "capacity": 300,
                "room_layouts": ["theatre"], "facilities": [],
                "operating_hours": [{"day": "fri", "open": "08:00:00", "close": "22:00:00"}], "created_by": organiser["id"],
            }).execute().data[0]["id"])
        # V2 is booked last but inserted first, so the order of rows is not
        # what decides the primary venue.
        for venue_id, label, submitted in (
            (venue_ids[1], "V2", "2026-10-03T00:00:00Z"),
            (venue_ids[0], "V1", "2026-10-01T00:00:00Z"),
        ):
            bookings.insert({
                "event_id": event_id, "venue_id": venue_id, "coordinator_id": organiser["id"],
                "coordinator_name": "spm-test Coordinator", "coordinator_email": organiser["email"],
                "booking_date": event["start_date"], "start_time": "18:00", "end_time": "21:00",
                "event_name": event["name"], "event_purpose": "Prove S-56",
                "expected_attendance": 40, "venue_name": names[label], "status": "confirmed",
                "decided_by": organiser["id"], "decided_at": "2026-10-04T00:00:00Z",
                "submitted_at": submitted,
            }).execute()

        register = f"{GATEWAY_BASE_URL}/event-registrations/events/{event_id}/registration"
        taken = httpx.post(register, headers=attendee["headers"], timeout=20)
        assert taken.status_code == 201, taken.text

        def mine():
            listed = httpx.get(
                f"{GATEWAY_BASE_URL}/event-registrations/me/registrations",
                headers=attendee["headers"], timeout=20,
            )
            assert listed.status_code == 200, listed.text
            (row,) = [row for row in listed.json() if row["event_id"] == event_id]
            return row

        row = mine()
        assert row["details_confirmed"] is True
        assert row["start_date"] == event["start_date"]
        assert (row["start_time"], row["end_time"]) == ("18:00:00", "21:00:00")
        assert row["venue"] == names["V1"]

        # A significant S-18 change sends it back for re-checking.
        events.update({
            "status": "planning", "safety_recheck_required": True, "safety_decision": None,
            "safety_decision_reason": None, "safety_officer_id": None, "safety_decided_at": None,
        }).eq("id", event_id).execute()
        row = mine()
        assert row["details_confirmed"] is False
        for field in ("start_date", "start_time", "end_date", "end_time", "venue"):
            assert row[field] is None
    finally:
        notifications.delete().eq("event_id", event_id).execute()
        registrations.delete().eq("event_id", event_id).execute()
        bookings.delete().eq("event_id", event_id).execute()
        events.delete().eq("id", event_id).execute()
        for venue_id in venue_ids:
            venues.delete().eq("id", venue_id).execute()
    assert registrations.select("id").eq("event_id", event_id).execute().data == []
    assert bookings.select("id").eq("event_id", event_id).execute().data == []
    assert events.select("id").eq("id", event_id).execute().data == []
