# Composite services

Orchestration layer. A composite service strings together calls to the atomic
services in [`../atomic`](../atomic/README.md) to carry out one business use
case.

## Rules

- Owns no database of its own — all state lives behind an atomic service.
- Talks to atomic services over HTTP only.
- Holds the business logic that spans more than one entity.

## Services

_None yet._ Add one folder per use case, following the service structure in
[`AGENTS.md`](../../../AGENTS.md).
