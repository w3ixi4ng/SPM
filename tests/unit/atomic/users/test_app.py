"""Unit tests for the users service -- see TEST_CASES.md.

Supabase is faked, so these prove the service's own behaviour: what it accepts,
what status it returns, and what it puts in the session cookies. They cannot
prove the schema is exposed or the grants are right; that is what the
integration tests are for.
"""

from types import SimpleNamespace

import pytest

from .conftest import (
    EMAIL,
    NAME,
    PROFILE,
    USER_ID,
    auth_error,
    fake_session,
    fake_user,
    on_insert,
    on_select,
)

ACCESS_COOKIE = "sb_access_token"
REFRESH_COOKIE = "sb_refresh_token"

SIGNUP = {"name": NAME, "email": EMAIL, "password": "correct-horse-battery"}
LOGIN = {"email": EMAIL, "password": "correct-horse-battery"}


def set_cookies(response):
    """The Set-Cookie headers, as {name: the whole attribute string}."""
    out = {}
    for header in response.headers.get_list("set-cookie"):
        out[header.split("=", 1)[0]] = header
    return out


# --- TC-USERS-001 ---------------------------------------------------------
def test_health_reports_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- TC-USERS-002 ---------------------------------------------------------
def test_signup_creates_account_and_profile(client, db, auth):
    on_select(db, [])
    on_insert(db, [PROFILE])
    auth.auth.sign_up.return_value = SimpleNamespace(
        user=fake_user(), session=fake_session()
    )

    response = client.post("/users/signup", json=SIGNUP)

    assert response.status_code == 201
    assert response.json() == {"id": USER_ID, "name": NAME, "email": EMAIL}

    auth.auth.sign_up.assert_called_once_with(
        {"email": EMAIL, "password": SIGNUP["password"]}
    )
    db.auth.admin.update_user_by_id.assert_called_once_with(
        USER_ID,
        {"app_metadata": {"role": "event_organiser"}},
    )
    # The profile carries the auth user's id rather than one of its own.
    db.schema.return_value.table.return_value.insert.assert_called_once_with(
        {"id": USER_ID, "name": NAME, "email": EMAIL}
    )

    cookies = set_cookies(response)
    assert set(cookies) == {ACCESS_COOKIE, REFRESH_COOKIE}
    for cookie in cookies.values():
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert "Path=/" in cookie
    # The token is in the cookie and nowhere else -- never in the body.
    assert "access-token" not in response.text


# --- TC-USERS-003 ---------------------------------------------------------
def test_signup_rejects_email_that_already_has_a_profile(client, db, auth):
    on_select(db, [{"id": USER_ID}])

    response = client.post("/users/signup", json=SIGNUP)

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"
    # Rejected before any account was created upstream.
    auth.auth.sign_up.assert_not_called()


# --- TC-USERS-004 ---------------------------------------------------------
def test_signup_requires_a_name(client, db):
    on_select(db, [])
    response = client.post(
        "/users/signup", json={"email": EMAIL, "password": SIGNUP["password"]}
    )
    assert response.status_code == 422


# --- TC-USERS-005 ---------------------------------------------------------
def test_signup_rejects_a_malformed_email(client, db):
    on_select(db, [])
    response = client.post("/users/signup", json={**SIGNUP, "email": "not-an-email"})
    assert response.status_code == 422


# --- TC-USERS-006 ---------------------------------------------------------
def test_signup_rejects_a_short_password(client, db):
    on_select(db, [])
    response = client.post("/users/signup", json={**SIGNUP, "password": "short"})
    assert response.status_code == 422


# --- TC-USERS-007 ---------------------------------------------------------
def test_signup_maps_an_upstream_duplicate_to_409(client, db, auth):
    # The profile row is gone but the account is not, so only Supabase knows.
    on_select(db, [])
    auth.auth.sign_up.side_effect = auth_error("User already registered", 422)

    response = client.post("/users/signup", json=SIGNUP)

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


# --- TC-USERS-008 ---------------------------------------------------------
def test_signup_undoes_the_account_when_the_profile_cannot_be_written(client, db, auth):
    on_select(db, [])
    on_insert(db, error=RuntimeError("insert failed"))
    auth.auth.sign_up.return_value = SimpleNamespace(
        user=fake_user(), session=fake_session()
    )

    response = client.post("/users/signup", json=SIGNUP)

    assert response.status_code == 500
    # Otherwise the address is registered for good with no profile behind it.
    db.auth.admin.delete_user.assert_called_once_with(USER_ID)
    assert set_cookies(response) == {}


