# Test cases — users service (unit)

Covers `tests/unit/atomic/users/test_app.py`: the auth endpoints of the users
service with Supabase faked in both of its roles, the table client and the auth
client.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/users` |
| Last run | 2026-09-12, working tree of branch `user-auth` |
| Environment | Python 3.12.5, pytest 9.1.1, fastapi 0.141.1, supabase-py 2.31.0. No network, no database, no Docker. |
| Result | 23 passed |

A pass here is only a pass as of that build, and it says nothing about whether
the `users` schema is exposed or granted — the fake agrees with everything.
That is what [`../../../integration/atomic/users/TEST_CASES.md`](../../../integration/atomic/users/TEST_CASES.md)
is for.

**Shared pre-conditions.** Every case below starts from: the FastAPI app built
with `get_db` and `get_auth` overridden by `MagicMock`s, no cookies in the
client, and the environment variables `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
`SUPABASE_ANON_KEY` set to dummy values by `conftest.py`. Anything else a case
needs is listed under its own pre-conditions.

**Shared test data.**

```
id       11111111-1111-4111-8111-111111111111
name     Ada Lovelace
email    ada@example.com
password correct-horse-battery
profile  {"id": <id>, "name": "Ada Lovelace", "email": "ada@example.com",
          "created_at": "2026-09-12T00:00:00Z"}
```

---

## TC-USERS-001 — health check answers

- **Scenario:** The service reports itself up.
- **Pre-conditions:** Shared.
- **Steps:** 1. `GET /health`.
- **Test data:** None.
- **Expected:** `200`, body exactly `{"status": "ok"}`.
- **Actual:** `200`, `{"status": "ok"}`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_health_reports_ok`

## TC-USERS-002 — sign-up creates the account and its profile

- **Scenario:** A new address gets a Supabase Auth account, a row in
  `users.users`, and a session in cookies.
- **Pre-conditions:** The profile lookup returns `[]`; the insert returns the
  shared profile; `sign_up` returns a user and a session
  (`access_token="access-token"`, `refresh_token="refresh-token"`).
- **Steps:**
  1. `POST /users/signup` with the payload below.
  2. Read the response body, the `Set-Cookie` headers, and the arguments the
     fakes were called with.
- **Test data:** `{"name": "Ada Lovelace", "email": "ada@example.com", "password": "correct-horse-battery"}`
- **Expected:** `201`; body exactly
  `{"id": "1111...1111", "name": "Ada Lovelace", "email": "ada@example.com"}`;
  `sign_up` called with `{"email": "ada@example.com", "password": "correct-horse-battery"}`;
  the insert called with `{"id": <auth user id>, "name": ..., "email": ...}` —
  the profile takes the auth id, it does not mint its own; two cookies,
  `sb_access_token` and `sb_refresh_token`, each `HttpOnly`, `SameSite=lax`,
  `Path=/`; no token anywhere in the body.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_creates_account_and_profile`

## TC-USERS-003 — sign-up refuses an address that already has a profile

- **Scenario:** The duplicate is caught here, before an account is made.
- **Pre-conditions:** The profile lookup returns `[{"id": <id>}]`.
- **Steps:** 1. `POST /users/signup` with the shared payload.
- **Test data:** `{"name": "Ada Lovelace", "email": "ada@example.com", "password": "correct-horse-battery"}`
- **Expected:** `409`, `detail` exactly `"Email already registered"`, and
  `sign_up` never called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_rejects_email_that_already_has_a_profile`

## TC-USERS-004 — sign-up requires a name

- **Scenario:** A missing required field is rejected by validation.
- **Pre-conditions:** Shared.
- **Steps:** 1. `POST /users/signup` with no `name`.
- **Test data:** `{"email": "ada@example.com", "password": "correct-horse-battery"}`
- **Expected:** `422`.
- **Actual:** `422`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_requires_a_name`

## TC-USERS-005 — sign-up rejects a malformed address

- **Scenario:** Format checking happens on the server, not only in the form.
- **Pre-conditions:** Shared.
- **Steps:** 1. `POST /users/signup` with an address that is not one.
- **Test data:** `{"name": "Ada Lovelace", "email": "not-an-email", "password": "correct-horse-battery"}`
- **Expected:** `422`.
- **Actual:** `422`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_rejects_a_malformed_email`

## TC-USERS-006 — sign-up rejects a password under 8 characters

- **Scenario:** The length rule is enforced before Supabase is called.
- **Pre-conditions:** Shared.
- **Steps:** 1. `POST /users/signup` with a five-character password.
- **Test data:** `{"name": "Ada Lovelace", "email": "ada@example.com", "password": "short"}`
- **Expected:** `422`.
- **Actual:** `422`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_rejects_a_short_password`

