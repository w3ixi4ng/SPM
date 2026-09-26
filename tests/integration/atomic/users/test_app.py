"""Integration tests for the users service -- see TEST_CASES.md.

The real service, in Docker, against a real (test) Supabase project. These are
the only tests that can prove the `users` schema is exposed, that the grants
ran, and that the table is where the code thinks it is.

    docker compose --env-file .env.test up -d --build --wait
    pytest tests/integration

Deliberately few: one round trip proves the whole chain at once.
"""

import uuid
from http.cookies import SimpleCookie

import httpx
import pytest
from .conftest import BASE_URL, requires_env

pytestmark = requires_env

PASSWORD = "correct-horse-battery-staple"


def unique_email() -> str:
    return f"spm-test-{uuid.uuid4().hex[:12]}@example.com"


def session_cookies(response) -> dict:
    """The session out of the Set-Cookie headers.

    Read by hand rather than through httpx's cookie jar: the cookies are set
    Secure, and a jar correctly refuses to send those back over plain http to
    a container published on localhost.
    """
    jar = {}
    for header in response.headers.get_list("set-cookie"):
        parsed = SimpleCookie()
        parsed.load(header)
        for name, morsel in parsed.items():
            jar[name] = morsel.value
    return jar


def as_header(jar: dict) -> dict:
    return {"Cookie": "; ".join(f"{name}={value}" for name, value in jar.items())}


@pytest.fixture
def api():
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:
        yield client


# --- TC-USERS-101 ---------------------------------------------------------
def test_signup_login_me_logout_round_trip(api, cleanup, admin):
    email = unique_email()

    created = api.post(
        "/users/signup", json={"name": "Ada Lovelace", "email": email, "password": PASSWORD}
    )
    assert created.status_code == 201, created.text
    profile = created.json()
    cleanup.append(profile["id"])

    assert profile["email"] == email
    assert profile["name"] == "Ada Lovelace"
    # The profile really is in users.users, not somewhere in public.
    stored = (
        admin.schema("users").table("users").select("*").eq("id", profile["id"]).execute()
    )
    assert stored.data, "no row in users.users -- check the schema is exposed and granted"
    auth_user = admin.auth.admin.get_user_by_id(profile["id"]).user
    assert auth_user.app_metadata["role"] == "event_organiser"

    signup_session = session_cookies(created)
    if not signup_session:
        pytest.skip(
            "sign-up returned no session: turn off Authentication -> Providers -> "
            "Email -> Confirm email in the TEST Supabase project"
        )

    # The cookies are the whole session, and they are locked down.
    raw = created.headers.get_list("set-cookie")
    assert all("HttpOnly" in header for header in raw)
    assert all("Secure" in header for header in raw)
    assert "access_token" not in created.text

    me = api.get("/users/me", headers=as_header(signup_session))
    assert me.status_code == 200, me.text
    assert me.json() == {**profile, "role": "event_organiser"}

    assert api.post("/users/logout", headers=as_header(signup_session)).status_code == 204

    signed_in = api.post("/users/login", json={"email": email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json() == profile

    me_again = api.get("/users/me", headers=as_header(session_cookies(signed_in)))
    assert me_again.status_code == 200
    assert me_again.json()["id"] == profile["id"]
    assert me_again.json()["role"] == "event_organiser"


# --- TC-USERS-102 ---------------------------------------------------------
def test_signing_up_twice_with_one_email_is_refused(api, cleanup):
    email = unique_email()
    payload = {"name": "Ada Lovelace", "email": email, "password": PASSWORD}

    first = api.post("/users/signup", json=payload)
    assert first.status_code == 201, first.text
    cleanup.append(first.json()["id"])

    second = api.post("/users/signup", json=payload)

    assert second.status_code == 409
    assert second.json()["detail"] == "Email already registered"


# --- TC-USERS-103 ---------------------------------------------------------
def test_me_without_a_session_is_401(api):
    response = api.get("/users/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


# --- TC-USERS-104 ---------------------------------------------------------
def test_public_signup_cannot_choose_another_role(api, cleanup):
    response = api.post(
        "/users/signup",
        json={
            "name": "Ada Lovelace",
            "email": unique_email(),
            "password": PASSWORD,
            "role": "event_coordinator",
        },
    )

    # If this assertion ever fails because an account was incorrectly created,
    # still register it for fixture cleanup before reporting the failure.
    if response.status_code == 201:
        cleanup.append(response.json()["id"])

    assert response.status_code == 422
    assert "role" in response.json()["errors"]


# --- TC-USERS-105 ---------------------------------------------------------
def test_coordinator_listing_against_real_supabase(api, cleanup, admin):
    def seed(role: str) -> str:
        email = unique_email()
        created = admin.auth.admin.create_user(
            {
                "email": email,
                "password": PASSWORD,
                "email_confirm": True,
                "app_metadata": {"role": role},
            }
        )
        user_id = str(created.user.id)
        cleanup.append(user_id)
        admin.schema("users").table("users").insert(
            {"id": user_id, "name": role, "email": email}
        ).execute()
        return user_id

    coordinator_id = seed("event_coordinator")
    organiser_id = seed("event_organiser")

    response = api.get("/users/coordinators")

    assert response.status_code == 200, response.text
    ids = [row["id"] for row in response.json()]
    assert coordinator_id in ids
    assert organiser_id not in ids
    assert len(ids) == len(set(ids))  # no duplicates from pagination
