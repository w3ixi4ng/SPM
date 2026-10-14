"""Fixtures for the venue_bookings composite's integration tests.

These run against the real composite, the real users, events, venues and
bookings services, Kong, and a real (test) Supabase project -- never against
`.env`, since they create and delete real accounts, events, venues and
bookings.
"""

import os
import uuid
from pathlib import Path

import pytest
from tests.supabase_client import create_client

REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_TEST = REPO_ROOT / ".env.test"


def _load_env_test() -> None:
    if not ENV_TEST.is_file():
        return
    for line in ENV_TEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_test()

BASE_URL = f"http://localhost:{os.environ.get('VENUE_BOOKINGS_SERVICE_PORT', '8101')}"
GATEWAY_BASE_URL = f"http://localhost:{os.environ.get('KONG_PROXY_PORT', '8000')}/api"

requires_env = pytest.mark.skipif(
    not all(
        os.environ.get(name)
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY")
    ),
    reason="needs .env.test with a test Supabase project",
)


@pytest.fixture(scope="session")
def admin():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


@pytest.fixture(scope="session")
def auth_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def _make_user(admin, role: str, name: str) -> dict:
    email = f"spm-test-venue-bookings-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery-staple"
    created = admin.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "app_metadata": {"role": role},
        }
    )
    user_id = str(created.user.id)
    admin.schema("users").table("users").insert({"id": user_id, "name": name, "email": email}).execute()
    return {"id": user_id, "email": email, "password": password}


def cookie_for(auth_client, user) -> dict:
    signed_in = auth_client.auth.sign_in_with_password(
        {"email": user["email"], "password": user["password"]}
    )
    return {"Cookie": f"sb_access_token={signed_in.session.access_token}"}


@pytest.fixture
def world(admin):
    """The shared pre-conditions in TEST_CASES.md: a coordinator, a venue
    staff member, an organiser, a venue, and an event in planning assigned to
    the coordinator. Everything it creates -- and any booking a test makes
    for its event -- is deleted afterwards, pass or fail."""
    tag = uuid.uuid4().hex[:8]
    coordinator = _make_user(admin, "event_coordinator", "spm-test Coordinator")
    staff = _make_user(admin, "venue_staff", "spm-test Venue Staff")
    organiser = _make_user(admin, "event_organiser", "spm-test Organiser")
    venue_id = event_id = None

    try:
        venue_id = (
            admin.schema("venues")
            .table("venues")
            .insert(
                {
                    "name": f"spm-test Venue {tag}",
                    "location": "10 Anson Road",
                    "capacity": 150,
                    "facilities": ["projector"],
                    "accessibility": ["wheelchair_access"],
                    "room_layouts": ["theatre"],
                    "operating_hours": [{"day": "thu", "open": "08:00:00", "close": "20:00:00"}],
                    "created_by": staff["id"],
                }
            )
            .execute()
            .data[0]["id"]
        )
        event_id = (
            admin.schema("events")
            .table("events")
            .insert(
                {
                    "organiser_id": organiser["id"],
                    "status": "planning",
                    "assigned_coordinator_id": coordinator["id"],
                    "name": f"spm-test Event {tag}",
                    "purpose": "Reconnect graduates with faculty",
                    "start_date": "2026-11-12",
                    "start_time": "09:00",
                    "end_date": "2026-11-12",
                    "end_time": "18:00",
                    "expected_attendance": 120,
                    "room_layout": "theatre",
                    "required_facilities": ["projector"],
                    "required_accessibility": ["wheelchair_access"],
                    "decision": "approved",
                    "decided_at": "2026-10-01T00:00:00Z",
                    "submitted_at": "2026-09-30T00:00:00Z",
                }
            )
            .execute()
            .data[0]["id"]
        )
        yield {
            "coordinator": coordinator,
            "staff": staff,
            "venue_id": venue_id,
            "event_id": event_id,
        }
    finally:
        if event_id:
            admin.schema("bookings").table("bookings").delete().eq("event_id", event_id).execute()
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        if venue_id:
            admin.schema("venues").table("venues").delete().eq("id", venue_id).execute()
        for user in (coordinator, staff, organiser):
            admin.auth.admin.delete_user(user["id"])
