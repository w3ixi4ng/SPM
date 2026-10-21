"""Integration tests for the venue_bookings composite -- see TEST_CASES.md."""

import httpx

from .conftest import BASE_URL, GATEWAY_BASE_URL, cookie_for, requires_env

pytestmark = requires_env


# S-75 adds a live clash warning to listed rows (and, on held/confirmed rows,
# the venue's setup and turnaround). These compare the booking itself.
# Read-time fields the composite adds to each row: S-75's clash warning and the
# venue's times, and S-77's alternative-arrangements flag.
S75_FIELDS = {
    "clashes", "setup_minutes", "turnaround_minutes",
    "requires_alternative_arrangements", "unavailable_periods",
}


def booking_only(row):
    return {key: value for key, value in row.items() if key not in S75_FIELDS}


# --- TC-VENUEBOOKINGS-101 --------------------------------------------------
def test_a_coordinators_request_reaches_venue_staff_and_stays_visible_to_the_coordinator(admin, auth_client, world):
    as_coordinator = cookie_for(auth_client, world["coordinator"])

    created = httpx.post(
        f"{GATEWAY_BASE_URL}/venue-bookings",
        headers=as_coordinator,
        json={
            "event_id": world["event_id"],
            "venue_id": world["venue_id"],
            "booking_date": "2026-11-12",
            "start_time": "09:00",
            "end_time": "12:00",
        },
        timeout=15.0,
    )
    assert created.status_code == 201, created.text
    booking = created.json()
    assert booking["status"] == "pending"

    rows = admin.schema("bookings").table("bookings").select("*").eq("id", booking["id"]).execute().data
    assert len(rows) == 1, "no row in bookings.bookings -- check the schema is exposed and granted"
    event = admin.schema("events").table("events").select("*").eq("id", world["event_id"]).execute().data[0]
    venue = admin.schema("venues").table("venues").select("*").eq("id", world["venue_id"]).execute().data[0]
    assert rows[0]["event_name"] == event["name"]
    assert rows[0]["expected_attendance"] == 120
    assert rows[0]["venue_name"] == venue["name"]
    assert rows[0]["coordinator_email"] == world["coordinator"]["email"]
    assert rows[0]["room_layout"] == "theatre"
    assert rows[0]["required_facilities"] == ["projector"]
    assert rows[0]["required_accessibility"] == ["wheelchair_access"]

    assert event["status"] == "planning"

    sent = httpx.get(
        f"{GATEWAY_BASE_URL}/venue-bookings",
        params={"event_id": world["event_id"]},
        headers=as_coordinator,
        timeout=15.0,
    )
    assert sent.status_code == 200, sent.text
    assert [(row["id"], row["status"]) for row in sent.json()] == [(booking["id"], "pending")]

    as_staff = cookie_for(auth_client, world["staff"])
    pending = httpx.get(f"{GATEWAY_BASE_URL}/venue-bookings/pending", headers=as_staff, timeout=15.0)
    assert pending.status_code == 200, pending.text
    assert booking["id"] in [row["id"] for row in pending.json()]


# --- TC-VENUEBOOKINGS-102 --------------------------------------------------
def test_an_unsuitable_venue_is_refused_against_real_venue_data(admin, auth_client, world):
    admin.schema("events").table("events").update({"expected_attendance": 200}).eq(
        "id", world["event_id"]
    ).execute()
    as_coordinator = cookie_for(auth_client, world["coordinator"])

    refused = httpx.post(
        f"{BASE_URL}/venue-bookings",
        headers=as_coordinator,
        json={
            "event_id": world["event_id"],
            "venue_id": world["venue_id"],
            "booking_date": "2026-11-12",
            "start_time": "07:00",
            "end_time": "10:00",
        },
        timeout=15.0,
    )

    assert refused.status_code == 422, refused.text
    assert {"booking_date", "operating_hours", "expected_attendance"} <= set(refused.json()["errors"])
    saved = admin.schema("bookings").table("bookings").select("id").eq("event_id", world["event_id"]).execute()
    assert saved.data == []


# TC-VENUEBOOKINGS-103
def test_venue_edit_preserves_history_and_new_requests_use_saved_values(admin, auth_client, world):
    coordinator = cookie_for(auth_client, world["coordinator"])
    staff = cookie_for(auth_client, world["staff"])
    payload = {"event_id": world["event_id"], "venue_id": world["venue_id"],
               "booking_date": "2026-11-12", "start_time": "09:00", "end_time": "12:00"}
    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as api:
        created = api.post("/venue-bookings", headers=coordinator, json=payload)
        assert created.status_code == 201, created.text
        booking = created.json()
        before = admin.schema("bookings").table("bookings").select("*").eq("id", booking["id"]).execute().data
        updated = api.patch(f"/venues/{world['venue_id']}", headers=staff,
                            json={"capacity": 100, "facilities": [], "accessibility": []})
        assert updated.status_code == 200, updated.text
        refused = api.post("/venue-bookings", headers=coordinator, json=payload)
        assert refused.status_code == 422, refused.text
        assert {"expected_attendance", "required_facilities", "required_accessibility"} <= set(refused.json()["errors"])
        after = admin.schema("bookings").table("bookings").select("*").eq("event_id", world["event_id"]).execute().data
        assert after == before
        pending = api.get("/venue-bookings/pending", headers=staff)
        assert pending.status_code == 200, pending.text
        assert booking in [booking_only(row) for row in pending.json()]
        sent = api.get("/venue-bookings", headers=coordinator, params={"event_id": world["event_id"]})
        assert sent.status_code == 200, sent.text
        assert [booking_only(row) for row in sent.json()] == [booking]


# TC-VENUEBOOKINGS-104
def test_new_request_uses_updated_venue_values(admin, auth_client, world):
    staff = cookie_for(auth_client, world["staff"])
    coordinator = cookie_for(auth_client, world["coordinator"])
    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=15.0) as api:
        updated = api.patch(f"/venues/{world['venue_id']}", headers=staff,
                            json={"capacity": 100, "facilities": [], "accessibility": []})
        assert updated.status_code == 200, updated.text
        refused = api.post("/venue-bookings", headers=coordinator, json={
            "event_id": world["event_id"], "venue_id": world["venue_id"],
            "booking_date": "2026-11-12", "start_time": "09:00", "end_time": "12:00",
        })
        assert refused.status_code == 422, refused.text
        assert {"expected_attendance", "required_facilities", "required_accessibility"} <= set(refused.json()["errors"])
        assert admin.schema("bookings").table("bookings").select("id").eq("event_id", world["event_id"]).execute().data == []
