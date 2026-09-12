"""Fixtures for the users service's integration tests.

These run against the real service in Docker and a real (test) Supabase
project. They create accounts and delete them again, which is why they point
at `.env.test` and never at the project you work against day to day.
"""

import os
from pathlib import Path

import pytest
from supabase import create_client

REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_TEST = REPO_ROOT / ".env.test"


def _load_env_test() -> None:
    """Read .env.test into the environment.

    docker compose reads this file itself, but pytest runs on the host and
    would otherwise have no credentials to clean up with. Values already in
    the environment win, so CI can set them directly.
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

# The service is published on the host, so it is localhost here -- not the
# compose hostname in USERS_SERVICE_URL, which only resolves inside the
# compose network.
BASE_URL = f"http://localhost:{os.environ.get('USERS_SERVICE_PORT', '8001')}"

requires_env = pytest.mark.skipif(
    not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")),
    reason="needs .env.test with a test Supabase project",
)


@pytest.fixture(scope="session")
def admin():
    """A service_role client, used only to clean up what the tests create."""
    return create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )


@pytest.fixture
def cleanup(admin):
    """Delete every account a test made, pass or fail.

    The suite has to be runnable twice in a row, so nothing is allowed to
    survive it. Deleting the auth user takes the profile row with it via the
    foreign key, and the row is deleted here anyway in case that cascade was
    dropped from the schema.
    """
    created: list[str] = []
    yield created
    for user_id in created:
        try:
            admin.schema("users").table("users").delete().eq("id", user_id).execute()
        except Exception:
            pass
        try:
            admin.auth.admin.delete_user(user_id)
        except Exception:
            pass
