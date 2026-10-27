# Test cases — users service (unit)

Covers `tests/unit/atomic/users/test_app.py`: the auth endpoints of the users
service with Supabase faked in both of its roles, the table client and the auth
client.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/users` |
| Last run | 2026-10-27, CI on S-93 commit `17f60bc` |
| Environment | Python 3.14.8, pytest 9.1.1; mocked Supabase; no network, database or Docker. |
| Result | 40 passed in this folder; 1,505 passed, 17 skipped across Python unit. |

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
  the trusted Auth app metadata is updated server-side to
  `{"role": "event_organiser"}`;
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
- **Steps:** 1. `GET /users/me`. 2. Repeat with the first profile read raising a dropped-connection error. 3. Repeat with both profile reads raising that error.
- **Test data:** The access cookie above; `httpx.RemoteProtocolError("connection terminated")` on one or both profile reads.
- **Expected:** `200`; body contains the three profile fields and trusted role; `get_user` called
  once with `"access-token"` — the token comes from the cookie, never from a
  session stored on the shared client. A dropped connection on the idempotent
  profile read is retried once and returns `200` if the retry succeeds. If both
  reads fail, return `502` without changing or clearing the session.
- **Actual:** The normal read and one-retry read returned `200`; two dropped reads returned `502` after exactly two attempts.
- **Status:** Pass
- **Evidence:** `test_app.py::test_me_returns_the_signed_in_user`, `test_me_retries_a_dropped_connection_on_the_profile_read`, `test_me_reports_upstream_failure_after_two_dropped_reads`

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

## TC-USERS-024 — public signup cannot choose an internal role

- **Scenario:** A caller cannot promote itself through the public signup body.
- **Pre-conditions:** Shared.
- **Steps:** Submit the normal signup payload with each internal/non-public role
  added as a `role` field.
- **Test data:** `event_coordinator`, `venue_staff`, `technical_support`, and
  `attendee`.
- **Expected:** Every request returns `422`; Supabase signup and admin role
  assignment are never called.
- **Actual:** As expected for all four roles.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_cannot_choose_an_internal_role`

## TC-USERS-025 — failed trusted-role assignment is rolled back

- **Scenario:** Signup does not leave an account without its required public role.
- **Pre-conditions:** Supabase Auth creates the user, then the trusted admin
  metadata update raises.
- **Steps:** `POST /users/signup` with the shared payload.
- **Test data:** Shared signup payload.
- **Expected:** `500` with `Could not configure user account`; the new Auth user
  is deleted and no profile insert is attempted.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_removes_account_when_trusted_role_assignment_fails`

## TC-USERS-026 — `/users/me` safely reports a missing trusted role

- **Scenario:** An authenticated legacy account without `app_metadata.role`
  does not acquire a role from another source.
- **Pre-conditions:** A valid session resolves to a user with empty app metadata;
  its profile row exists.
- **Steps:** 1. `GET /users/me`. 2. Inspect the response role.
- **Test data:** The standard profile and no trusted role.
- **Expected:** `200` with `role: null`.
- **Actual:** `200` with `role: null`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_me_returns_no_role_when_trusted_role_is_missing`

## TC-USERS-027 — coordinator listing returns only that role

- **Scenario:** The `event_requests` composite needs the id, name, and email
  of every account whose trusted role is `event_coordinator`, to check their
  schedules and pick one.
- **Pre-conditions:** The Auth admin listing returns four users: two with
  `app_metadata.role="event_coordinator"`, one `event_organiser`, one with no
  role; the profile table holds a row for each.
- **Steps:** `GET /internal/users/coordinators`.
- **Test data:** As above.
- **Expected:** `200`; response contains exactly the two coordinators' `id`,
  `name`, `email` — no password, role, or other field; the other two accounts
  are absent.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_listing_returns_only_that_role`

## TC-USERS-028 — coordinator listing is empty when no one holds the role

- **Scenario:** A fresh deployment with no coordinators yet returns an empty
  list, not an error — the composite treats this the same as everyone being
  busy.
- **Pre-conditions:** The Auth admin listing returns no user with that role.
- **Steps:** `GET /internal/users/coordinators`.
- **Test data:** None.
- **Expected:** `200`, `[]`.
- **Actual:** As expected.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_listing_is_empty_when_no_one_holds_the_role`

---

## S-43 — Auto-Assign Technical Support

## TC-USERS-029 — Technical Support listing trusts only Auth app metadata

- **Scenario:** The assignment composite receives only eligible Technical
  Support Staff profiles.
- **Pre-conditions:** Paginated Auth admin results contain two users with
  `app_metadata.role="technical_support"`, plus Coordinator, Organiser, and
  role-less users; profile rows exist for all of them.
- **Steps:** `GET /users/technical-support`.
- **Test data:** The five accounts above, split across two Auth pages.
- **Expected:** `200`; exactly the two Technical Support profiles are returned
  with id, name, and email. Neither profile data nor user-editable metadata can
  grant eligibility, and no secret Auth fields are returned.
