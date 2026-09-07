# Unit tests

Fast, isolated tests for a single module or function.

- No network calls, no database, no running services — mock or stub every
  external collaborator.
- Each test should run in milliseconds.
- Mirror the source tree here, e.g. `unit/atomic/user/test_routes.py` for
  `backend/services/atomic/user`.

```bash
pytest tests/unit
```
