# Event service

Atomic service. Owns the `event` entity and its storage.

## Responsibility

CRUD over events. Does not call any other service.

## Endpoints



## Running

```bash
uvicorn app:app --reload
```

## Tests

- Unit: `tests/unit/atomic/event/`
- Integration: `tests/integration/atomic/event/`
