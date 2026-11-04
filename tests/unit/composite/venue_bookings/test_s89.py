"""S-89: venue unavailability never cancels anything by itself, and a
released booking stays visible without a flag. TC-VENUEBOOKINGS-400..401."""

from unittest.mock import AsyncMock

import pytest

from .conftest import app_module, fake_response, me
from .test_unavailable_periods import A, B, BLOCK_ID, COOKIE, REQUEST, STUDIO_B, TODAY, Studio

E1 = A["event_id"]
EVENT_CLOSED = "This event's venue bookings can no longer be changed"


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(app_module, "_today", lambda: TODAY)


@pytest.fixture
def studio(services):
    return Studio(services)


# --- TC-VENUEBOOKINGS-400 ------------------------------------------------------
def test_marking_a_venue_unavailable_never_cancels_or_rejects_anything(client, studio):
    marked = client.post("/venue-bookings/blocks", json=REQUEST, cookies=COOKIE)
    retried = client.post(f"/venue-bookings/blocks/{BLOCK_ID}/notify", cookies=COOKIE)

    assert marked.status_code == 201
    assert {row["id"] for row in marked.json()["affected_bookings"]} >= {A["id"], B["id"]}
    assert retried.status_code == 200

    services = studio.services
    # The block insert is the only Bookings write.
    assert [call.args[0] for call in services.bookings.post.await_args_list] == ["/blocks"]
    services.bookings.delete.assert_not_awaited()
    for name in ("patch", "put"):
        method = getattr(services.bookings, name, None)
        if isinstance(method, AsyncMock):
            method.assert_not_awaited()
    # Events is only read and given history -- never a status-changing write.
    event_writes = [
        call.args[0] for call in getattr(services.events, "post", AsyncMock()).await_args_list
    ]
    assert not any(
        path.endswith(("/cancellation-decision", "/venue-cancellation", "/decision"))
        for path in event_writes
    )


# --- TC-VENUEBOOKINGS-401 ------------------------------------------------------
def _released(row):
    return {
        **row, "status": "released", "released_at": "2026-11-11T02:00:00+00:00",
        "released_by": row["coordinator_id"], "release_reason": "event_cancelled",
    }


@pytest.mark.parametrize("role", ["event_coordinator", "event_organiser"])
def test_a_released_booking_is_listed_without_a_flag(client, studio, role):
    studio.services.user = me(role)
    released = _released(A)
    studio.by_event = [released]

    async def events_get(path, **kwargs):
        return fake_response(200, {"id": E1, "status": "cancelled"})

    studio.services.events.get = AsyncMock(side_effect=events_get)

    response = client.get("/venue-bookings", params={"event_id": E1}, cookies=COOKIE)

    assert response.status_code == 200, response.text
    [row] = response.json()
    assert row["status"] == "released"
    if role == "event_coordinator":
        assert row["requires_alternative_arrangements"] is False
        assert row["clashes"] == []


def test_a_released_booking_of_a_cancelled_event_cannot_be_replaced(client, studio):
    studio.services.user = me("event_coordinator")
    released = _released(A)
    studio.one[released["id"]] = released

    async def events_get(path, **kwargs):
        return fake_response(200, {"id": E1, "status": "cancelled"})

    studio.services.events.get = AsyncMock(side_effect=events_get)

    search = client.get(f"/venue-bookings/{released['id']}/replacement-venues", cookies=COOKIE)
    request = client.post(
        f"/venue-bookings/{released['id']}/replacement", json={"venue_id": STUDIO_B}, cookies=COOKIE,
    )

    assert search.status_code == 409
    assert search.json()["detail"] == EVENT_CLOSED
    assert request.status_code == 409
    assert request.json()["detail"] == EVENT_CLOSED
    studio.services.bookings.post.assert_not_awaited()
