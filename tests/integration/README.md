# Integration tests

Tests that cross a real boundary — database, HTTP between services, message
broker.

- Dependencies must be running before these tests start
  (e.g. `docker compose up -d`).
- Each test cleans up the data it creates so the suite can be re-run.
- Slower than unit tests; keep the count focused on the seams that matter.

```bash
pytest tests/integration
```
