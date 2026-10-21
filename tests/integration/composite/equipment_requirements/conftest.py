"""Fixtures for real equipment-requirements integration tests."""

import os
import uuid
from pathlib import Path

import pytest
from tests.supabase_client import create_client

REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_TEST = REPO_ROOT / ".env.test"
PASSWORD = "correct-horse-battery-staple"


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

BASE_URL = f"http://localhost:{os.environ.get('EQUIPMENT_REQUIREMENTS_SERVICE_PORT', '8102')}"
GATEWAY_BASE_URL = f"http://localhost:{os.environ.get('KONG_PROXY_PORT', '8000')}/api"

requires_env = pytest.mark.skipif(
    not all(os.environ.get(name) for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY")),
    reason="needs .env.test with a test Supabase project",
)


@pytest.fixture(scope="session")
def admin():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


@pytest.fixture(scope="session")
def auth_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def _make_user(admin, role: str) -> dict:
    email = f"spm-test-equipment-requirements-{uuid.uuid4().hex[:10]}@example.com"
    created = admin.auth.admin.create_user({
        "email": email,
        "password": PASSWORD,
        "email_confirm": True,
        "app_metadata": {"role": role},
    })
    user_id = str(created.user.id)
    admin.schema("users").table("users").insert({
        "id": user_id,
        "name": f"spm-test {role}",
        "email": email,
    }).execute()
    return {"id": user_id, "email": email, "password": PASSWORD}


def cookie_for(auth_client, user: dict) -> dict:
    signed_in = auth_client.auth.sign_in_with_password({
        "email": user["email"],
        "password": user["password"],
    })
    return {"Cookie": f"sb_access_token={signed_in.session.access_token}"}


@pytest.fixture
def world(admin):
    coordinator = _make_user(admin, "event_coordinator")
    new_coordinator = _make_user(admin, "event_coordinator")
    support = _make_user(admin, "technical_support")
    organiser = _make_user(admin, "event_organiser")
    event_id = equipment_id = None

    try:
        equipment_id = admin.schema("equipment").table("equipment").insert({
            "type": f"spm-test Projector {uuid.uuid4().hex[:8]}",
            "description": "Integration test item",
            "total_quantity": 10,
            "created_by": support["id"],
        }).execute().data[0]["id"]
        event_id = admin.schema("events").table("events").insert({
            "organiser_id": organiser["id"],
            "assigned_coordinator_id": coordinator["id"],
            "status": "planning",
            "name": "spm-test Equipment planning",
            "purpose": "Prove requirement orchestration",
            "start_date": "2026-11-12",
            "start_time": "09:00",
            "end_date": "2026-11-12",
            "end_time": "12:00",
            "expected_attendance": 80,
            "decision": "approved",
            "decided_at": "2026-10-01T00:00:00Z",
            "submitted_at": "2026-09-30T00:00:00Z",
            "technical_support_required": True,
            "technical_support_details": "Prepare the recorded equipment",
            "assigned_technical_support_id": support["id"],
            "technical_support_assigned_at": "2026-10-01T01:00:00Z",
        }).execute().data[0]["id"]
        yield {
            "coordinator": coordinator,
            "new_coordinator": new_coordinator,
            "support": support,
            "event_id": event_id,
            "equipment_id": equipment_id,
        }
    finally:
        if event_id:
            admin.schema("equipment").table("requirement_changes").delete().eq("event_id", event_id).execute()
            admin.schema("equipment").table("requirements").delete().eq("event_id", event_id).execute()
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        if equipment_id:
            admin.schema("equipment").table("equipment").delete().eq("id", equipment_id).execute()
        for user in (coordinator, new_coordinator, support, organiser):
            admin.auth.admin.delete_user(user["id"])
