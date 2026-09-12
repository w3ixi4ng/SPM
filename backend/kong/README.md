# Kong

The API gateway. Everything the browser calls goes through here, so the
frontend knows one base URL — `/api` — instead of a port per service.

```
browser  ->  /api/users/login  ->  Kong  ->  http://users:8001/users/login
```

## Configuration

[`kong.yml`](kong.yml) is the whole configuration. Kong runs **DB-less**: no
database, no admin API, no runtime state. The routing table lives in git and
changes the same way code does — edit the file, restart Kong, review the diff.

```bash
docker compose restart kong
```

## Adding a service

One entry in `kong.yml`. The service's own path prefix goes on the **url**, not
the route:

```yaml
  - name: events
    url: http://events:8002/events     # the service's own prefix
    routes:
      - name: events
        paths:
          - /api/events                # what the browser calls
        strip_path: true
```

Kong strips `/api/events` and appends the rest to the url, so
`/api/events/42` reaches the events service as `/events/42`. Leaving the
prefix off the url sends it `/42` instead, and you get a 404 that looks like
the service is broken.

The frontend needs no change — it already calls `/api/...`.

## Ports

Kong's proxy is on **8000**, set by `KONG_PROXY_PORT`. Its admin API is
switched **off**: DB-less needs no admin, and Kong's default admin port is 8001,
which the users service already owns.

The services stay published on their own ports too, so you can still reach one
directly — `http://localhost:8001/users/me` — which is what the integration
tests do, to test the service rather than the gateway.
