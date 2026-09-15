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

Only Event Organiser workflows are currently defined. Other roles receive a
dashboard without operational controls rather than speculative functionality.

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

## Verification

From the repository root:

```bash
node --test tests/unit/frontend/test_*.mjs
cd frontend && npm run lint && npm run build
```