- **Actual:** Only the two trusted Technical Support profiles were returned across the paginated Auth result.
- **Status:** Pass
- **Evidence:** `test_app.py::test_technical_support_listing_uses_trusted_roles_across_pages`

## TC-USERS-030 — an empty Technical Support pool is a valid result

- **Scenario:** A deployment with no eligible Technical Support account does
  not turn the users lookup itself into an error.
- **Pre-conditions:** Auth contains no user whose trusted role is
  `technical_support`.
- **Steps:** `GET /users/technical-support`.
- **Expected:** `200`, `[]`; no profile-table query is issued.
- **Actual:** `200`, `[]`, with no profile-table query.
- **Status:** Pass
- **Evidence:** `test_app.py::test_technical_support_listing_is_empty_when_no_one_holds_the_role`

## TC-USERS-031 — internal profile lookup resolves queue organisers without exposing roles

- **Scenario:** The S-83 composite can display organisers while the users
  service remains the sole owner of profiles.
- **Pre-conditions:** Profiles exist for ids A and B; an unknown id is also
  requested.
- **Steps:** `POST /internal/users/profiles` with all three ids, including A twice.
- **Test data:** A `11111111-1111-4111-8111-111111111111`; B
  `22222222-2222-4222-8222-222222222222`; unknown
  `99999999-9999-4999-8999-999999999999`.
- **Expected:** `200` with A and B once each, containing only id, name, and
  email; the unknown id is absent. An empty input returns `200 []` without a
  database call, and an oversized/invalid body returns `422`.
