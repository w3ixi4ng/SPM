"""Fixtures for the real notifications-service integration test."""

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

BASE_URL = f"http://localhost:{os.environ.get('NOTIFICATIONS_SERVICE_PORT', '8006')}"

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


@pytest.fixture
def notification_users(admin, auth_client):
    users = []
    try:
        for role in ("event_organiser", "event_coordinator", "attendee"):
            email = f"spm-notifications-{uuid.uuid4().hex[:12]}@example.com"
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
            signed_in = auth_client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            users.append(
                {
                    "id": user_id,
                    "role": role,
                    "access_token": signed_in.session.access_token,
                }
            )
        yield users
    finally:
        for user in users:
            admin.schema("notifications").table("notifications").delete().eq(
                "recipient_id", user["id"]
            ).execute()
            admin.auth.admin.delete_user(user["id"])
