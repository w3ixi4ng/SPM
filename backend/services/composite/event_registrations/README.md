# Event registrations composite

S-51. Serves confirmed events' public pages, and lets Attendees register for
them while registration is open. S-48: each registration can be read back by
the Attendee who holds it and by the Organiser who owns the event. S-49: a
recorded registration sends the Attendee an in-app confirmation. Owns no storage: event details and
registration settings come from `events`, venue names from `bookings` and
`venues`, the signed-in user from `users`, and places are written to
`registrations`, and confirmations to `notifications`.

Browser-facing through Kong at `/api/event-registrations`.

## Endpoints

| Method | Path | Sign-in | Purpose |
| --- | --- | --- | --- |
| `GET` | `/event-registrations/events` | none | Every confirmed event's public details, by start. |
| `GET` | `/event-registrations/events/{event_id}` | none | One confirmed event's public details. |
| `POST` | `/event-registrations/events/{event_id}/registration` | Attendee | Register the signed-in Attendee, if the period is open, the Organiser hasn't closed it, and a place is left (S-50). |
| `GET` | `/event-registrations/events/{event_id}/registration` | Attendee | Whether the signed-in Attendee is registered, or on the waiting list. |
| `DELETE` | `/event-registrations/events/{event_id}/registration` | Attendee | S-53: withdraw the signed-in Attendee's place, until the event starts. The next Attendee waiting takes it and is notified. |
| `POST` | `/event-registrations/events/{event_id}/waiting-list` | Attendee | S-50: join a full event's waiting list. |
| `GET` | `/event-registrations/me/registrations` | Attendee | The confirmed events the signed-in Attendee is registered for or waiting for (S-52), soonest first. |
| `GET` | `/event-registrations/events/{event_id}/attendees` | the event's Organiser | Who has registered for the event, earliest first, and who is on its waiting list. |
| `GET` | `/health`, `/event-registrations/health` | none | Liveness check. |

## Request

No body or query parameters on any route. The event id is in the path; the
Attendee or Organiser is whoever the `sb_access_token` cookie belongs to,
never anything in the request.

## Response

**Public event** (`GET /events`, an array of these; `GET /events/{id}`, one):

```json
{
  "id": "22222222-2222-4222-8222-222222222222",
  "name": "Alumni networking evening",
  "purpose": "Reconnect alumni with current students",
  "start_date": "2026-11-20",
  "start_time": "18:00:00",
  "end_date": "2026-11-20",
  "end_time": "21:00:00",
  "venues": ["Seminar Room 2-1"],
  "registration_required": true,
  "registration_opens_at": "2026-11-01T09:00:00",
  "registration_closes_at": "2026-11-15T18:00:00",
  "registration_closed_by_organiser": false,
  "is_full": false
}
```

S-50: `is_full` is true once the registered Attendees reach the event's
expected attendance -- the same figure the S-35 venue check uses. The figure
itself is never shown. `registration_closed_by_organiser` is true while the
Organiser has closed registration early.

`venues` lists the names of the event's confirmed bookings, and is `[]` until
one is confirmed. With registration off, `registration_required` is `false`
and both dates are `null`. Nothing about the organiser, the expected
attendance, contacts or internal notes is ever included.

**Registration** (`201` from `POST`, `200` from `GET`):

```json
{"event_id": "22222222-2222-4222-8222-222222222222", "registered": true, "registered_at": "2026-11-05T04:00:00Z", "waitlisted": false, "joined_at": null, "position": null}
```

`GET` answers `{"registered": false, "registered_at": null, ...}` when the
Attendee holds no place, with `"waitlisted": true`, `joined_at` and
`position` if they are on the waiting list. `position` (S-52) is their place
in line, first come, first served: `1` is next.

**Waiting list** (`201` from `POST /events/{event_id}/waiting-list`):

```json
{"event_id": "22222222-2222-4222-8222-222222222222", "waitlisted": true, "joined_at": "2026-11-05T04:00:00Z", "position": 2}
```

It is refused with the same `401`/`403`/`404` and period `409`s as
registering, plus the S-50 rows below. Where several apply, the first wins:
registration off, then the period, then the Organiser's close, then full.

**Confirmation (S-49).** Once a `POST` has recorded the place, the composite
stores one `registration_confirmation` notification for the Attendee through
the notifications service (`POST /internal/notifications`, deduplicated on
`registration_confirmation:{registration id}`). The Attendee reads it on their
dashboard via `GET /api/notifications`:

```text
Registration confirmed: Alumni networking evening, 20 Nov 2026, 6:00 pm – 9:00 pm, at Seminar Room 2-1. Name: Ada Tan. Email: ada@example.com.
```

An event ending on a later day reads `20 Nov 2026, 6:00 pm – 21 Nov 2026,
12:30 am`; several confirmed venues are joined (`at Seminar Room 2-1, Hall
A`); none reads `venue to be confirmed`. Any refused or failed `POST` sends
nothing. If the confirmation can't be built or stored after the place is
recorded, the `POST` still answers `201` and the failure is only logged.

