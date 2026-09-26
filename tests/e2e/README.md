# End-to-end tests

A real browser, driving the built frontend through Kong, against both services
and a real (test) Supabase project. The slowest tests in the repo and the only
ones that see the whole thing at once.

Three journeys. That is deliberate — see [what goes here](#what-goes-here).

## What only these can prove

Everything below is invisible to the other suites, and each has already broken
once:

- **Kong's routing.** That `/api/users` still wins over the frontend's `/`
  catch-all, and that a service prefix is not dropped or doubled.
- **The SPA fallback.** Opening `/dashboard/event-organiser` directly — or
  reloading it — has to serve `index.html`. Without `try_files` in
  `frontend/nginx.conf` it is a 404 that reads like a broken route.
- **A session cookie surviving a page load.** The cookies are `httpOnly` and
  `Secure`, and no JavaScript can see them. Only a browser can tell you they
  were set, sent back, and cleared.
- **That the frontend's policy mirror is true.** `frontend/src/lib/access.js`
  restates the permissions in the events service's `authorization.py`. Nothing
  keeps them in step; TC-E2E-204 is what notices when they drift.

## Before they will run

1. **A `.env.test` pointing at a test Supabase project**, with both schemas
   applied, exposed and granted — the same setup
   [`../integration/README.md`](../integration/README.md) describes. These
   tests create and delete real accounts and rows.

2. **Turn off email confirmation** in that project —
   Authentication → Providers → Email → *Confirm email*. With it on, sign-up
   returns no session, and TC-E2E-201 skips with that message rather than
   failing. The other three seed confirmed accounts through the admin API and
   do not care.

3. **The whole stack, frontend included:**

   ```bash
   docker compose --env-file .env.test up -d --build --wait
   ```

4. **Chromium.** `pip` installs the bindings; the browser is a separate
   download:

   ```bash
   pip install -r ../requirements.txt
   playwright install chromium
   ```

## Running

```bash
pytest tests/e2e

# watch it happen, which is the fastest way to debug a selector
pytest tests/e2e --headed --slowmo 300

# one journey
pytest tests/e2e/test_role_access.py -v
```

Everything is addressed through **Kong** on `KONG_PROXY_PORT`, never a service
port and never the Vite dev server. The frontend container is not published on
a host port for exactly this reason: the app calls a relative `/api`, so it is
only coherent on the origin that serves both.

## What goes here

Whole journeys a person would recognise, named after the journey rather than
the service — `test_sign_up.py`, not `test_users.py`.

**Keep the number very small.** The repo's rule is many unit tests, few
integration tests; e2e should be fewer still. Each one is slow, needs the
entire stack, and has more ways to be flaky than everything else combined. A
case belongs here only if no other suite can prove it — if you can reach it
with a `TestClient` and a `MagicMock`, that is where it goes.

Do not add a journey per role or per field. Validation rules, error messages
and status codes are already covered in `tests/unit/`.

## Cleaning up

Every fixture deletes what it created — the auth account, its profile row, and
any events. The suite has to pass twice in a row.

If a run dies mid-teardown (a dropped connection to Supabase will do it),
accounts can be left behind. They are all addressed `spm-e2e-*@example.com`,
so they are easy to find and remove.

## When one fails

In order of likelihood:

1. **The stack is not up, or is up on `.env` instead of `.env.test`.** Check
   `docker compose --env-file .env.test ps`.
2. **A selector moved.** These drive the real pages; renaming an input id or a
   button's text breaks them, and that is the point. Rerun with `--headed
   --slowmo 300` and watch where it stops.
3. **The database is not set up** — the same list as the integration tests.
4. **Email confirmation is on**, and TC-E2E-201 skipped rather than ran. A skip
   is not a pass; the case is Blocked until the setting changes.