## TC-USERS-007 — a duplicate only Supabase knows about is still a 409

- **Scenario:** The profile row is gone but the account survives, so the
  duplicate surfaces from upstream instead of from the table.
- **Pre-conditions:** The profile lookup returns `[]`; `sign_up` raises
  `AuthApiError("User already registered", 422)`.
- **Steps:** 1. `POST /users/signup` with the shared payload.
- **Test data:** As TC-USERS-002.
- **Expected:** `409`, `detail` exactly `"Email already registered"` — the same
  answer as TC-USERS-003, so the caller cannot tell the two apart.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_maps_an_upstream_duplicate_to_409`

## TC-USERS-008 — a failed profile insert takes the account with it

- **Scenario:** Sign-up must not leave an account with no profile: the retry
  would come back as a duplicate and the address would be stuck for good.
- **Pre-conditions:** The profile lookup returns `[]`; `sign_up` succeeds with a
  user and session; the insert raises `RuntimeError("insert failed")`.
- **Steps:** 1. `POST /users/signup` with the shared payload.
- **Test data:** As TC-USERS-002.
- **Expected:** `500`; `auth.admin.delete_user` called once with the new user's
  id; no cookies set.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_undoes_the_account_when_the_profile_cannot_be_written`

## TC-USERS-009 — sign-up sets no cookies when the address needs confirming

- **Scenario:** With email confirmation on in Supabase, the account exists but
  nobody is signed in yet.
- **Pre-conditions:** The profile lookup returns `[]`; the insert returns the
  profile; `sign_up` returns a user and `session=None`.
- **Steps:** 1. `POST /users/signup` with the shared payload.
- **Test data:** As TC-USERS-002.
- **Expected:** `201` with the profile, and no `Set-Cookie` headers at all.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_sets_no_cookies_when_the_email_needs_confirming`

## TC-USERS-010 — sign-up normalises the address

- **Scenario:** Case and surrounding spaces must not create a second account.
- **Pre-conditions:** As TC-USERS-002.
- **Steps:** 1. `POST /users/signup` with a padded, mixed-case address.
- **Test data:** `email` of `"  Ada@Example.COM  "`, rest as TC-USERS-002.
- **Expected:** `201`; the duplicate check queries `eq("email", "ada@example.com")`
  and `sign_up` is called with `"ada@example.com"` — one casing in, one casing
  stored.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_normalises_the_email`

## TC-USERS-011 — login returns the profile and sets the session

- **Scenario:** Correct credentials produce a session in cookies.
- **Pre-conditions:** `sign_in_with_password` returns the shared user and a
  session; the profile lookup returns the shared profile.
- **Steps:** 1. `POST /users/login`. 2. Read the body and the `Set-Cookie` headers.
- **Test data:** `{"email": "ada@example.com", "password": "correct-horse-battery"}`
- **Expected:** `200`; body exactly the three profile fields; both session
  cookies set; no token in the body.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_login_returns_the_profile_and_sets_cookies`

## TC-USERS-012 — a wrong password is a 401 that says nothing

- **Scenario:** Bad credentials are refused without hinting at which half.
- **Pre-conditions:** `sign_in_with_password` raises
  `AuthApiError("Invalid login credentials", 400)`.
- **Steps:** 1. `POST /users/login` with the wrong password.
- **Test data:** `{"email": "ada@example.com", "password": "correct-horse-battery"}`
- **Expected:** `401`, `detail` exactly `"Invalid email or password"`, no
  cookies set, and no upstream message passed through.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_login_rejects_a_wrong_password_without_saying_so`

## TC-USERS-013 — an unknown address is answered identically

- **Scenario:** The login form cannot be used to discover which addresses have
  accounts.
- **Pre-conditions:** As TC-USERS-012.
- **Steps:** 1. `POST /users/login` with an address that has no account.
- **Test data:** `{"email": "nobody@example.com", "password": "correct-horse-battery"}`
- **Expected:** `401` and `detail` exactly `"Invalid email or password"` —
  byte-for-byte what TC-USERS-012 returns.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_login_answers_an_unknown_email_exactly_the_same_way`

## TC-USERS-014 — login requires a password

- **Scenario:** A missing field is a validation error, not an auth attempt.
- **Pre-conditions:** Shared.
- **Steps:** 1. `POST /users/login` with only an address.
- **Test data:** `{"email": "ada@example.com"}`
- **Expected:** `422`.
- **Actual:** `422`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_login_requires_a_password`

## TC-USERS-015 — an upstream rate limit is passed on as 429

- **Scenario:** Supabase throttling the address is not a credentials failure and
  should not read like one.
- **Pre-conditions:** `sign_in_with_password` raises
  `AuthApiError("Request rate limit reached", 429)`.
