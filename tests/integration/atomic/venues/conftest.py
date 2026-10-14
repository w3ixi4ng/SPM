"""Fixtures for real venues-service integration tests."""

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

BASE_URL = f"http://localhost:{os.environ.get('VENUES_SERVICE_PORT', '8003')}"
GATEWAY_BASE_URL = f"http://localhost:{os.environ.get('KONG_PROXY_PORT', '8000')}/api"

PASSWORD = "correct-horse-battery-staple"

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
def venue_ids(admin):
    """Ids of venues a test created; every one is deleted afterwards."""
    ids: list[str] = []
    yield ids
    for venue_id in ids:
        admin.schema("venues").table("venues").delete().eq("id", venue_id).execute()


@pytest.fixture
def make_session(admin, auth_client):
    """Create a signed-in Auth user with a trusted role, deleted afterwards."""
    user_ids: list[str] = []

    def _make(role: str) -> dict:
        email = f"spm-test-venues-{uuid.uuid4().hex[:12]}@example.com"
        created = admin.auth.admin.create_user(
            {
                "email": email,
                "password": PASSWORD,
                "email_confirm": True,
                "app_metadata": {"role": role},
            }
        )
        user_id = str(created.user.id)
        user_ids.append(user_id)
        signed_in = auth_client.auth.sign_in_with_password(
            {"email": email, "password": PASSWORD}
        )
        return {
            "user_id": user_id,
            "headers": {"Cookie": f"sb_access_token={signed_in.session.access_token}"},
        }

    yield _make

    for user_id in user_ids:
        admin.auth.admin.delete_user(user_id)