- **Actual:** Known ids were returned once with profile fields only; empty input returned `[]` without storage access.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_profile_lookup_returns_known_unique_profiles`

## TC-USERS-032 — Coordinator pool includes trusted Auth users without profiles

- **Scenario:** Coordinator eligibility comes only from trusted Auth app metadata, while profile data is optional display enrichment.
- **Pre-conditions:** Auth returns a profiled Coordinator A, a profile-less Coordinator B, and users with `event_organiser`, `technical_support`, `safety_officer`, `event_coordinator_lead`, and missing trusted roles. B has an Auth email but no `users.users` row. One non-Coordinator has editable `user_metadata.role=event_coordinator`.
- **Steps:** Call `GET /internal/users/coordinators`; compare returned IDs and display fields with the Auth users and the available profile rows. Repeat with B on Auth page 2.
- **Test data:** A `alex@example.com` with profile name `Alex`; B `idle@example.com` without a profile; five non-Coordinator roles and one editable-role impostor.
- **Expected:** Exactly A and B are returned. A uses its profile name/email; B uses its Auth email as display name and email. No role is inferred from a profile, email, name, or editable `user_metadata`; no Auth secret or token is returned. The same complete pool remains usable by S-83 assignment and S-84 reassignment validation.
- **Actual:** The returned pool contained exactly the two trusted Coordinator IDs; the profiled name remained Alex and the missing-profile account displayed its Auth email, including when that account was on Auth page 2. Every other trusted role and the editable-metadata impostor was excluded.
- **Status:** Pass
- **Evidence:** `test_app.py::test_coordinator_listing_keeps_trusted_auth_users_without_profiles`, `test_app.py::test_coordinator_listing_includes_profileless_auth_user_on_later_page`; local Python 3.14 unit run, 2026-10-18.

## S-93 confirmed specification — trusted Coordinator availability

Drafted 2026-10-25 on `S-93/reassign-active-events-before-deactivation` at
`605e1e8` from `origin/sprint4`. Confirmed by developer on 2026-10-25.
The source of truth is
Supabase Auth `app_metadata.coordinator_active`. A missing key means active for
existing Coordinator accounts; explicit `false` means inactive. A malformed
value is unavailable for new assignment. Only an administrative operation may
change this trusted field; it preserves `app_metadata.role` and does not delete
the account or disable login.

## TC-USERS-033 — Coordinator status comes from trusted Auth metadata

- **Scenario:** The Users service exposes an authoritative active/inactive state without changing the trusted role.
- **Pre-conditions:** Fake Auth lists four users with `app_metadata.role=event_coordinator`: A has no status key, B has `coordinator_active=true`, C has `false`, and D has malformed `"false"`; all have profiles.
- **Steps:** 1. Request the internal Coordinator inventory. 2. Request the active assignment candidate list. 3. Repeat with C's editable `user_metadata.coordinator_active=true`.
- **Test data:** A `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`, B `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`, C `cccccccc-cccc-4ccc-8ccc-cccccccccccc`, D `dddddddd-dddd-4ddd-8ddd-dddddddddddd`.
- **Expected:** Inventory reports A and B active, C inactive, D unavailable; candidates contain only A and B. C's editable metadata cannot change the result. Each response retains the trusted Coordinator role and returns no Auth secret.
- **Actual:** Auth metadata gave true, true, false, and null; editable user metadata did not activate the inactive account; the composite candidate pool kept only the active users.
- **Status:** Pass
- **Evidence:** test_app.py::test_coordinator_availability_uses_only_boolean_auth_app_metadata; tests/unit/composite/event_requests/test_s93.py::test_candidate_pool_filters_inactive_and_malformed

## TC-USERS-034 — administrative status changes preserve role and account

- **Scenario:** Marking a Coordinator inactive changes assignment availability without deactivating authentication.
- **Pre-conditions:** Fake Auth user C has `app_metadata={"role":"event_coordinator","coordinator_active":true,"team":"operations"}` and a Users profile.
- **Steps:** 1. Apply an out-of-band Supabase Auth admin update to mark C inactive. 2. Read C again from Auth and Users. 3. Restore active status with the same admin capability.
- **Test data:** C `cccccccc-cccc-4ccc-8ccc-cccccccccccc`; active `true → false → true`.
- **Expected:** Both transitions persist a boolean and preserve `role` and `team`; C's profile and Auth account remain and login is not disabled. No new user-facing deactivation route is required by this case.
- **Actual:** Admin metadata updates persisted false then true, preserved role and team, and the inactive account still signed in; no account or profile was deleted.
- **Status:** Pass
- **Evidence:** tests/integration/atomic/users/test_app.py::test_coordinator_active_metadata_round_trip; tests/integration/composite/event_requests/test_s93.py::test_inactive_target_is_rejected_but_existing_work_can_be_transferred

## Session check: a rejected token vs no answer

`get_current_user` used to treat every error from Supabase Auth as a dead
session. A dropped connection, a timeout, a 5xx or a 429 then became a `401`
and cleared the browser's cookies, which signed working users out and failed
CI at random (e.g. S-88's concurrent submissions got `[401, 401]`). Only a 4xx
other than 429 is now a verdict on the token. Anything else is retried twice
(after 0.2 s and 0.5 s), then answers `503` and leaves the cookies alone.
The tests patch out the pauses.

## TC-USERS-035 — a rejected token is a 401 straight away

- **Scenario:** Supabase rejects the token, so the session check doesn't retry.
- **Pre-conditions:** `get_user` raises `AuthApiError` "invalid JWT", status 403; no refresh cookie.
- **Steps:** `GET /users/me` with `sb_access_token=revoked-token`.
- **Expected:** `401`; `get_user` called once; both session cookies cleared.
- **Actual:** `401`, one call, both cookies cleared.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/users/test_app.py::test_me_rejected_token_is_401_without_retrying; 2026-10-27, branch `update/auth-session` (on sprint4), pre-commit working tree

## TC-USERS-036 — a session check that got no answer is retried

- **Scenario:** A blip on the way to Supabase is not a logout.
- **Pre-conditions:** `get_user` first raises the error in the table, then returns the user; the profile row exists.
- **Steps:** `GET /users/me` with `sb_access_token=access-token`.
- **Test data / Expected:**
  | First attempt | Result |
  | --- | --- |
  | `httpx.RemoteProtocolError` "Server disconnected" | `200` with the profile; `get_user` called twice |
  | `httpx.ReadTimeout` | `200` with the profile; `get_user` called twice |
- **Actual:** Both `200` after two calls.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/users/test_app.py::test_me_retries_a_session_check_that_got_no_answer (2 params); 2026-10-27, branch `update/auth-session` (on sprint4), pre-commit working tree

## TC-USERS-037 — no answer at all is a 503, and the cookies stay

- **Scenario:** Supabase Auth is unreachable or overloaded, so the service says that instead of claiming the user is signed out.
- **Pre-conditions:** Every `get_user` call fails as in the table; both cookies are sent.
- **Steps:** `GET /users/me`.
- **Test data:** `httpx.RemoteProtocolError`; `AuthApiError` status 500; `AuthApiError` status 429.
- **Expected:** Each → `503` "Authentication service unavailable"; `get_user` called 3 times; `refresh_session` not called; no `Set-Cookie`.
- **Actual:** Each `503` after 3 calls, no refresh, no cookies set.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/users/test_app.py::test_me_is_503_and_keeps_the_cookies_when_auth_never_answers (3 params); 2026-10-27, branch `update/auth-session` (on sprint4), pre-commit working tree

## TC-USERS-038 — a refresh that got no answer is retried

- **Scenario:** The same applies to renewing an expired session.
- **Pre-conditions:** `get_user` raises `AuthApiError` "token is expired", 401. `refresh_session` first raises `httpx.RemoteProtocolError`, then returns a new session (`new-access` / `new-refresh`).
- **Steps:** `GET /users/me` with both cookies.
- **Expected:** `200`; `refresh_session` called twice; the response sets `sb_access_token=new-access`.
- **Actual:** `200`, two refresh calls, new access cookie set.
- **Status:** Pass
- **Evidence:** tests/unit/atomic/users/test_app.py::test_me_retries_a_refresh_that_got_no_answer; 2026-10-27, branch `update/auth-session` (on sprint4), pre-commit working tree