- **Steps:** 1. `POST /users/login`.
- **Test data:** As TC-USERS-011.
- **Expected:** `429`.
- **Actual:** `429`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_login_passes_on_a_rate_limit`

## TC-USERS-016 — logout clears the cookies and revokes the token

- **Scenario:** Logging out ends the session in this browser and everywhere the
  refresh token could be replayed.
- **Pre-conditions:** The client holds `sb_access_token=access-token` and
  `sb_refresh_token=refresh-token`.
- **Steps:** 1. `POST /users/logout`. 2. Read the `Set-Cookie` headers and the
  calls made on the admin client.
- **Test data:** The two cookies above.
- **Expected:** `204`; both cookies handed back already expired (`Max-Age=0` or
  a 1970 date); `auth.admin.sign_out` called once with `"access-token"`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_logout_clears_the_cookies`

## TC-USERS-017 — `/users/me` returns the signed-in user

- **Scenario:** The route guard every page load depends on.
- **Pre-conditions:** The client holds `sb_access_token=access-token`;
  `get_user` returns the shared user; the profile lookup returns the profile.
- **Steps:** 1. `GET /users/me`.
- **Test data:** The access cookie above.
- **Expected:** `200`; body exactly the three profile fields; `get_user` called
  once with `"access-token"` — the token comes from the cookie, never from a
  session stored on the shared client.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_me_returns_the_signed_in_user`

## TC-USERS-018 — `/users/me` with no cookies is a 401

- **Scenario:** A signed-out visitor is told so, cheaply.
- **Pre-conditions:** Shared — no cookies.
- **Steps:** 1. `GET /users/me`.
- **Test data:** None.
- **Expected:** `401`, `detail` `"Not authenticated"`, and Supabase never
  called.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_me_is_401_with_no_cookies`

## TC-USERS-019 — an expired access token is refreshed, not rejected

- **Scenario:** The access token lasts an hour; an older tab must not be logged
  out while its refresh token is still good.
- **Pre-conditions:** The client holds both cookies; `get_user` raises
  `AuthApiError("token is expired", 401)`; `refresh_session` returns a new
  session (`new-access`, `new-refresh`); the profile lookup returns the profile.
- **Steps:** 1. `GET /users/me`. 2. Read the `Set-Cookie` headers.
- **Test data:** `sb_access_token=expired-token`, `sb_refresh_token=refresh-token`.
- **Expected:** `200`; `refresh_session` called once with `"refresh-token"`;
  the response carries the renewed pair — `new-access` in `sb_access_token`,
  `new-refresh` in `sb_refresh_token`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_me_refreshes_an_expired_access_token`

## TC-USERS-020 — dead cookies are taken back on a 401

- **Scenario:** When neither token works, the browser should stop sending them.
- **Pre-conditions:** The client holds both cookies; `get_user` and
  `refresh_session` both raise `AuthApiError(..., 401)`.
- **Steps:** 1. `GET /users/me`. 2. Read the `Set-Cookie` headers.
- **Test data:** `sb_access_token=expired-token`, `sb_refresh_token=revoked-token`.
- **Expected:** `401`, and both cookies expired on the way out. (Raising throws
  away the response a dependency was given, so this only works because of the
  exception handler in `app.py` — the case exists to keep that wired up.)
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_me_clears_cookies_when_neither_token_works`

## TC-USERS-021 — a valid session with no profile row is a 404

- **Scenario:** The account is fine but the profile has been deleted.
- **Pre-conditions:** The client holds a valid access cookie; `get_user` returns
  the user; the profile lookup returns `[]`.
- **Steps:** 1. `GET /users/me`.
- **Test data:** `sb_access_token=access-token`.
- **Expected:** `404` — a missing row is not an empty `200`.
- **Actual:** `404`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_me_is_404_when_the_profile_row_is_gone`

## TC-USERS-022 — logout works when there was no session

- **Scenario:** A logout from a browser with no cookies is not an error.
- **Pre-conditions:** Shared — no cookies.
- **Steps:** 1. `POST /users/logout`.
- **Test data:** None.
- **Expected:** `204`, and `auth.admin.sign_out` never called — there is no
  token to revoke.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_logout_works_without_a_session`

## TC-USERS-023 — validation errors match the shape of every other error

- **Scenario:** A frontend reads `detail` the same way whatever went wrong, and
  gets per-field messages it can put next to the inputs.
- **Pre-conditions:** Shared.
- **Steps:** 1. `POST /users/signup` with two fields wrong at once.
- **Test data:** `{"name": "Ada Lovelace", "email": "not-an-email", "password": "short"}`
- **Expected:** `422`; `detail` is a **string**, not FastAPI's list of error
  objects; `errors` holds one entry per bad field — exactly `email` and
  `password`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_validation_errors_arrive_in_the_same_shape_as_every_other_error`
