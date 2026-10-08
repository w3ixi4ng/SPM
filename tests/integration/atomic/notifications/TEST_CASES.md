# Test cases — notifications service (integration)

Covers the real notifications service against the test Supabase project.

| | |
| --- | --- |
| Suite | `docker compose --env-file .env.test up -d --build --wait`, then `pytest tests/integration/atomic/notifications` |
| Last run | Not run — blocked until the developer applies and exposes `notifications` in the test project |
| Environment | `.env.test`; fresh full stack; notifications schema applied, granted, and exposed |
| Result | Blocked |

**Story:** S-83 Assign Event Requests from Unassigned Queue.

## TC-NOTIFICATIONS-101 — assignment notifications persist and remain recipient-private

- **Scenario:** The table, grants, exposed schema, service role, Auth
  validation, and recipient filter agree across a real boundary.
- **Pre-conditions:** Fresh `.env.test` stack; `notifications` schema applied,
  granted, and exposed; temporary organiser, coordinator, and unrelated user
  accounts exist and are cleaned up afterwards.
- **Steps:** 1. Create the confirmed two-recipient internal batch. 2. Sign in
  as the organiser and list notifications twice. 3. Sign in as the
  coordinator and list. 4. Sign in as the unrelated user and list. 5. Repeat
  the internal batch when both rows exist. 6. Delete each recipient row in
  turn, repeat the complete batch, and count matching rows directly with the
  admin client after each retry.
- **Test data:** Event `Autumn Forum`; the three temporary user ids; kind
  `event_assignment`; the two stable deduplication keys.
- **Expected:** Organiser and coordinator each see their one notification on
  both reads; the unrelated user sees none. Retrying with both rows present
  creates no duplicates; retrying with either row missing recreates only the
  missing row. Every final count is exactly two—one per recipient. Cleanup
  removes them and the test can run twice.
- **Actual:** Cannot run until the developer applies `backend/sql/notifications.sql`
  and exposes `notifications` in the test Supabase project.
- **Status:** Blocked
- **Evidence:** `test_app.py::test_assignment_notifications_persist_and_are_recipient_private`