| Status | When | `detail` |
| --- | --- | --- |
| `401` | Registering or checking without signing in | "Sign in to register for this event." |
| `403` | Signed in, but not an `attendee` | "Only attendee accounts can register for events." |
| `404` | The event is missing or not `confirmed` | "Event not found." |
| `409` | The event doesn't use registration | "This event doesn't need registration." |
| `409` | Before the period opens | "Registration hasn't opened yet. It's open from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm." |
| `409` | At or after the period closes | "Registration has closed. It was open from 1 Nov 2026, 9:00 am to 15 Nov 2026, 6:00 pm." |
| `409` | Already registered | "You're already registered for this event." |
| `409` | The Organiser closed registration (register or waiting list) | "The organiser has closed registration for this event." |
| `409` | Registering once the event is full | "This event is full. You can join the waiting list." |
| `409` | Joining the waiting list while places are left | "This event still has places. Register instead." |
| `409` | Joining the waiting list twice | "You're already on the waiting list for this event." |
| `502` | A service it depends on did not answer | "Events service unavailable" (or Users, Bookings, Venues, Registrations) |

The period is Singapore time. "Now" is read in Singapore time whatever the
server's clock, opening is inclusive and closing is exclusive.

**My registrations** (`200` from `GET /me/registrations`; `[]` when none):

```json
[
  {
    "event_id": "22222222-2222-4222-8222-222222222222",
    "name": "Alumni networking evening",
    "start_date": "2026-11-20",
    "start_time": "18:00:00",
    "end_date": "2026-11-20",
    "end_time": "21:00:00",
    "status": "confirmed",
    "registered_at": "2026-11-05T04:00:00Z",
    "joined_at": null,
    "position": null
  },
  {
    "event_id": "88888888-8888-4888-8888-888888888888",
    "name": "Careers fair",
    "start_date": "2026-11-25",
    "start_time": "10:00:00",
    "end_date": "2026-11-25",
    "end_time": "16:00:00",
    "status": "waitlisted",
    "registered_at": null,
    "joined_at": "2026-11-06T04:00:00Z",
    "position": 2
  }
]
```

S-52: `status` is `confirmed` for a place and `waitlisted` for a waiting-list
entry, which has `joined_at` and its place in line instead of
`registered_at`. Only events that are still `confirmed` are listed. Answers `401` and `403`
exactly as registering does.

**Withdrawal** (`200` from `DELETE /events/{event_id}/registration`): the
Attendee's status afterwards, the same shape as the `GET`:

```json
{"event_id": "22222222-2222-4222-8222-222222222222", "registered": false, "registered_at": null, "waitlisted": false, "joined_at": null, "position": null}
```

Allowed until the event's `start_date` + `start_time`, Singapore time, even
after the registration period ends or the Organiser closes it. The
registrations service gives the freed place to the Attendee who has waited
longest, up to the event's `expected_attendance`. That Attendee gets one
`waiting_list_promotion` notification: "A place opened up: you're now
registered for {event}, {date and time}, at {venues}. Name: {name}. Email:
{email}." Like the S-49 confirmation it is best effort: if it can't be built
or stored, the failure is logged and the withdrawal still answers `200`.

| Status | When | `detail` |
| --- | --- | --- |
| `401` | Not signed in | "Sign in to withdraw your registration." |
| `403` | Not an Attendee | "Only attendee accounts can register for events." |
| `404` | Not a confirmed event | "Event not found." |
| `404` | The Attendee holds no place (including only waiting) | "You're not registered for this event." |
| `409` | The event has started | "This event has already started. You can no longer withdraw." |
| `502` | Users, Events or Registrations did not answer | "Registrations service unavailable" (or Users, Events) |

**Event attendees** (`200` from `GET /events/{event_id}/attendees`):

```json
{
  "event_id": "22222222-2222-4222-8222-222222222222",
  "count": 1,
  "attendees": [
    {
      "attendee_id": "33333333-3333-4333-8333-333333333333",
      "name": "Ada Tan",
      "email": "ada@example.com",
      "registered_at": "2026-11-05T04:00:00Z"
    }
  ],
  "waiting_list": [
    {
      "attendee_id": "44444444-4444-4444-8444-444444444444",
      "name": "Ben Lim",
      "email": "ben@example.com",
      "joined_at": "2026-11-06T04:00:00Z"
    }
  ]
}
```

With no registrations, `count` is `0` and `attendees` is `[]`; `waiting_list`
is oldest first and `[]` when no one is waiting. Ownership is
the events service's to decide; its answer is passed on:

| Status | When | `detail` |
| --- | --- | --- |
| `401` | Not signed in | "Sign in to see who has registered." |
| `403` | Signed in, but not an Event Organiser | "Insufficient permissions" |
| `404` | Missing, or another Organiser's event | "Event not found" |
| `502` | A service it depends on did not answer | "Events service unavailable" (or Users, Registrations) |

## Configuration

`USERS_SERVICE_URL`, `EVENTS_SERVICE_URL`, `BOOKINGS_SERVICE_URL`,
`VENUES_SERVICE_URL`, `REGISTRATIONS_SERVICE_URL` and
`NOTIFICATIONS_SERVICE_URL`. Every outbound client
has a bounded timeout.

## Running

Development, with the atomic services it calls running and the URLs above
pointing at `localhost`:

```bash
cd backend/services/composite/event_registrations
uvicorn app:app --reload --port 8104
```

Unit tests need no Docker or Supabase:

```bash
pytest tests/unit/composite/event_registrations
```

Integration and browser tests need the S-51 block of
[`events.sql`](../../../sql/events.sql) and
[`registrations.sql`](../../../sql/registrations.sql) applied and exposed in
the test project, plus the S-49 `registration_confirmation` kind in
[`notifications.sql`](../../../sql/notifications.sql), and the whole stack started immediately before:

```bash
docker compose --env-file .env.test down -v
docker compose --env-file .env.test up -d --build --wait
pytest tests/integration/composite/event_registrations
pytest tests/e2e/test_register_for_event.py tests/e2e/test_set_registration_period.py
```
