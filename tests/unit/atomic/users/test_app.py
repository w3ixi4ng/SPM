"""Unit tests for the users service -- see TEST_CASES.md.

Supabase is faked, so these prove the service's own behaviour: what it accepts,
what status it returns, and what it puts in the session cookies. They cannot
prove the schema is exposed or the grants are right; that is what the
integration tests are for.
"""

from types import SimpleNamespace

import httpx
import pytest

from .conftest import (
    EMAIL,
    NAME,
    PROFILE,
    USER_ID,
    auth_admin_user,
    auth_error,
    fake_session,
    fake_user,
    on_in,
    on_insert,
    on_select,
)

ACCESS_COOKIE = "sb_access_token"
REFRESH_COOKIE = "sb_refresh_token"

SIGNUP = {
    "name": NAME,
    "email": EMAIL,
    "password": "correct-horse-battery",
    "role": "event_organiser",
}
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


def test_me_retries_a_dropped_connection_on_the_profile_read(client, db, auth):
    client.cookies.set(ACCESS_COOKIE, "access-token")
    auth.auth.get_user.return_value = SimpleNamespace(user=fake_user())
    execute = db.schema.return_value.table.return_value.select.return_value.eq.return_value.execute
    execute.side_effect = [httpx.RemoteProtocolError("connection terminated"), SimpleNamespace(data=[PROFILE])]

    response = client.get("/users/me")

    assert response.status_code == 200
    assert response.json()["id"] == USER_ID
    assert execute.call_count == 2


def test_me_reports_upstream_failure_after_two_dropped_reads(client, db, auth):
    client.cookies.set(ACCESS_COOKIE, "access-token")
    auth.auth.get_user.return_value = SimpleNamespace(user=fake_user())
    execute = db.schema.return_value.table.return_value.select.return_value.eq.return_value.execute
    execute.side_effect = httpx.RemoteProtocolError("connection terminated")

    response = client.get("/users/me")

    assert response.status_code == 502
    assert response.json()["detail"] == "User profile service unavailable"
    assert execute.call_count == 2


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


@pytest.fixture
def no_retry_pause(client, monkeypatch):
    """Retries without the real pauses. Patched on the module the route's
    dependency actually lives in, whatever else is called `security`."""
    from app import app

    route = next(r for r in app.routes if getattr(r, "path", None) == "/users/me")
    check = next(
        dep.call for dep in route.dependant.dependencies if dep.call.__name__ == "get_current_user"
    )
    monkeypatch.setitem(check.__globals__, "AUTH_RETRY_DELAYS", (0, 0))


# --- TC-USERS-035 ---------------------------------------------------------
def test_me_rejected_token_is_401_without_retrying(client, auth, no_retry_pause):
    client.cookies.set(ACCESS_COOKIE, "revoked-token")
    auth.auth.get_user.side_effect = auth_error("invalid JWT", 403)

    response = client.get("/users/me")

    assert response.status_code == 401
    assert auth.auth.get_user.call_count == 1
    assert set(set_cookies(response)) == {ACCESS_COOKIE, REFRESH_COOKIE}


# --- TC-USERS-036 ---------------------------------------------------------
@pytest.mark.parametrize(
    "blip",
    [httpx.RemoteProtocolError("Server disconnected"), httpx.ReadTimeout("timed out")],
    ids=["dropped", "timeout"],
)
def test_me_retries_a_session_check_that_got_no_answer(client, db, auth, no_retry_pause, blip):
    client.cookies.set(ACCESS_COOKIE, "access-token")
    auth.auth.get_user.side_effect = [blip, SimpleNamespace(user=fake_user())]
    on_select(db, [PROFILE])

    response = client.get("/users/me")

    assert response.status_code == 200
    assert response.json()["id"] == USER_ID
    assert auth.auth.get_user.call_count == 2


# --- TC-USERS-037 ---------------------------------------------------------
@pytest.mark.parametrize(
    "failure",
    [
        httpx.RemoteProtocolError("Server disconnected"),
        auth_error("upstream error", 500),
        auth_error("rate limit", 429),
    ],
    ids=["dropped", "500", "429"],
)
def test_me_is_503_and_keeps_the_cookies_when_auth_never_answers(
    client, auth, no_retry_pause, failure
):
    client.cookies.set(ACCESS_COOKIE, "access-token")
    client.cookies.set(REFRESH_COOKIE, "refresh-token")
    auth.auth.get_user.side_effect = failure

    response = client.get("/users/me")

    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication service unavailable"
    assert auth.auth.get_user.call_count == 3
    # No verdict on the token is not a logout.
    auth.auth.refresh_session.assert_not_called()
    assert set_cookies(response) == {}


