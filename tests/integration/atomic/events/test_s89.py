"""TC-EVENTS-450..452 (S-89). Run after the S-89 block of events.sql on .env.test.

The recorded cancellation persists, satisfies every event constraint from a
never-safety-checked and a safety-approved event, writes one history entry,
resumes unchanged, completes once, and loses to a real concurrent edit.
"""

import os
import uuid

import httpx
import pytest

from .conftest import BASE_URL, requires_env

pytestmark = requires_env

DAY = "2026-12-03"
BOOKING = str(uuid.uuid4())


@pytest.fixture
def coordinator(admin, auth_client):
    email = f"spm-test-s89-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery-staple"
    user = admin.auth.admin.create_user({
        "email": email, "password": password, "email_confirm": True,
        "app_metadata": {"role": "event_coordinator"},
    }).user
    session = auth_client.auth.sign_in_with_password({"email": email, "password": password}).session
    event_ids: list[str] = []
    try:
        yield {
            "id": str(user.id),
            "headers": {
                "Cookie": f"sb_access_token={session.access_token}",
                "X-Assignment-Service-Token": os.environ["ASSIGNMENT_SERVICE_SECRET"],
            },
            "event_ids": event_ids,
        }
    finally:
        for event_id in event_ids:
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        admin.auth.admin.delete_user(str(user.id))


def _event(admin, coordinator, status, **extra):
    row = admin.schema("events").table("events").insert({
        "organiser_id": str(uuid.uuid4()), "assigned_coordinator_id": coordinator["id"],
        "status": status, "name": f"spm-test S-89 {status} {uuid.uuid4().hex[:6]}",
        "purpose": "Venue unavailability", "start_date": DAY, "start_time": "09:00",
        "end_date": DAY, "end_time": "17:00", "expected_attendance": 80,
        "submitted_at": "2026-10-01T00:00:00Z", "decision": "approved",
        "decided_at": "2026-10-02T00:00:00Z", **extra,
    }).execute().data[0]
    coordinator["event_ids"].append(row["id"])
    return row


def _body(event, **changes):
    return {
        "reason": "spm-test Hall closed for repairs",
        "alternatives_considered": "spm-test Two halls discussed; neither fits",
        "expected_version": event.get("edit_version") or 0,
        "affected_booking_ids": [BOOKING],
        **changes,
    }


def _stored(admin, event_id):
    return admin.schema("events").table("events").select("*").eq("id", event_id).execute().data[0]


def _history(admin, event_id):
    return (
        admin.schema("events").table("event_history").select("*")
        .eq("event_id", event_id).eq("action", "cancelled_venue_unavailable").execute().data
    )


