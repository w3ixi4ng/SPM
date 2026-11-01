"""Fixtures for the real S-51 event_registrations composite."""

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from tests.supabase_client import create_client

REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_TEST = REPO_ROOT / ".env.test"
PASSWORD = "correct-horse-battery-staple"
SGT = timezone(timedelta(hours=8))


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

GATEWAY_BASE_URL = f"http://localhost:{os.environ.get('KONG_PROXY_PORT', '8000')}/api"

requires_env = pytest.mark.skipif(
    not all(
        os.environ.get(name)
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY")
    ),
    reason="needs .env.test with the S-51 SQL applied and the stack running",
)


@pytest.fixture(scope="session")
def admin():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


@pytest.fixture(scope="session")
def auth_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def sgt_now() -> datetime:
    return datetime.now(SGT).replace(tzinfo=None, second=0, microsecond=0)


def confirmed_event(
    admin, organiser_id: str, *, opens: datetime, closes: datetime, expected_attendance: int = 40
) -> str:
    """A confirmed event starting ten days out, with the given period."""
    start = sgt_now() + timedelta(days=10)
    return admin.schema("events").table("events").insert({
        "organiser_id": organiser_id,
        "status": "confirmed",
        "name": f"spm-test S-51 {uuid.uuid4().hex[:8]}",
        "purpose": "Prove registration end to end",
        "start_date": start.date().isoformat(),
        "start_time": "18:00",
        "end_date": start.date().isoformat(),
        "end_time": "21:00",
        "expected_attendance": expected_attendance,
        "submitted_at": "2026-10-01T00:00:00Z",
        "decision": "approved",
        "decided_at": "2026-10-02T00:00:00Z",
        "safety_decision": "approved",
        "safety_officer_id": organiser_id,
        "safety_decided_at": "2026-10-03T00:00:00Z",
        "registration_required": True,
        "registration_opens_at": opens.isoformat(),
        "registration_closes_at": closes.isoformat(),
    }).execute().data[0]["id"]


def _delete_user_rows(admin, schema: str, table: str, column: str, user_id: str) -> None:
    """An exact-id DELETE is safe to repeat after a lost or timed-out response."""
    for attempt in range(3):
        try:
            admin.schema(schema).table(table).delete().eq(column, user_id).execute()
            return
        except (httpx.RemoteProtocolError, httpx.ReadTimeout):
            if attempt == 2:
                raise


@pytest.fixture
def attendee(admin, auth_client):
    email = f"spm-test-registration-{uuid.uuid4().hex[:10]}@example.com"
    created = admin.auth.admin.create_user({
        "email": email,
        "password": PASSWORD,
        "email_confirm": True,
        "app_metadata": {"role": "attendee"},
    })
    user_id = str(created.user.id)
    admin.schema("users").table("users").insert(
        {"id": user_id, "name": "spm-test attendee", "email": email}
    ).execute()
    signed_in = auth_client.auth.sign_in_with_password({"email": email, "password": PASSWORD})
    try:
        yield {
            "id": user_id,
            "headers": {"Cookie": f"sb_access_token={signed_in.session.access_token}"},
        }
    finally:
        _delete_user_rows(admin, "registrations", "registrations", "attendee_id", user_id)
        # S-49: registering leaves a confirmation in the Attendee's inbox.
        _delete_user_rows(admin, "notifications", "notifications", "recipient_id", user_id)
        admin.auth.admin.delete_user(user_id)


@pytest.fixture
def make_account(admin, auth_client):
    """S-48: signed-in accounts with a given role and profile name."""
    made = []

    def make(role: str, name: str) -> dict:
        email = f"spm-test-registration-{uuid.uuid4().hex[:10]}@example.com"
        created = admin.auth.admin.create_user({
            "email": email,
            "password": PASSWORD,
            "email_confirm": True,
            "app_metadata": {"role": role},
        })
        user_id = str(created.user.id)
        made.append(user_id)
        admin.schema("users").table("users").insert(
            {"id": user_id, "name": name, "email": email}
        ).execute()
        signed_in = auth_client.auth.sign_in_with_password({"email": email, "password": PASSWORD})
        return {
            "id": user_id,
            "name": name,
            "email": email,
            "headers": {"Cookie": f"sb_access_token={signed_in.session.access_token}"},
        }

    yield make
    for user_id in made:
        _delete_user_rows(admin, "registrations", "registrations", "attendee_id", user_id)
        _delete_user_rows(admin, "registrations", "waiting_list", "attendee_id", user_id)
        # S-58: withdrawing or declining records the Attendee's withdrawal.
        _delete_user_rows(admin, "registrations", "withdrawals", "attendee_id", user_id)
        # S-49: registering leaves a confirmation in the Attendee's inbox.
        _delete_user_rows(admin, "notifications", "notifications", "recipient_id", user_id)
        admin.auth.admin.delete_user(user_id)
