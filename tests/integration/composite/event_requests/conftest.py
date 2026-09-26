"""Fixtures for the event_requests composite service's integration tests.

These run against the real composite, the real atomic services, and a real
(test) Supabase project -- never against `.env`, since they create and delete
real accounts and events.
"""

import os
import time
import uuid
from pathlib import Path

import httpx
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

BASE_URL = f"http://localhost:{os.environ.get('EVENT_REQUESTS_SERVICE_PORT', '8100')}"
EVENTS_BASE_URL = f"http://localhost:{os.environ.get('EVENTS_SERVICE_PORT', '8002')}"
GATEWAY_BASE_URL = f"http://localhost:{os.environ.get('KONG_PROXY_PORT', '8000')}/api"

requires_env = pytest.mark.skipif(
    not all(
        os.environ.get(name)
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY")
    ),
    reason="needs .env.test with a test Supabase project",
)


def request_with_retry(client: httpx.Client, method: str, url: str, *, retries: int = 6, delay: float = 0.5, **kwargs):
    """Retries a request when the connection itself is refused, not when it
    gets back an answer -- a 409 or 500 is a real result and must not be
    retried away, only a `ConnectError` is.

    `_event_requests_reachable` below only guards the moment before a test
    starts; the port has been observed to drop mid-test too, which surfaces
    here as the request itself failing rather than the fixture.
    """
    last_error = None
    for _ in range(retries):
        try:
            return client.request(method, url, **kwargs)
        except httpx.ConnectError as exc:
            last_error = exc
            time.sleep(delay)
    raise last_error


@pytest.fixture(autouse=True)
def _event_requests_reachable():
    """Waits for `event_requests`'s own published port to accept connections
    before each test.

    On some CI runners the container reports healthy (checked from inside the
    container) a moment before its host port mapping is actually wired, and
    that gap has shown up again mid-run, not just at startup -- so this polls
    before every test rather than once per session. Never observed locally;
    a no-op there since the first request always succeeds.
    """
    last_error = None
    for _ in range(10):
        try:
            httpx.get(f"{BASE_URL}/health", timeout=1.0)
            return
        except httpx.HTTPError as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"{BASE_URL}/health never became reachable: {last_error}")


@pytest.fixture(scope="session")
def admin():
    return create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )


@pytest.fixture(scope="session")
def auth_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def _make_user(admin, role: str) -> dict:
    email = f"spm-event-requests-{uuid.uuid4().hex[:12]}@example.com"
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
    admin.schema("users").table("users").insert(
        {"id": user_id, "name": role, "email": email}
    ).execute()
    return {"id": user_id, "email": email, "password": password}


@pytest.fixture
def organiser_session(admin, auth_client):
    """A signed-in event_organiser, and the ids it created for cleanup."""
    user = _make_user(admin, "event_organiser")
    event_ids: list[str] = []

    try:
        signed_in = auth_client.auth.sign_in_with_password(
            {"email": user["email"], "password": user["password"]}
        )
        yield {
            "user_id": user["id"],
            "access_token": signed_in.session.access_token,
            "event_ids": event_ids,
        }
    finally:
        for event_id in event_ids:
            admin.schema("events").table("events").delete().eq("id", event_id).execute()
        admin.auth.admin.delete_user(user["id"])


@pytest.fixture
def coordinator(admin):
    """One seeded event_coordinator account, cleaned up after."""
    user = _make_user(admin, "event_coordinator")
    try:
        yield user["id"]
    finally:
        admin.auth.admin.delete_user(user["id"])


@pytest.fixture
def second_coordinator(admin):
    """A second seeded event_coordinator account, for reassignment cases."""
    user = _make_user(admin, "event_coordinator")
    try:
        yield user["id"]
    finally:
        admin.auth.admin.delete_user(user["id"])
