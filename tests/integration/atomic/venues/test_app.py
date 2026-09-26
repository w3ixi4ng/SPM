"""Real service/database round trips for the venues atomic service."""

import uuid

import httpx

from .conftest import BASE_URL, GATEWAY_BASE_URL, requires_env

pytestmark = requires_env


# --- TC-VENUES-101 --------------------------------------------------------
def test_venue_round_trip(admin, make_session, venue_ids):
    staff = make_session("venue_staff")
    coordinator = make_session("event_coordinator")
    name = f"spm-test Venue {uuid.uuid4().hex[:8]}"
    venue = {
        "name": name,
        "location": "1 Harbourfront Walk, Singapore 098585",
        "capacity": 250,
        "facilities": ["projector", "wifi"],
        "accessibility": ["wheelchair_access"],
        "room_layouts": ["theatre", "banquet"],
        "operating_hours": [{"day": "mon", "open": "09:00", "close": "18:00"}],
        "description": "Integration venue",
    }

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=staff["headers"]) as api:
        created = api.post("/venues", json=venue)
        assert created.status_code == 201, created.text
        saved = created.json()
        venue_ids.append(saved["id"])
        assert saved["created_by"] == staff["user_id"]
        assert saved["created_at"]

        fetched = api.get(f"/venues/{saved['id']}")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json() == saved

        listed = api.get("/venues")
        assert listed.status_code == 200, listed.text
        assert saved["id"] in {row["id"] for row in listed.json()}

    for field in ("name", "location", "capacity", "facilities", "accessibility",
                  "room_layouts", "description"):
        assert saved[field] == venue[field]
    assert saved["operating_hours"] == [
        {"day": "mon", "open": "09:00:00", "close": "18:00:00"}
    ]

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=coordinator["headers"]) as api:
        fetched = api.get(f"/venues/{saved['id']}")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json() == saved

        listed = api.get("/venues")
        assert listed.status_code == 200, listed.text
        assert saved["id"] in {row["id"] for row in listed.json()}

        refused = api.post("/venues", json={**venue, "name": f"{name} coordinator"})
        assert refused.status_code == 403, refused.text

    with httpx.Client(base_url=BASE_URL, timeout=15.0, headers=staff["headers"]) as api:
        duplicate = api.post("/venues", json={**venue, "name": name.upper()})
        assert duplicate.status_code == 409, duplicate.text

    rows = (
        admin.schema("venues").table("venues").select("*").ilike("name", name).execute().data
    )
    assert len(rows) == 1, "no single row in venues.venues -- check the schema is exposed and granted"
    assert rows[0]["created_by"] == staff["user_id"]


# --- TC-VENUES-102 --------------------------------------------------------
def test_kong_routes_every_venue_operation(make_session, venue_ids):
    staff = make_session("venue_staff")
    venue = {
        "name": f"spm-test Gateway {uuid.uuid4().hex[:8]}",
        "location": "10 Anson Road, Singapore 079903",
        "capacity": 30,
        "room_layouts": ["boardroom"],
        "operating_hours": [{"day": "tue", "open": "08:00", "close": "17:00"}],
    }

    with httpx.Client(
        base_url=GATEWAY_BASE_URL, timeout=15.0, headers=staff["headers"]
    ) as api:
        health = api.get("/venues/health")
        assert health.status_code == 200, health.text

        options = api.get("/venues/options")
        assert options.status_code == 200, options.text
        assert set(options.json()) == {"facilities", "accessibility", "room_layouts", "days"}

        created = api.post("/venues", json=venue)
        assert created.status_code == 201, created.text
        venue_id = created.json()["id"]
        venue_ids.append(venue_id)

        listed = api.get("/venues")
        assert listed.status_code == 200, listed.text
        assert venue_id in {row["id"] for row in listed.json()}

        fetched = api.get(f"/venues/{venue_id}")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["name"] == venue["name"]
