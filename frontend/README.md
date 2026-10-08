# ConnectSphere frontend

React and Vite frontend for ConnectSphere. Browser API requests use the `/api`
prefix and include the HTTP-only Supabase session cookies issued by the users
service.

## Role-aware access

On startup, `AuthProvider` calls `GET /users/me`. The response's trusted `role`
selects one of five dashboards:

| Role | Dashboard |
| --- | --- |
| `event_organiser` | `/dashboard/event-organiser` |
| `event_coordinator` | `/dashboard/event-coordinator` |
| `venue_staff` | `/dashboard/venue-staff` |
| `technical_support` | `/dashboard/technical-support` |
| `attendee` | `/dashboard/attendee` |

The shared presentation policy lives in `src/lib/access.js`. Route guards hide
and redirect obvious unauthorized navigation, but this is not a security
boundary: services must enforce the same permissions against the verified
Supabase session.

Each dashboard exposes only the workflows already defined for its trusted
role. Route guards are a presentation convenience; the services independently
enforce every read and write against the verified session.

## Technical Support assignments (S-43)

The Technical Support dashboard keeps the Equipment Catalogue global: every
Technical Support staff member can view and manage the shared catalogue. Its
separate **Assigned events** section calls `GET /api/events/support-assigned`
and `GET /api/equipment-requirements`, then groups each requirement under its
event.

Only `planning` and `confirmed` events assigned to the signed-in staff member
are returned. Each card shows the event name, schedule, status, support notes,
and only that event's required equipment and quantities. Cancelled or otherwise
inactive events, another staff member's events, and their requirements are not
rendered. An empty assignment list is shown distinctly from a load failure.
The backend applies the same assignment filter; the frontend filter is only a
defensive presentation check.

## Event requests

The Event Organiser form calls the events service through Kong at
`/api/events`. New and existing drafts use the create and PATCH endpoints;
complete new requests and existing drafts use the corresponding submission
endpoints. Opening `/events/{id}` reloads the server-owned event and submitted
requests are read-only.

The Event Organiser dashboard loads `GET /api/events` and shows every request
owned by the authenticated organiser, with distinct Draft and Submitted labels.
Each entry links back to `/events/{id}` for editing or read-only viewing.

`src/lib/eventRequests.js` owns the explicit camelCase-to-snake_case payload
mapping. It never sends server-managed identity, ownership, status, or timestamp
fields. Event requests are not persisted in browser storage and API failures do
not silently report a save or submission.

## Development

From this directory:

```bash
npm install
npm run dev
```

Vite proxies `/api` to Kong on port 8000. The backend stack must therefore be
running for login and role resolution.

## In Docker

`docker compose up --build` from the repository root builds this app and serves
it from nginx behind Kong, at `http://localhost:8000`. That is the arrangement
the end-to-end tests drive and the one production uses.

The container is **not** published on a host port. The app calls a relative
`/api`, so it is only coherent on an origin serving both it and the services;
reached directly it would render and then 404 every API call. Use `npm run dev`
for day-to-day work — the Vite proxy above imitates the same single origin, and
you get hot reload.

Two things this build depends on, both easy to break:

- `nginx.conf` falls back to `index.html`, because React Router's paths do not
  exist on disk. Without it, reloading `/dashboard/event-organiser` is a 404.
- Kong routes `/` here **last**; `/api/*` is more specific and still wins.

## Verification

From the repository root:

```bash
node --test tests/unit/frontend/test_*.mjs
cd frontend && npm run lint && npm run build
```


## Edit venue details (S-28)

Venue Staff see Edit beside every venue in their catalogue. `/venues/:id/edit`
loads the saved venue and reuses the Add Venue form controls for location,
capacity, facilities and accessibility only. Other roles cannot open this route;
the backend independently enforces `venues:update`.

Save calls `PATCH /api/venues/{id}` and returns to a newly loaded staff catalogue.
The updated values appear without a manual refresh and survive subsequent page
loads. Other users may refresh their already-open pages. Cancel returns without
saving. Field errors preserve entered values; load/save failures are shown safely.

Existing booking history is unchanged. Availability and editing name, description,
operating hours or layouts are outside this story. No new booking logic is added.

Automated browser checks (fresh `.env.test` Docker stack and Chromium required):

```bash
pytest tests/e2e/test_update_venue.py tests/e2e/test_add_venue.py
```

## S-37 booking decisions

Venue Staff use the existing Pending booking requests list: choose Approve
or Reject, optionally enter a reason/alternative, then Save decision. Rejection
requires at least one nonblank explanation. Successful saves reload the pending
list automatically. Failures display safe feedback; a stale request returns a
conflict rather than overwriting a decision. Decisions are final.

The currently assigned Coordinator reopens or refreshes the event and sees
Confirmed/Rejected and any reason/alternative in Venue requests. Existing event
access rules remain unchanged; access for the original requester after
reassignment remains an open requirement. Suggestions never reserve another slot.

Apply the [S-37 SQL block](../backend/sql/bookings.sql) to development and test
before trying the feature. No frontend environment changes are required.
This story does not prevent overlapping confirmations: S-38 must protect the
atomic confirmation operation before a double-booking guarantee can be made.
