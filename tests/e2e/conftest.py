"""Fixtures for the end-to-end suite.

These drive a real browser against the whole stack in Docker -- the built
frontend, Kong, both services, and a real (test) Supabase project. Everything
goes through the gateway on a single origin, which is the arrangement that
makes the httpOnly session cookies behave the way they do in production.

Nothing here talks to a service port directly. If a test needs to reach past
the browser it uses the admin client, the same way the integration suite does.
"""

import os
import uuid
from pathlib import Path

import pytest
from supabase import create_client

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_TEST = REPO_ROOT / ".env.test"


def _load_env_test() -> None:
    """Read .env.test into the environment.

    docker compose reads this file itself, but pytest runs on the host and
    would otherwise have no credentials to seed and clean up with. Values
    already in the environment win, so CI can set them directly.
    """
    if not ENV_TEST.is_file():
        return
    for line in ENV_TEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_test()

# Kong, never a service port. The app calls a relative `/api`, so the gateway
# is the only origin on which the whole thing is coherent.
E2E_BASE_URL = f"http://localhost:{os.environ.get('KONG_PROXY_PORT', '8000')}"

PASSWORD = "correct-horse-battery-staple"

requires_env = pytest.mark.skipif(
    not all(
        os.environ.get(name)
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY")
    ),
    reason="needs .env.test with a test Supabase project, and the stack running",
)


def unique_email() -> str:
    return f"spm-e2e-{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture(scope="session")
def base_url() -> str:
    """Point pytest-playwright at the gateway, so tests can `goto('/login')`."""
    return E2E_BASE_URL


@pytest.fixture(scope="session")
def admin():
    return create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )


@pytest.fixture
def make_user(admin):
    """Create a confirmed account with a chosen role, and clean it up after.

    `email_confirm` is set so the account can sign in immediately whatever the
    project's confirmation setting is. Only the sign-up journey depends on that
    setting, and it deliberately goes through the real form instead of this.

    The profile row is inserted by hand: `/users/me` reads `users.users` and
    404s without it, and an account created through the admin API never went
    through the sign-up route that normally writes it.
    """
    created: list[str] = []

    def _make(role: str = "event_organiser") -> dict:
        email = unique_email()
        created_user = admin.auth.admin.create_user(
            {
                "email": email,
                "password": PASSWORD,
                "email_confirm": True,
                "app_metadata": {"role": role},
            }
        )
        user_id = str(created_user.user.id)
        created.append(user_id)

        admin.schema("users").table("users").insert(
            {"id": user_id, "name": "E2E Tester", "email": email}
        ).execute()

        return {"id": user_id, "email": email, "password": PASSWORD, "role": role}

    yield _make

    for user_id in created:
        # Events, venues and bookings first: they are in other schemas with
        # no cascade back to the account, so deleting the user would strand
        # them.
        admin.schema("bookings").table("bookings").delete().eq(
            "coordinator_id", user_id
        ).execute()
        admin.schema("equipment").table("requirements").delete().eq(
            "recorded_by_coordinator_id", user_id
        ).execute()
        admin.schema("events").table("events").delete().eq(
            "organiser_id", user_id
        ).execute()
        admin.schema("venues").table("venues").delete().eq(
            "created_by", user_id
        ).execute()
        admin.schema("equipment").table("equipment").delete().eq(
            "created_by", user_id
        ).execute()
        # users.users cascades from auth.users, so the profile goes with this.
        admin.auth.admin.delete_user(user_id)


@pytest.fixture
def sign_in(page):
    """Sign in through the real login form and wait for the redirect."""

    def _sign_in(user: dict):
        page.goto("/login")
        page.fill("input[name=email]", user["email"])
        page.fill("input[name=password]", user["password"])
        page.click("button[type=submit]")
        return page

    return _sign_in