# --- TC-USERS-009 ---------------------------------------------------------
def test_signup_sets_no_cookies_when_the_email_needs_confirming(client, db, auth):
    on_select(db, [])
    on_insert(db, [PROFILE])
    # Email confirmation on: the account exists but is not signed in yet.
    auth.auth.sign_up.return_value = SimpleNamespace(user=fake_user(), session=None)

    response = client.post("/users/signup", json=SIGNUP)

    assert response.status_code == 201
    assert set_cookies(response) == {}


# --- TC-USERS-010 ---------------------------------------------------------
def test_signup_normalises_the_email(client, db, auth):
    on_select(db, [])
    on_insert(db, [PROFILE])
    auth.auth.sign_up.return_value = SimpleNamespace(
        user=fake_user(), session=fake_session()
    )

    response = client.post("/users/signup", json={**SIGNUP, "email": "  Ada@Example.COM  "})

    assert response.status_code == 201
    # Stored and looked up in one casing, so Ada@ and ada@ are one account.
    auth.auth.sign_up.assert_called_once_with(
        {"email": EMAIL, "password": SIGNUP["password"]}
    )
    select = db.schema.return_value.table.return_value.select.return_value
    select.eq.assert_called_once_with("email", EMAIL)


# --- TC-USERS-011 ---------------------------------------------------------
def test_login_returns_the_profile_and_sets_cookies(client, db, auth):
    auth.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=fake_user(), session=fake_session()
    )
    on_select(db, [PROFILE])

    response = client.post("/users/login", json=LOGIN)

    assert response.status_code == 200
    assert response.json() == {"id": USER_ID, "name": NAME, "email": EMAIL}
    assert set(set_cookies(response)) == {ACCESS_COOKIE, REFRESH_COOKIE}
    assert "access-token" not in response.text


# --- TC-USERS-012 ---------------------------------------------------------
def test_login_rejects_a_wrong_password_without_saying_so(client, db, auth):
    auth.auth.sign_in_with_password.side_effect = auth_error(
        "Invalid login credentials", 400
    )

    response = client.post("/users/login", json=LOGIN)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert set_cookies(response) == {}


