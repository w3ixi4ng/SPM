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
        admin.schema("notifications").table("notifications").delete().eq(
            "recipient_id", user["id"]
        ).execute()
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
        admin.schema("notifications").table("notifications").delete().eq(
            "recipient_id", user["id"]
        ).execute()
        admin.auth.admin.delete_user(user["id"])


@pytest.fixture
def coordinator_session(admin, auth_client):
    """A signed-in event_coordinator, for reading their own assigned queue."""
    user = _make_user(admin, "event_coordinator")
    try:
        signed_in = auth_client.auth.sign_in_with_password(
            {"email": user["email"], "password": user["password"]}
        )
        yield {"user_id": user["id"], "access_token": signed_in.session.access_token}
    finally:
        admin.schema("notifications").table("notifications").delete().eq(
            "recipient_id", user["id"]
        ).execute()
        admin.auth.admin.delete_user(user["id"])


@pytest.fixture
def lead_session(admin, auth_client):
    """A signed-in Event Coordinator Lead for the S-83 queue."""
    user = _make_user(admin, "event_coordinator_lead")
    try:
        signed_in = auth_client.auth.sign_in_with_password(
            {"email": user["email"], "password": user["password"]}
        )
        yield {"user_id": user["id"], "access_token": signed_in.session.access_token}
    finally:
        admin.schema("notifications").table("notifications").delete().eq(
            "recipient_id", user["id"]
        ).execute()
        admin.auth.admin.delete_user(user["id"])


@pytest.fixture
def technical_support_users(admin):
    users = [_make_user(admin, "technical_support") for _ in range(2)]
    try:
        yield users
    finally:
        for user in users:
            admin.auth.admin.delete_user(user["id"])


def all_technical_support_ids(admin) -> set[str]:
    page_size = 200
    ids: set[str] = set()
    page = 1
    while True:
        batch = admin.auth.admin.list_users(page=page, per_page=page_size)
        if not batch:
            break
        ids.update(
            user.id
            for user in batch
            if (user.app_metadata or {}).get("role") == "technical_support"
        )
        if len(batch) < page_size:
            break
        page += 1
    return ids


@pytest.fixture
def second_coordinator(admin):
    """A second seeded event_coordinator account, for reassignment cases."""
    user = _make_user(admin, "event_coordinator")
    try:
        yield user["id"]
    finally:
        admin.auth.admin.delete_user(user["id"])


def all_coordinator_ids(admin) -> set[str]:
    """Every event_coordinator account that currently exists in the project.

    `GET /users/coordinators` (and so the assignment logic) sees the whole
    pool, not just the accounts a given test created -- a leftover account
    from manual testing or an earlier run is just as eligible as a fixture's.
    Tests that need a *specific, deterministic* outcome (rather than merely
    "some coordinator") have to know about every candidate, not only their
    own. Paginates the same way the users service's own listing does, so a
    growing test project can't silently hide an account from this check.
    """
    page_size = 200
    ids: set[str] = set()
    page = 1
    while True:
        batch = admin.auth.admin.list_users(page=page, per_page=page_size)
        if not batch:
            break
        ids.update(
            user.id for user in batch if (user.app_metadata or {}).get("role") == "event_coordinator"
        )
        if len(batch) < page_size:
            break
        page += 1
    return ids


def block_other_coordinators(
    admin,
    organiser_id: str,
    exempt_ids: set[str],
    window: dict,
) -> list[str]:
    """Give every coordinator not in `exempt_ids` a submitted event covering
    `window`, so only the exempted ones can be picked for it. Returns the
    created event ids, for the caller to register for cleanup.

    `window` has start_date/start_time/end_date/end_time.
    """
    created_ids = []
    blocked_ids: set[str] = set()

    # CI jobs share one test Supabase project. Another run can create a
    # coordinator while this helper is inserting its blocking events, so a
    # single snapshot can immediately become stale and leave that new account
    # free. Keep taking snapshots until a complete pass finds nobody new.
    while True:
        unblocked_ids = all_coordinator_ids(admin) - exempt_ids - blocked_ids
        if not unblocked_ids:
            break

        for coordinator_id in unblocked_ids:
            row = (
                admin.schema("events")
                .table("events")
                .insert(
                    {
                        "organiser_id": organiser_id,
                        "status": "submitted",
                        "assigned_coordinator_id": coordinator_id,
                        "name": f"Blocking booking for {coordinator_id}",
                        "purpose": "Keeps this coordinator out of the pool for this test",
                        # Only the four date/time keys, deliberately -- spreading
                        # the whole `window` dict here once clobbered the `name`,
                        # `purpose`, etc. set above, because a real caller's
                        # window (SUBMITTED) has its own `name` key too, and a
                        # later key in a dict literal always wins.
                        "start_date": window["start_date"],
                        "start_time": window["start_time"],
                        "end_date": window["end_date"],
                        "end_time": window["end_time"],
                        "expected_attendance": 5,
                        "venue": "Room 2",
                        "submitted_at": "2026-09-24T00:00:00Z",
                    }
                )
                .execute()
            )
            created_ids.append(row.data[0]["id"])
            blocked_ids.add(coordinator_id)
    return created_ids
