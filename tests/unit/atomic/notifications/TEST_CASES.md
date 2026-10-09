# Test cases — notifications service (unit)

Covers the atomic `notifications` service introduced by S-83. Supabase and
Auth are faked; no network, database, or Docker is used.

| | |
| --- | --- |
| Suite | `pytest tests/unit/atomic/notifications` |
| Last run | 2026-10-09, branch `S-84/reassign-event-coordinator`, pre-commit working tree |
| Environment | Unit fakes only |
| Result | Pass — 9 passed; 735 passed across `tests/unit` |

**Stories:** S-83 Assign Event Requests from Unassigned Queue and S-84
Reassign Event Coordinator.

**Confirmed notification requirement:** a successful assignment creates a
persistent in-app notification for both the newly assigned Event Coordinator
and the Event Organiser. No email or external delivery is required.

## TC-NOTIFICATIONS-001 — health check does not touch storage

- **Scenario:** The service reports itself up independently of user data.
- **Pre-conditions:** Supabase dependency replaced by a fake.
- **Steps:** `GET /health`.
- **Test data:** None.
- **Expected:** `200`, `{"status":"ok"}`; no Auth or table call.
- **Actual:** `200` returned without Auth or storage calls.
- **Status:** Pass
- **Evidence:** `test_app.py::test_health_reports_ok`

## TC-NOTIFICATIONS-002 — authentication is required to list notifications

- **Scenario:** A caller cannot read notifications without a verified session.
- **Pre-conditions:** No valid access cookie.
- **Steps:** `GET /notifications`.
- **Test data:** No cookies.
- **Expected:** `401`; the notifications table is not queried.
- **Actual:** `401` returned and storage was untouched.
- **Status:** Pass
- **Evidence:** `test_app.py::test_list_notifications_requires_authentication`

## TC-NOTIFICATIONS-003 — a user sees only their own persistent notifications

- **Scenario:** Recipient ownership is enforced server-side.
- **Pre-conditions:** Auth resolves recipient A; storage returns A's assignment
  notifications newest first.
- **Steps:** `GET /notifications`.
- **Test data:** A's two rows and B's unrelated row in the fake setup.
- **Expected:** `200` with only A's rows; the query filters
  `recipient_id=A` and orders `created_at` descending. Returned fields are id,
  kind, event id/name, message, and created timestamp.
- **Actual:** The recipient filter and descending timestamp order were applied and only the fake recipient rows returned.
- **Status:** Pass
- **Evidence:** `test_app.py::test_user_lists_only_their_notifications_newest_first`

## TC-NOTIFICATIONS-004 — an empty inbox is a valid response

- **Scenario:** Having no notifications is not an error.
- **Pre-conditions:** Auth resolves recipient A; the filtered query returns
  no rows.
- **Steps:** `GET /notifications`.
- **Test data:** Recipient A.
- **Expected:** `200`, `[]`.
- **Actual:** `200 []` returned.
- **Status:** Pass
- **Evidence:** `test_app.py::test_empty_notification_inbox_returns_an_empty_list`

## TC-NOTIFICATIONS-005 — one internal batch persists both assignment recipients

- **Scenario:** The S-83 composite records the coordinator and organiser
  notifications together.
- **Pre-conditions:** The fake batch upsert returns two rows.
- **Steps:** `POST /internal/notifications` with the confirmed pair.
- **Test data:** Event `Autumn Forum`; organiser and coordinator A recipient
  ids; kind `event_assignment`; two distinct stable deduplication keys.
- **Expected:** `201` with two rows. Storage receives one batch upsert keyed by
  `deduplication_key`; recipient/event ids are UUIDs, messages are non-blank,
  and unknown fields or duplicate keys within the body return `422` before
  storage.
- **Actual:** One two-row upsert used `deduplication_key`; duplicate keys in one request were rejected before storage.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_batch_persists_both_assignment_notifications`

## TC-NOTIFICATIONS-006 — retrying the same batch creates no duplicates

- **Scenario:** Notification persistence can recover from an uncertain
  downstream response.
- **Pre-conditions:** The same logical notification batch is submitted after
  each possible prior result: neither recipient row exists, only one recipient
  row exists, or both rows exist because the earlier success response was
  lost.
- **Steps:** Submit the complete TC-NOTIFICATIONS-005 batch in every state.
- **Test data:** Identical two deduplication keys.
- **Expected:** Every call succeeds and returns the same two logical records;
  storage uses an upsert conflict target on the unique deduplication key to
  create only missing rows. The final state is always exactly one coordinator
  notification and one organiser notification—never duplicates.
- **Actual:** Repeated batches used the same unique conflict target and stable keys; real missing-row repair is specified by TC-NOTIFICATIONS-101.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_batch_is_idempotent_by_deduplication_key`

## TC-NOTIFICATIONS-007 — storage failures do not fabricate notification success

- **Scenario:** Data API errors are converted to the service's safe error
  shape.
- **Pre-conditions:** Select and upsert each raise in turn.
- **Steps:** List notifications, then create the internal batch.
- **Test data:** TC-NOTIFICATIONS-003 and TC-NOTIFICATIONS-005 data.
- **Expected:** Each returns `500 {"detail":"Internal server error"}` and no
  notification rows are fabricated in the response.
- **Actual:** Select and upsert failures returned safe `500` responses without fabricated rows.
- **Status:** Pass
- **Evidence:** `test_app.py::test_notification_storage_failures_are_safe`

## TC-NOTIFICATIONS-008 — reassignment accepts all three persistent recipients

- **Scenario:** S-84 uses the same atomic inbox for the former Coordinator,
  new Coordinator, and Event Organiser.
- **Steps:** Submit one `event_reassignment` batch containing all three.
- **Expected:** `201`; one upsert contains exactly three distinct recipients
  and version-scoped deduplication keys. A repeated batch is covered by the
  same unique-key idempotency rule as TC-NOTIFICATIONS-006.
- **Actual:** One upsert accepted the three distinct reassignment recipients
  and their version-scoped keys.
- **Status:** Pass
- **Evidence:** `test_app.py::test_internal_batch_accepts_three_reassignment_recipients`
