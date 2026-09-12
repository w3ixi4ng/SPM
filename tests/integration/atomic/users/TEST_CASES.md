# Test cases — users service (integration)

Covers `tests/integration/atomic/users/test_app.py`: the real service in Docker
against a real **test** Supabase project. These are the only cases that can
prove the `users` schema is exposed, that the grants ran, and that the table is
where the code thinks it is.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait` then `pytest tests/integration/atomic/users` |
| Last run | Not yet run — see Status below |
| Environment | Would be: `.env.test` pointing at the test Supabase project, users service on `localhost:8001` |
| Result | 3 Blocked |

**Everything below is Blocked, not Failed.** The cases cannot run until a
developer has applied [`backend/sql/users.sql`](../../../../backend/sql/users.sql)
to the test project and exposed the `users` schema. Blocked says "this has not
been proven yet"; Failed would say "this was tried and the service is wrong",
and that would be a different and worse claim.

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
  3. Inspect the `Set-Cookie` headers on the sign-up response.
  4. `GET /users/me`, sending the cookies from step 1.
  5. `POST /users/logout` with the same cookies.
  6. `POST /users/login` with the same address and password.
  7. `GET /users/me` with the cookies from step 6.
  8. Delete the account and its row, in the fixture teardown.
- **Test data:** `{"name": "Ada Lovelace", "email": "spm-test-<hex>@example.com", "password": "correct-horse-battery-staple"}`
- **Expected:**
  - Step 1: `201`, body has `id`, `name` and the address as sent.
  - Step 2: exactly one row, at `users.users` — not in `public`.
  - Step 3: both cookies present, each `HttpOnly` and `Secure`; no token
    anywhere in the body.
  - Step 4: `200`, body identical to step 1's.
  - Step 5: `204`.
  - Step 6: `200`, body identical to step 1's.
  - Step 7: `200` with the same `id`.
- **Actual:** —
- **Status:** Blocked — schema not yet applied or exposed on the test project.
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
- **Actual:** —
- **Status:** Blocked — schema not yet applied or exposed on the test project.
- **Evidence:** `test_app.py::test_signing_up_twice_with_one_email_is_refused`

## TC-USERS-103 — `/users/me` without cookies is a 401

- **Scenario:** The route guard's signed-out answer, from the real service
  rather than the test client.
- **Pre-conditions:** Shared (item 5 not required). No cookies sent.
- **Steps:** 1. `GET /users/me` with no `Cookie` header.
- **Test data:** None.
- **Expected:** `401`, `detail` exactly `"Not authenticated"`.
- **Actual:** —
- **Status:** Blocked — stack not yet runnable against the test project.
- **Evidence:** `test_app.py::test_me_without_a_session_is_401`
