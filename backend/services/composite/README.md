# Composite services

Orchestration layer. A composite service strings together calls to the atomic
services in [`../atomic`](../atomic/README.md) to carry out one business use
case.

## Rules

- Owns no database of its own — all state lives behind an atomic service.
- Talks to atomic services over HTTP only.
- Holds the business logic that spans more than one entity.

## Services

| Service | Spans | Use case |
| --- | --- | --- |
| [`event_requests/`](event_requests/README.md) | `events`, `users` | Route a submitted event request to a free event coordinator. |
| [`venue_bookings/`](venue_bookings/README.md) | `users`, `events`, `venues`, `bookings` | Check and submit a Coordinator's venue booking request; list pending ones for Venue Staff. |
| [`equipment_requirements/`](equipment_requirements/README.md) | `users`, `events`, `equipment` | Let the currently assigned Coordinator record equipment during planning; let Technical Support view it. |

Add one folder per use case, following the service structure in
[`AGENTS.md`](../../../AGENTS.md).
