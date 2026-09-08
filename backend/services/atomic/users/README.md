# Users service

Atomic service. Owns the `users` entity and its storage.

## Responsibility

CRUD over users. Does not call any other service.

## Endpoints


## Running

```bash
uvicorn app:app --reload
```

## Tests

- Unit: `tests/unit/atomic/users/`
- Integration: `tests/integration/atomic/users/`
