"""Fixtures for real events-service integration tests."""

import os
import uuid
from pathlib import Path

import pytest
from supabase import create_client

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

BASE_URL = f"http://localhost:{os.environ.get('EVENTS_SERVICE_PORT', '8002')}"
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
    return create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )


@pytest.fixture(scope="session")
def auth_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


@pytest.fixture
def organiser_session(admin, auth_client):
    email = f"spm-events-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery-staple"
    created = admin.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "app_metadata": {"role": "event_organiser"},
        }
    )
    user_id = str(created.user.id)
    event_ids: list[str] = []

    try:
        signed_in = auth_client.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        access_token = signed_in.session.access_token

        yield {
            "user_id": user_id,
            "access_token": access_token,
            "event_ids": event_ids,
        }
    finally:
        for event_id in event_ids:
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        admin.auth.admin.delete_user(user_id)
