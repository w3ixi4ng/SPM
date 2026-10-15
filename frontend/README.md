# ConnectSphere frontend

React and Vite frontend for ConnectSphere. Browser API requests use the `/api`
prefix and include the HTTP-only Supabase session cookies issued by the users
service.

## Role-aware access

On startup, `AuthProvider` calls `GET /users/me`. The response's trusted `role`
selects a role dashboard:

| Role | Dashboard |
| --- | --- |
| `event_organiser` | `/dashboard/event-organiser` |
| `event_coordinator` | `/dashboard/event-coordinator` |
| `event_coordinator_lead` | `/dashboard/event-coordinator-lead` |
| `venue_staff` | `/dashboard/venue-staff` |
| `technical_support` | `/dashboard/technical-support` |
| `safety_officer` | `/dashboard/safety-officer` |
| `attendee` | `/dashboard/attendee` |

The shared presentation policy lives in `src/lib/access.js`. Route guards hide
and redirect obvious unauthorized navigation, but this is not a security
boundary: services must enforce the same permissions against the verified
Supabase session.

Each dashboard exposes only the controls permitted for that trusted role.
Route guards are a presentation convenience; the services independently
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

## S-85 coordinator oversight

The Event Coordinator Lead dashboard groups active work under every trusted
Event Coordinator and keeps Coordinators with zero assignments visible. Each
group shows its active-assignment count; each event shows its name, lifecycle
status, organiser, complete date/time window, and current Coordinator.

The overview is loaded from
`GET /api/event-requests/coordinator-overview`. Its active set is
`submitted`, `under_review`, `returned`, `planning`, and `confirmed` with a
non-null assignment. Loading, empty-pool, zero-assignment, and service-failure
states are distinct. The S-83 unassigned queue and S-84 reassignment controls
remain on the same dashboard. A successful reassignment moves the event
between the displayed groups and updates both counts without a reload.

## S-86 operational safety checks

Safety Officers load `GET /api/safety-checks` and open an eligible confirmed
event at `/safety-checks/{id}`. The detail combines organiser and schedule,
confirmed venue capacity/layout/accessibility/restrictions, Technical Support
assignment/notes, equipment requirements, and the event's special
requirements. Loading, empty, controlled failure, detail and success states
are distinct.

The browser posts only `decision` and the applicable reason. The composite
derives the Safety Officer id from the verified session. Approval advances to
`preparation`; rejection uses `safety_rejected`; requested changes return the
event to `planning` with preserved feedback and history. Conflicts never
display success, and S-86 sends no notification.

## S-87 safety changes and resubmission

An assigned Coordinator's dashboard marks a planning event whose current
safety decision is `changes_requested` as **Returned after safety review**.
The event detail loads the preserved reason, Safety Officer identity, decision
time and history from `GET /api/safety-checks/coordinator/events/{id}`. Venue,
equipment and Technical Support controls remain available because the event is
back in `planning` and no existing arrangement is deleted.

**Resubmit for Safety Review** posts to the route's `/resubmit` action. It is
shown only for a safety-returned planning event. Success changes the displayed
event to `confirmed`, announces that a fresh review is required, and disables
planning-only arrangement edits. Loading, controlled error and success states
are distinct. S-87 adds no notifications and does not replace S-17's general
confirmation workflow.

## S-77 mark venue temporarily unavailable

On a venue's availability calendar, Venue Staff choose **Mark unavailable**
and enter a start date and time, an end date and time, and a reason
(Maintenance, Equipment failure, Renovation, Safety concern, or Other
operational reason, which needs a description). The slide-over panel stays
open after saving and lists the held and confirmed bookings the period
affects. If their Coordinators couldn't be notified, it offers **Notify
Coordinators** to retry.

The calendar marks a day the period covers completely as Unavailable. A day
it covers only partly reads Partly unavailable (or keeps its booking state)
and lists the period's times in the day's detail.

On the Coordinator's event page, a booking a period affects shows "Needs
alternative arrangements" with the period and its reason. The Coordinator
also gets an in-app notification. Bookings and events are never changed by a
period. Helpers are in `src/lib/venueAvailability.js` and
`src/lib/venueBookings.js`.

## S-78 request replacement venue for affected booking

On the Coordinator's event page, a booking flagged "Needs alternative
arrangements" offers **Find a replacement venue** and **Mark resolved**.

**Find a replacement venue** opens its own screen,
`/coordinator/events/:id/bookings/:bookingId/replacement`. It shows the
booking's date and times and the event's requirements as read-only text, and
lists only the venues the service says are suitable and free then. The
Coordinator picks one, can add notes, and sends it. Back on the event page,
the booking stays flagged and reads "Replacement requested: <venue>, waiting
for Venue Staff". Once Venue Staff approve, it reads "Replaced by <venue>".
Venue Staff's request page says "Replacement for <venue>".

**Mark resolved** opens a slide-over panel for a note on what was arranged
instead. The booking then reads "Resolved: <note>". Helpers are in
`src/lib/venueBookings.js`.

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
