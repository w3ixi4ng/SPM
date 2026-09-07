# Tests

Test suite for the backend services.

## Layout

| Folder | Purpose |
| --- | --- |
| `unit/` | Fast, isolated tests. No network, no database, no running services — collaborators are mocked or stubbed. |
| `integration/` | Tests that cross a boundary: real database, HTTP calls between services, message broker, etc. |

## Conventions

- Test files are named `test_<subject>.py`.
- Mirror the source layout inside each folder, e.g. tests for
  `backend/services/atomic/user` live in `unit/atomic/user/` and
  `integration/atomic/user/`.
- Each test is independent and can run in any order.

## Running

```bash
# everything
pytest tests

# only the fast ones
pytest tests/unit

# only the ones that need services up
pytest tests/integration
```

Integration tests expect their dependencies (databases, atomic services) to be
reachable. Bring them up first, e.g. `docker compose up -d`.
