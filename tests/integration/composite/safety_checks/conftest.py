"""Fixtures for the real S-86 safety_checks composite."""

import os
import uuid
from pathlib import Path

import pytest
from supabase import create_client

REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_TEST = REPO_ROOT / ".env.test"
PASSWORD = "correct-horse-battery-staple"


def _load_env_test():
    if not ENV_TEST.is_file():
        return
    for line in ENV_TEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_test()

GATEWAY_BASE_URL = f"http://localhost:{os.environ.get('KONG_PROXY_PORT', '8000')}/api"

requires_env = pytest.mark.skipif(
    not all(
        os.environ.get(name)
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY")
    ),
    reason="needs .env.test with the S-86 events SQL applied and the stack running",
)


@pytest.fixture(scope="session")
def admin():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


@pytest.fixture(scope="session")
def auth_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def make_user(admin, role):
    email = f"spm-test-safety-{uuid.uuid4().hex[:10]}@example.com"
    created = admin.auth.admin.create_user(
        {
            "email": email,
            "password": PASSWORD,
            "email_confirm": True,
            "app_metadata": {"role": role},
        }
    )
    user_id = str(created.user.id)
    admin.schema("users").table("users").insert(
        {"id": user_id, "name": f"spm-test {role}", "email": email}
    ).execute()
    return {"id": user_id, "email": email, "password": PASSWORD}


def cookie_for(auth_client, user):
    signed_in = auth_client.auth.sign_in_with_password(
        {"email": user["email"], "password": user["password"]}
    )
    return {"Cookie": f"sb_access_token={signed_in.session.access_token}"}


@pytest.fixture
def safety_world(admin):
    organiser = make_user(admin, "event_organiser")
    coordinator = make_user(admin, "event_coordinator")
    support = make_user(admin, "technical_support")
    officer = make_user(admin, "safety_officer")
    venue_staff = make_user(admin, "venue_staff")
    users = (organiser, coordinator, support, officer, venue_staff)
    event_id = venue_id = equipment_id = None
    try:
        venue_id = admin.schema("venues").table("venues").insert(
            {
                "name": f"spm-test Safety Hall {uuid.uuid4().hex[:8]}",
                "location": "Building A",
                "capacity": 200,
                "facilities": ["sound_system"],
                "accessibility": ["wheelchair_access"],
                "room_layouts": ["theatre"],
                "operating_hours": [
                    {"day": "wed", "open": "08:00:00", "close": "18:00:00"}
                ],
                "description": "No open flame; keep the north exit clear",
                "created_by": venue_staff["id"],
            }
        ).execute().data[0]["id"]
        equipment_id = admin.schema("equipment").table("equipment").insert(
            {
                "type": f"spm-test Safety microphone {uuid.uuid4().hex[:8]}",
                "description": "Keep cables behind barriers",
                "total_quantity": 10,
                "created_by": support["id"],
            }
        ).execute().data[0]["id"]
        event_id = admin.schema("events").table("events").insert(
            {
                "organiser_id": organiser["id"],
                "assigned_coordinator_id": coordinator["id"],
                "status": "confirmed",
                "name": "spm-test Operational safety review",
                "purpose": "Prove S-86 orchestration",
                "start_date": "2026-11-18",
                "start_time": "09:00",
                "end_date": "2026-11-18",
                "end_time": "12:00",
                "expected_attendance": 120,
                "special_requirements": "Keep emergency access clear and control crowd movement",
                "room_layout": "theatre",
                "required_facilities": ["sound_system"],
                "required_accessibility": ["wheelchair_access"],
                "decision": "approved",
                "decided_at": "2026-10-01T00:00:00Z",
                "submitted_at": "2026-09-30T00:00:00Z",
                "technical_support_required": True,
                "technical_support_details": "Place speakers away from exit routes",
                "assigned_technical_support_id": support["id"],
                "technical_support_assigned_at": "2026-10-01T01:00:00Z",
            }
        ).execute().data[0]["id"]
        admin.schema("equipment").table("requirements").insert(
            {
                "event_id": event_id,
                "equipment_item_id": equipment_id,
                "required_quantity": 4,
                "recorded_by_coordinator_id": coordinator["id"],
            }
        ).execute()
        admin.schema("bookings").table("bookings").insert(
            {
                "event_id": event_id,
                "venue_id": venue_id,
                "coordinator_id": coordinator["id"],
                "coordinator_name": "spm-test Coordinator",
                "coordinator_email": coordinator["email"],
                "status": "confirmed",
                "booking_date": "2026-11-18",
                "start_time": "09:00",
                "end_time": "12:00",
                "event_name": "spm-test Operational safety review",
                "event_purpose": "Prove S-86 orchestration",
                "expected_attendance": 120,
                "special_requirements": "Keep emergency access clear",
                "required_accessibility": ["wheelchair_access"],
                "required_facilities": ["sound_system"],
                "room_layout": "theatre",
                "notes": "Use the north entrance",
                "venue_name": "spm-test Safety Hall",
                "decision_reason": None,
                "decided_by": venue_staff["id"],
                "decided_at": "2026-10-02T00:00:00Z",
            }
        ).execute()
        yield {
            "event_id": event_id,
            "officer": officer,
            "organiser": organiser,
            "support": support,
        }
    finally:
        if event_id:
            admin.schema("bookings").table("bookings").delete().eq("event_id", event_id).execute()
            admin.schema("equipment").table("requirements").delete().eq("event_id", event_id).execute()
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        if equipment_id:
            admin.schema("equipment").table("equipment").delete().eq("id", equipment_id).execute()
        if venue_id:
            admin.schema("venues").table("venues").delete().eq("id", venue_id).execute()
        for user in users:
            admin.auth.admin.delete_user(user["id"])