# --- TC-USERS-038 ---------------------------------------------------------
def test_me_retries_a_refresh_that_got_no_answer(client, db, auth, no_retry_pause):
    client.cookies.set(ACCESS_COOKIE, "expired-token")
    client.cookies.set(REFRESH_COOKIE, "refresh-token")
    auth.auth.get_user.side_effect = auth_error("token is expired", 401)
    auth.auth.refresh_session.side_effect = [
        httpx.RemoteProtocolError("Server disconnected"),
        SimpleNamespace(user=fake_user(), session=fake_session("new-access", "new-refresh")),
    ]
    on_select(db, [PROFILE])

    response = client.get("/users/me")

    assert response.status_code == 200
    assert auth.auth.refresh_session.call_count == 2
    assert "new-access" in set_cookies(response)[ACCESS_COOKIE]


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
    ["event_coordinator", "venue_staff", "technical_support"],
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


# --- TC-USERS-027 ---------------------------------------------------------
def test_coordinator_listing_returns_only_that_role(client, db):
    coordinator_1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    coordinator_2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    db.auth.admin.list_users.return_value = [
        auth_admin_user(coordinator_1, "event_coordinator"),
        auth_admin_user(coordinator_2, "event_coordinator"),
        auth_admin_user("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "event_organiser"),
        auth_admin_user("dddddddd-dddd-4ddd-8ddd-dddddddddddd", None),
    ]
    coordinator_profiles = [
        {"id": coordinator_1, "name": "Grace Hopper", "email": "grace@example.com"},
        {"id": coordinator_2, "name": "Ada Lovelace", "email": "ada2@example.com"},
    ]
    on_in(db, coordinator_profiles)

    response = client.get("/internal/users/coordinators")

    assert response.status_code == 200
    assert response.json() == [
        {**profile, "coordinator_active": True} for profile in coordinator_profiles
    ]
    queried_ids = set(
        db.schema.return_value.table.return_value.select.return_value.in_.call_args[0][1]
    )
    assert queried_ids == {coordinator_1, coordinator_2}


def test_coordinator_availability_uses_only_boolean_auth_app_metadata(client, db):
    ids = [
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    ]
    users = [auth_admin_user(uid, "event_coordinator") for uid in ids]
    users[1].app_metadata["coordinator_active"] = True
    users[2].app_metadata["coordinator_active"] = False
    users[2].user_metadata["coordinator_active"] = True
    users[3].app_metadata["coordinator_active"] = "false"
    db.auth.admin.list_users.return_value = users
    on_in(db, [{"id": uid, "name": f"Coordinator {number}", "email": f"c{number}@example.com"} for number, uid in enumerate(ids)])
    response = client.get("/internal/users/coordinators")
    assert response.status_code == 200
    assert [item["coordinator_active"] for item in response.json()] == [True, True, False, None]
    assert all("password" not in item and "access_token" not in item for item in response.json())


# --- TC-USERS-028 ---------------------------------------------------------
def test_coordinator_listing_is_empty_when_no_one_holds_the_role(client, db):
    db.auth.admin.list_users.return_value = [
        auth_admin_user("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "event_organiser"),
    ]

    response = client.get("/internal/users/coordinators")

    assert response.status_code == 200
    assert response.json() == []
    db.schema.return_value.table.return_value.select.assert_not_called()


# --- TC-USERS-032 ---------------------------------------------------------
def test_coordinator_listing_keeps_trusted_auth_users_without_profiles(client, db):
    profiled = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    profileless = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    db.auth.admin.list_users.return_value = [
        auth_admin_user(profiled, "event_coordinator", "auth-alex@example.com"),
        auth_admin_user(profileless, "event_coordinator", "idle@example.com"),
        auth_admin_user("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "event_organiser"),
        auth_admin_user("dddddddd-dddd-4ddd-8ddd-dddddddddddd", "technical_support"),
        auth_admin_user("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "safety_officer"),
        auth_admin_user("ffffffff-ffff-4fff-8fff-ffffffffffff", "event_coordinator_lead"),
        auth_admin_user(
            "99999999-9999-4999-8999-999999999999",
            None,
            "impostor@example.com",
            {"role": "event_coordinator"},
        ),
    ]
    on_in(db, [{"id": profiled, "name": "Alex", "email": "alex@example.com"}])

    response = client.get("/internal/users/coordinators")

    assert response.status_code == 200
    assert response.json() == [
        {"id": profiled, "name": "Alex", "email": "alex@example.com", "coordinator_active": True},
        {"id": profileless, "name": "idle@example.com", "email": "idle@example.com", "coordinator_active": True},
    ]
    selected_ids = db.schema.return_value.table.return_value.select.return_value.in_.call_args.args[1]
    assert set(selected_ids) == {profiled, profileless}


def test_coordinator_listing_includes_profileless_auth_user_on_later_page(client, db):
    profiled = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    profileless = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    first_page = [auth_admin_user(profiled, "event_coordinator", "alex@example.com")]
    first_page.extend(
        auth_admin_user(f"irrelevant-{number}", "event_organiser")
        for number in range(199)
    )
    db.auth.admin.list_users.side_effect = [
        first_page,
        [auth_admin_user(profileless, "event_coordinator", "idle@example.com")],
    ]
    on_in(db, [{"id": profiled, "name": "Alex", "email": "alex@example.com"}])

    response = client.get("/internal/users/coordinators")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [profiled, profileless]
    assert response.json()[1]["name"] == "idle@example.com"
    assert db.auth.admin.list_users.call_count == 2


# --- TC-USERS-029 ---------------------------------------------------------
def test_technical_support_listing_uses_trusted_roles_across_pages(client, db):
    support_1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    support_2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    first_page = [auth_admin_user(support_1, "technical_support")]
    first_page.extend(
        auth_admin_user(f"{number:08x}-0000-4000-8000-000000000000", "event_organiser")
        for number in range(199)
    )
    db.auth.admin.list_users.side_effect = [
        first_page,
        [
            auth_admin_user(support_2, "technical_support"),
            auth_admin_user("cccccccc-cccc-4ccc-8ccc-cccccccccccc", None),
        ],
    ]
    profiles = [
        {"id": support_1, "name": "Support One", "email": "one@example.com"},
        {"id": support_2, "name": "Support Two", "email": "two@example.com"},
    ]
    on_in(db, profiles)

    response = client.get("/users/technical-support")

    assert response.status_code == 200
    assert response.json() == profiles
    queried_ids = db.schema.return_value.table.return_value.select.return_value.in_.call_args.args[1]
    assert queried_ids == [support_1, support_2]
    assert db.auth.admin.list_users.call_count == 2


# --- TC-USERS-030 ---------------------------------------------------------
def test_technical_support_listing_is_empty_when_no_one_holds_the_role(client, db):
    db.auth.admin.list_users.return_value = [
        auth_admin_user("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "event_coordinator")
    ]

    response = client.get("/users/technical-support")

    assert response.status_code == 200
    assert response.json() == []
    db.schema.return_value.table.return_value.select.assert_not_called()


# --- TC-USERS-031 ---------------------------------------------------------
def test_internal_profile_lookup_returns_known_unique_profiles(client, db):
    second_id = "22222222-2222-4222-8222-222222222222"
    unknown_id = "99999999-9999-4999-8999-999999999999"
    profiles = [
        {"id": USER_ID, "name": NAME, "email": EMAIL},
        {"id": second_id, "name": "Grace Hopper", "email": "grace@example.com"},
    ]
    on_in(db, profiles)

    response = client.post(
        "/internal/users/profiles",
        json={"ids": [USER_ID, second_id, USER_ID, unknown_id]},
    )

    assert response.status_code == 200
    assert response.json() == profiles
    select = db.schema.return_value.table.return_value.select
    select.assert_called_once_with("id,name,email")
    assert select.return_value.in_.call_args.args == (
        "id",
        [USER_ID, second_id, unknown_id],
    )


def test_internal_profile_lookup_empty_input_skips_storage(client, db):
    response = client.post("/internal/users/profiles", json={"ids": []})
    assert response.status_code == 200
    assert response.json() == []
    db.schema.assert_not_called()


# --- TC-USERS-039, TC-USERS-040 -------------------------------------------
@pytest.mark.parametrize("role", ["attendee", "event_organiser"])
def test_signup_stamps_the_role_that_was_chosen(client, db, auth, role):
    on_select(db, [])
    on_insert(db, [PROFILE])
    auth.auth.sign_up.return_value = SimpleNamespace(
        user=fake_user(), session=fake_session()
    )

    response = client.post("/users/signup", json={**SIGNUP, "role": role})

    assert response.status_code == 201
    assert response.json() == {"id": USER_ID, "name": NAME, "email": EMAIL}
    db.auth.admin.update_user_by_id.assert_called_once_with(
        USER_ID, {"app_metadata": {"role": role}}
    )
    # The role lives in trusted Auth metadata only, never in the profile.
    db.schema.return_value.table.return_value.insert.assert_called_once_with(
        {"id": USER_ID, "name": NAME, "email": EMAIL}
    )


# --- TC-USERS-041 ---------------------------------------------------------
@pytest.mark.parametrize("role", ["omitted", None, ""])
def test_signup_without_a_role_is_rejected(client, db, auth, role):
    body = {k: v for k, v in SIGNUP.items() if k != "role"}
    if role != "omitted":
        body["role"] = role

    response = client.post("/users/signup", json=body)

    assert response.status_code == 422
    assert "role" in response.json()["errors"]
    auth.auth.sign_up.assert_not_called()
    db.auth.admin.update_user_by_id.assert_not_called()


# --- TC-USERS-042 ---------------------------------------------------------
@pytest.mark.parametrize(
    "role",
    [
        "event_coordinator",
        "event_coordinator_lead",
        "venue_staff",
        "technical_support",
        "safety_officer",
        "admin",
        "Attendee",
        ["attendee", "event_organiser"],
    ],
)
def test_signup_cannot_choose_any_role_but_the_two_public_ones(client, db, auth, role):
    response = client.post("/users/signup", json={**SIGNUP, "role": role})

    assert response.status_code == 422
    assert "role" in response.json()["errors"]
    auth.auth.sign_up.assert_not_called()
    db.auth.admin.update_user_by_id.assert_not_called()