# --- TC-EVENTS-450 ------------------------------------------------------------
def test_the_recorded_cancellation_persists_and_satisfies_every_constraint(admin, coordinator):
    planning = _event(admin, coordinator, "planning")
    confirmed = _event(
        admin, coordinator, "confirmed", safety_decision="approved",
        safety_officer_id=str(uuid.uuid4()), safety_decided_at="2026-10-03T00:00:00Z",
    )

    with httpx.Client(base_url=BASE_URL, timeout=20.0, headers=coordinator["headers"]) as api:
        for event in (planning, confirmed):
            url = f"/internal/events/{event['id']}/venue-cancellation"
            response = api.post(url, json=_body(event))
            assert response.status_code == 200, (
                f"{response.text} -- check the S-89 block of events.sql is applied"
            )
            row = _stored(admin, event["id"])
            assert row["status"] == "cancelled"
            assert row["venue_cancellation_reason"] == "spm-test Hall closed for repairs"
            assert row["venue_cancellation_alternatives"] == "spm-test Two halls discussed; neither fits"
            assert row["venue_cancellation_booking_ids"] == [BOOKING]
            assert row["venue_cancelled_by"] == coordinator["id"]
            assert row["venue_cancelled_at"]
            assert row["cancellation_decision"] is None
            assert row["venue_cancellation_previous_status"] == event["status"]
            assert _history(admin, event["id"]) == []  # its own step

            history = api.post(f"/internal/events/{event['id']}/venue-cancellation/history")
            assert history.status_code == 200, history.text
            [entry] = _history(admin, event["id"])
            assert entry["details"]["affected_booking_ids"] == [BOOKING]
            assert entry["details"]["previous_status"] == event["status"]
            assert entry["actor_id"] == coordinator["id"]

        # Resuming returns the record unchanged.
        again = api.post(
            f"/internal/events/{confirmed['id']}/venue-cancellation",
            json=_body(confirmed, reason="spm-test something else", expected_version=0),
        )
        assert again.status_code == 200, again.text
        assert _stored(admin, confirmed["id"])["venue_cancellation_reason"] == "spm-test Hall closed for repairs"
        assert len(_history(admin, confirmed["id"])) == 1

        complete = f"/internal/events/{confirmed['id']}/venue-cancellation/complete"
        assert api.post(f"/internal/events/{confirmed['id']}/venue-cancellation/history").status_code == 200
        first = api.post(complete)
        assert first.status_code == 200, first.text
        completed_at = _stored(admin, confirmed["id"])["venue_cancellation_completed_at"]
        assert completed_at
        assert api.post(complete).status_code == 200
        assert _stored(admin, confirmed["id"])["venue_cancellation_completed_at"] == completed_at


# --- TC-EVENTS-451 ------------------------------------------------------------
def test_a_stale_version_is_refused(admin, coordinator):
    event = _event(admin, coordinator, "planning")
    version = event.get("edit_version") or 0

    with httpx.Client(base_url=BASE_URL, timeout=20.0, headers=coordinator["headers"]) as api:
        edited = api.patch(
            f"/events/assigned/{event['id']}",
            json={"expected_version": version, "internal_notes": "spm-test a routine edit"},
        )
        assert edited.status_code == 200, edited.text

        stale = api.post(f"/internal/events/{event['id']}/venue-cancellation", json=_body(event))
        assert stale.status_code == 409, stale.text
        assert stale.json()["detail"] == "This event changed since you opened it. Reload and try again."

    assert _stored(admin, event["id"])["status"] == "planning"
    assert _history(admin, event["id"]) == []


# --- TC-EVENTS-452 ------------------------------------------------------------
def test_history_is_recorded_once_and_gates_completion(admin, coordinator):
    event = _event(admin, coordinator, "planning")

    with httpx.Client(base_url=BASE_URL, timeout=20.0, headers=coordinator["headers"]) as api:
        cancel = f"/internal/events/{event['id']}/venue-cancellation"
        assert api.post(cancel, json=_body(event)).status_code == 200

        early = api.post(f"{cancel}/complete")
        assert early.status_code == 409, early.text
        assert early.json()["detail"] == "The cancellation has not been recorded in the event history yet."

        for _ in range(3):
            recorded = api.post(f"{cancel}/history")
            assert recorded.status_code == 200, (
                f"{recorded.text} -- check the S-89 events.sql block (unique index) is applied"
            )
        [entry] = _history(admin, event["id"])
        stored = _stored(admin, event["id"])
        # The entry carries when the cancellation happened, not when it was written.
        assert entry["occurred_at"][:19] == stored["venue_cancelled_at"][:19]
        assert entry["details"]["reason"] == stored["venue_cancellation_reason"]

        assert api.post(f"{cancel}/complete").status_code == 200

    # The database itself refuses a second entry.
    duplicate = None
    try:
        admin.schema("events").table("event_history").insert({
            "event_id": event["id"], "actor_id": coordinator["id"], "actor_role": "event_coordinator",
            "category": "review", "action": "cancelled_venue_unavailable", "details": {},
        }).execute()
    except Exception as exc:  # noqa: BLE001 -- the code is what matters
        duplicate = getattr(exc, "code", None)
    assert duplicate == "23505"
