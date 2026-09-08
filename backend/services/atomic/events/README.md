# Events service

Atomic service. Owns the `events` entity and its storage.

## Responsibility

CRUD over events. Does not call any other service.

## Endpoints



## Running

```bash
uvicorn app:app --reload
```

## Tests

- Unit: `tests/unit/atomic/events/`
- Integration: `tests/integration/atomic/events/`
