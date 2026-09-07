# User service

Atomic service. Owns the `user` entity and its storage.

## Responsibility

CRUD over users. Does not call any other service.

## Endpoints


## Running

```bash
uvicorn app:app --reload
```

## Tests

- Unit: `tests/unit/atomic/user/`
- Integration: `tests/integration/atomic/user/`