# --- TC-USERS-013 ---------------------------------------------------------
def test_login_answers_an_unknown_email_exactly_the_same_way(client, db, auth):
    # Same error from Supabase, same answer out -- the form cannot be used to
    # find out which addresses have accounts.
    auth.auth.sign_in_with_password.side_effect = auth_error(
        "Invalid login credentials", 400
    )

    response = client.post("/users/login", json={**LOGIN, "email": "nobody@example.com"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


# --- TC-USERS-014 ---------------------------------------------------------
def test_login_requires_a_password(client):
    response = client.post("/users/login", json={"email": EMAIL})
    assert response.status_code == 422


# --- TC-USERS-015 ---------------------------------------------------------
def test_login_passes_on_a_rate_limit(client, db, auth):
    auth.auth.sign_in_with_password.side_effect = auth_error(
        "Request rate limit reached", 429
    )

    response = client.post("/users/login", json=LOGIN)

    assert response.status_code == 429


# --- TC-USERS-016 ---------------------------------------------------------
def test_logout_clears_the_cookies(client, db):
    client.cookies.set(ACCESS_COOKIE, "access-token")
    client.cookies.set(REFRESH_COOKIE, "refresh-token")

    response = client.post("/users/logout")

    assert response.status_code == 204
    cookies = set_cookies(response)
    assert set(cookies) == {ACCESS_COOKIE, REFRESH_COOKIE}
    for cookie in cookies.values():
        # A cookie is deleted by being handed back already expired.
        assert "Max-Age=0" in cookie or "1970" in cookie
    # And the refresh token is revoked, so it cannot be replayed elsewhere.
    db.auth.admin.sign_out.assert_called_once_with("access-token")


# --- TC-USERS-022 ---------------------------------------------------------
def test_logout_works_without_a_session(client, db):
    response = client.post("/users/logout")

    assert response.status_code == 204
    db.auth.admin.sign_out.assert_not_called()


# --- TC-USERS-017 ---------------------------------------------------------
def test_me_returns_the_signed_in_user(client, db, auth):
    client.cookies.set(ACCESS_COOKIE, "access-token")
    auth.auth.get_user.return_value = SimpleNamespace(user=fake_user())
    on_select(db, [PROFILE])

    response = client.get("/users/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": USER_ID,
        "name": NAME,
        "email": EMAIL,
        "role": "event_organiser",
    }
    auth.auth.get_user.assert_called_once_with("access-token")


# --- TC-USERS-026 ---------------------------------------------------------
def test_me_returns_no_role_when_trusted_role_is_missing(client, db, auth):
    client.cookies.set(ACCESS_COOKIE, "access-token")
    auth.auth.get_user.return_value = SimpleNamespace(user=fake_user(role=None))
    on_select(db, [PROFILE])

    response = client.get("/users/me")

    assert response.status_code == 200
    assert response.json()["role"] is None


# --- TC-USERS-018 ---------------------------------------------------------
def test_me_is_401_with_no_cookies(client, auth):
    response = client.get("/users/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    auth.auth.get_user.assert_not_called()


# --- TC-USERS-019 ---------------------------------------------------------
def test_me_refreshes_an_expired_access_token(client, db, auth):
    client.cookies.set(ACCESS_COOKIE, "expired-token")
    client.cookies.set(REFRESH_COOKIE, "refresh-token")
    auth.auth.get_user.side_effect = auth_error("token is expired", 401)
    auth.auth.refresh_session.return_value = SimpleNamespace(
        user=fake_user(), session=fake_session("new-access", "new-refresh")
    )
    on_select(db, [PROFILE])

    response = client.get("/users/me")

    # An hour-old tab is not a logout.
    assert response.status_code == 200
    auth.auth.refresh_session.assert_called_once_with("refresh-token")
    cookies = set_cookies(response)
    assert "new-access" in cookies[ACCESS_COOKIE]
    assert "new-refresh" in cookies[REFRESH_COOKIE]


# --- TC-USERS-020 ---------------------------------------------------------
def test_me_clears_cookies_when_neither_token_works(client, auth):
    client.cookies.set(ACCESS_COOKIE, "expired-token")
    client.cookies.set(REFRESH_COOKIE, "revoked-token")
    auth.auth.get_user.side_effect = auth_error("token is expired", 401)
    auth.auth.refresh_session.side_effect = auth_error("refresh token revoked", 401)

    response = client.get("/users/me")

    assert response.status_code == 401
    # Dead cookies are taken back rather than sent on every later request.
    assert set(set_cookies(response)) == {ACCESS_COOKIE, REFRESH_COOKIE}


# --- TC-USERS-021 ---------------------------------------------------------
def test_me_is_404_when_the_profile_row_is_gone(client, db, auth):
    client.cookies.set(ACCESS_COOKIE, "access-token")
    auth.auth.get_user.return_value = SimpleNamespace(user=fake_user())
    on_select(db, [])

    response = client.get("/users/me")

    assert response.status_code == 404


# --- TC-USERS-023 ---------------------------------------------------------
def test_validation_errors_arrive_in_the_same_shape_as_every_other_error(client, db):
    on_select(db, [])

    response = client.post(
        "/users/signup", json={**SIGNUP, "email": "not-an-email", "password": "short"}
    )

    assert response.status_code == 422
    body = response.json()
    # A sentence, not FastAPI's list of objects: the caller reads `detail` the
    # same way whatever went wrong.
    assert isinstance(body["detail"], str)
    # And the per-field messages a form can put next to its inputs.
    assert set(body["errors"]) == {"email", "password"}


# --- TC-USERS-024 ---------------------------------------------------------
@pytest.mark.parametrize(
    "requested_role",
    ["event_coordinator", "venue_staff", "technical_support", "attendee"],
)
def test_signup_cannot_choose_an_internal_role(client, db, auth, requested_role):
    response = client.post(
        "/users/signup",
        json={**SIGNUP, "role": requested_role},
    )

    assert response.status_code == 422
    assert "role" in response.json()["errors"]
    auth.auth.sign_up.assert_not_called()
    db.auth.admin.update_user_by_id.assert_not_called()


# --- TC-USERS-025 ---------------------------------------------------------
def test_signup_removes_account_when_trusted_role_assignment_fails(client, db, auth):
    on_select(db, [])
    auth.auth.sign_up.return_value = SimpleNamespace(
        user=fake_user(), session=fake_session()
    )
    db.auth.admin.update_user_by_id.side_effect = RuntimeError("admin update failed")

    response = client.post("/users/signup", json=SIGNUP)

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not configure user account"
    db.auth.admin.delete_user.assert_called_once_with(USER_ID)
    db.schema.return_value.table.return_value.insert.assert_not_called()
