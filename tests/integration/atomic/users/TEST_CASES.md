# Test cases — users service (integration)

Covers `tests/integration/atomic/users/test_app.py`: the real service in Docker
against a real **test** Supabase project. These are the only cases that can
prove the `users` schema is exposed, that the grants ran, and that the table is
where the code thinks it is.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait` then `pytest tests/integration/atomic/users` |
| Last run | 2026-09-14, working tree of branch `events-schema` |
| Environment | `.env.test` → test Supabase project, `users` schema applied and exposed, email confirmation off; users service in Docker on `localhost:8001` |
| Result | 4 passed |

These passed as of the working tree above, and a pass is only ever a pass as
of a build. They return to Blocked — not Failed — the moment they run against a
project where [`backend/sql/users.sql`](../../../../backend/sql/users.sql) has
not been applied or the `users` schema is not exposed. Blocked says "this has
not been proven here"; Failed would say "this was tried and the service is
wrong", which is a different and worse claim.

**Shared pre-conditions.** Every case needs all of:

1. `.env.test` filled in, pointing at the **test** Supabase project — never the
   one with real data. These tests create and delete accounts.
2. `backend/sql/users.sql` applied to that project.
3. `users` added under **Data API → Settings → Exposed schemas** in that
   project. Exposing without granting, or granting without exposing, leaves the
   service just as broken as doing neither.
4. `docker compose --env-file .env.test up -d --build --wait` green, so the
   `/health` check has passed.
5. For TC-USERS-101 only: **Authentication → Providers → Email → Confirm email**
   switched **off** in the test project, so sign-up returns a session. With it
   on, the case skips itself rather than failing, and says so.

**Shared test data.** Each run makes its own address,
`spm-test-<12 hex chars>@example.com`, with name `Ada Lovelace` and password
`correct-horse-battery-staple`. Every account created is deleted afterwards
whether the case passes or fails, so the suite can be run twice in a row.

---

## TC-USERS-101 — sign up, check the session, log out, log back in

- **Scenario:** One round trip through every endpoint, against the real
  database. If this passes, the schema, the grants, the exposure, the table
  location and the cookie handling are all confirmed at once.
- **Pre-conditions:** Shared, including item 5.
- **Steps:**
  1. `POST /users/signup` with a fresh address.
  2. Read `users.users` directly with the service_role key, by the returned id.
  3. Read the Auth user with the service-role admin client.
  4. Inspect the `Set-Cookie` headers on the sign-up response.
  5. `GET /users/me`, sending the cookies from step 1.
  6. `POST /users/logout` with the same cookies.
  7. `POST /users/login` with the same address and password.
  8. `GET /users/me` with the cookies from step 7.
  9. Delete the account and its row, in the fixture teardown.
- **Test data:** `{"name": "Ada Lovelace", "email": "spm-test-<hex>@example.com", "password": "correct-horse-battery-staple"}`
- **Expected:**
  - Step 1: `201`, body has `id`, `name` and the address as sent.
  - Step 2: exactly one row, at `users.users` — not in `public`.
  - Step 3: `app_metadata.role` is exactly `event_organiser`.
  - Step 4: both cookies present, each `HttpOnly` and `Secure`; no token
    anywhere in the body.
  - Step 5: `200`, body contains step 1's profile plus
    `role: event_organiser`.
  - Step 6: `204`.
  - Step 7: `200`, body identical to step 1's.
  - Step 8: `200` with the same `id` and `role: event_organiser`.
- **Actual:** As expected at every step. Sign-up returned `201` with a session,
  the row was readable at `users.users`, the Auth user had trusted
  `app_metadata.role = event_organiser`, both cookies came back `HttpOnly` and
  `Secure` with no token in the body, and `/users/me` returned the same profile
  plus the trusted `event_organiser` role after both sign-up and login.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signup_login_me_logout_round_trip`

## TC-USERS-102 — the same address cannot sign up twice

- **Scenario:** The duplicate check holds against the real unique constraint,
  not just against a fake that was told to say so.
- **Pre-conditions:** Shared (item 5 not required).
- **Steps:**
  1. `POST /users/signup` with a fresh address.
  2. `POST /users/signup` again with the identical payload.
  3. Delete the account, in the fixture teardown.
- **Test data:** As TC-USERS-101.
- **Expected:** Step 1 `201`; step 2 `409` with `detail` exactly
  `"Email already registered"`, and no second account.
- **Actual:** First `201`, second `409` with `"Email already registered"`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_signing_up_twice_with_one_email_is_refused`

## TC-USERS-103 — `/users/me` without cookies is a 401

- **Scenario:** The route guard's signed-out answer, from the real service
  rather than the test client.
- **Pre-conditions:** Shared (item 5 not required). No cookies sent.
- **Steps:** 1. `GET /users/me` with no `Cookie` header.
- **Test data:** None.
- **Expected:** `401`, `detail` exactly `"Not authenticated"`.
- **Actual:** `401` with `"Not authenticated"`.
- **Status:** Pass
- **Evidence:** `test_app.py::test_me_without_a_session_is_401`

## TC-USERS-104 — public signup cannot choose an internal role

- **Scenario:** Prove public signup rejects role input before account creation.
- **Pre-conditions:** Shared (item 5 not required).
- **Steps:** 1. `POST /users/signup` with valid public signup fields plus
  `"role": "event_coordinator"`.
- **Test data:** Shared test data plus `"role": "event_coordinator"`.
- **Expected:** `422`, with `role` identified in the validation errors; no Auth
  user or profile row is created.
- **Actual:** `422`; `role` was identified in the validation errors and no test
  record was created.
- **Status:** Pass
- **Evidence:** `test_app.py::test_public_signup_cannot_choose_another_role`

## TC-USERS-105 — coordinator listing against real Supabase

- **Scenario:** Prove `GET /users/coordinators` against real Auth app metadata
  and the real `users.users` table, not the unit tests' fake.
- **Pre-conditions:** `.env.test` targets the throwaway project; `users.sql` is
  applied and `users` exposed; the users service is running on port 8001. Two
  temporary Auth users are created: one with trusted role `event_coordinator`,
  one with trusted role `event_organiser`, each with a matching profile row.
- **Steps:** 1. `GET /users/coordinators`. 2. Delete both Auth users and
  profile rows.
- **Test data:** Two `spm-users-<hex>@example.com` accounts.
- **Expected:** `200`; response includes the coordinator account's id, name,
  and email, and does not include the organiser account.
- **Actual:** Not yet run.
- **Status:** Blocked — needs the new endpoint built.
- **Evidence:** —
