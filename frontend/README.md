# ConnectSphere frontend

React and Vite frontend for ConnectSphere. Browser API requests use the `/api`
prefix and include the HTTP-only Supabase session cookies issued by the users
service.

## Role-aware access

On startup, `AuthProvider` calls `GET /users/me`. The response's trusted `role`
selects one of six dashboards:

| Role | Dashboard |
| --- | --- |
| `event_organiser` | `/dashboard/event-organiser` |
| `event_coordinator` | `/dashboard/event-coordinator` |
| `event_coordinator_lead` | `/dashboard/event-coordinator-lead` |
| `venue_staff` | `/dashboard/venue-staff` |
| `technical_support` | `/dashboard/technical-support` |
| `attendee` | `/dashboard/attendee` |

The shared presentation policy lives in `src/lib/access.js`. Route guards hide
and redirect obvious unauthorized navigation, but this is not a security
boundary: services must enforce the same permissions against the verified
Supabase session.

Each dashboard exposes only the controls permitted for that trusted role.

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

## S-83 assignment and notifications

The Event Coordinator Lead dashboard loads the unassigned request queue and
trusted Event Coordinator list through the `event_requests` composite. The
Lead explicitly chooses a Coordinator for each request. The UI does not check
or reject scheduling conflicts because that is not an S-83 business rule.

Event Organiser and Event Coordinator dashboards load persistent in-app
notifications from `GET /api/notifications`. Assignment creates one
notification for each party. Retrying an assignment after a notification
service failure is safe and does not duplicate either message. The product
does not send assignment email or any external notification.

## S-84 coordinator reassignment

The Lead dashboard also lists assigned active events with their organiser and
current Coordinator. The Lead chooses any different trusted Coordinator; the
UI does not filter scheduling conflicts. A successful action updates the card
without a reload and transfers the event between Coordinator workspaces.

The browser submits the displayed current owner and assignment version with
the new Coordinator id. A stale `409` asks the Lead to reload rather than
silently overwriting a newer transfer. The former Coordinator, new
Coordinator, and Organiser receive persistent in-app notifications. Retrying
after notification failure is idempotent, and no email/external delivery is
used.

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
