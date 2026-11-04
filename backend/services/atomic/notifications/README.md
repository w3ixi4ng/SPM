# Notifications service

Atomic FastAPI service for persistent in-app notifications. It owns
`notifications.notifications`; no other service reads or writes that table.

Stories include S-63 Notify Organiser — Event Decisions and Changes, S-71 Notify Coordinator — Availability Change, S-83
Assign Event Requests from Unassigned Queue, S-84 Reassign Event Coordinator,
S-77 Mark Venue Temporarily Unavailable, S-81 Place Tentative Venue Hold with
Expiry, and S-49 Registration Confirmation Notification.

## Endpoints

| Method | Path | Caller | Does |
| --- | --- | --- | --- |
| `GET` | `/notifications` | Authenticated browser | Lists only the signed-in user's notifications, newest first. |
| `POST` | `/internal/notifications` | `event_requests`, `venue_bookings` and `event_registrations` composites | Idempotently persists a batch using each row's deduplication key. Not routed through Kong. |
| `GET` | `/health` | Infrastructure | Liveness check. |

## Request

`POST /internal/notifications` accepts:

```json
{
  "notifications": [
    {
      "recipient_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      "event_id": "33333333-3333-4333-8333-333333333333",
      "event_name": "Autumn Forum",
      "kind": "event_assignment",
      "message": "You have been assigned to Autumn Forum.",
      "deduplication_key": "event_assignment:33333333-3333-4333-8333-333333333333:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    }
  ]
}
```

All fields are required. The batch contains 1–20 rows and cannot repeat a
deduplication key. Supported kinds are `event_assignment`,
`event_reassignment`, `venue_unavailable` (a Coordinator's or Organiser's
booking needs alternative arrangements), `equipment_unavailable` (a confirmed
or preparation event needs replacement equipment), `venue_hold_expiry` (the
time a tentative hold will be released), `registration_confirmation` (an
Attendee's place at an event was recorded), `waiting_list_promotion` (S-53: a
withdrawal freed a place and this Attendee, first on the waiting list, now
holds it; no longer sent since S-55, kept for rows already stored), and
`waiting_list_offer` (S-55: a freed place is held for this Attendee, first on
the waiting list, until they accept or decline it), `event_cancelled` (S-69:
an event this Attendee was registered or waiting for was cancelled), and,
from S-74, `waiting_list_joined`, `registration_withdrawn` and
`waiting_list_offer_declined` (the Attendee joined a waiting list, withdrew
their place, or declined an offered place). S-63 adds the organiser kinds
`event_request_decision`, `venue_booking_decision`, `safety_check_outcome`,
and `event_schedule_changed`. S-84 sends a three-row reassignment batch whose
keys include the event's monotonic assignment version.

## Response

Successful create returns `201`; listing returns `200`. Both return rows with
the stored fields plus an integer `id` and `created_at` timestamp:

```json
[
  {
    "id": 1,
    "recipient_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "event_id": "33333333-3333-4333-8333-333333333333",
    "event_name": "Autumn Forum",
    "kind": "event_assignment",
    "message": "You have been assigned to Autumn Forum.",
    "deduplication_key": "event_assignment:33333333-3333-4333-8333-333333333333:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "created_at": "2026-10-08T12:00:00Z"
  }
]
```

Errors are `401` for a missing/expired list session, `422` for invalid create
data, and `500` when notification storage is unavailable.

## Run

First run `backend/sql/notifications.sql` in the dev Supabase SQL Editor,
grant the table, and expose the `notifications` schema. Fill the root `.env`,
then:

```bash
cd backend/services/atomic/notifications
uvicorn app:app --reload --port 8006
```

For tests, apply and expose the same schema in the throwaway test project,
fill `.env.test`, recreate the stack immediately before running, then run:

```bash
pytest tests/unit/atomic/notifications

docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/atomic/notifications
```
