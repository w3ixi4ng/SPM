"""Fixtures for the bookings service's integration tests.

These run against the real bookings service and a real (test) Supabase
project -- never against `.env`, since they create and delete real rows.
"""

import os
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

BASE_URL = f"http://localhost:{os.environ.get('BOOKINGS_SERVICE_PORT', '8004')}"

requires_env = pytest.mark.skipif(
    not all(os.environ.get(name) for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")),
    reason="needs .env.test with a test Supabase project",
)


@pytest.fixture(scope="session")
def admin():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


@pytest.fixture
def booking_ids(admin):
    """Ids a test created, deleted afterwards pass or fail."""
    created: list[str] = []
    try:
        yield created
    finally:
        for booking_id in created:
            admin.schema("bookings").table("bookings").delete().eq("id", booking_id).execute()
