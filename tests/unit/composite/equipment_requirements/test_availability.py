"""S-44: the equipment availability check, TC-EQUIPMENTREQUIREMENTS-012..019."""
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from .conftest import fake_response, user

TS_ID = "abababab-abab-4bab-8bab-abababababab"
PATH = "/equipment-requirements/availability"
WINDOW = {"start_date": "2026-11-12", "start_time": "09:00", "end_date": "2026-11-12", "end_time": "12:00"}

MIC = "11111111-0000-4000-8000-00000000000a"
PROJECTOR = "11111111-0000-4000-8000-00000000000b"
SPEAKER = "11111111-0000-4000-8000-00000000000c"


def item(item_id, type_, total, operational="available", lifecycle="active"):
    return {"id": item_id, "type": type_, "description": None, "total_quantity": total,
            "operational_status": operational, "lifecycle_status": lifecycle}


# As GET /equipment returns it: ordered by type.
CATALOGUE = [
    item(SPEAKER, "Old Speaker", 6, lifecycle="retired"),
    item(PROJECTOR, "Projector", 4, operational="maintenance"),
    item(MIC, "Wireless Microphone", 12),
]


def event(event_id, status, start_date, start_time, end_date, end_time, name):
    return {"id": event_id, "name": name, "status": status, "start_date": start_date,
            "start_time": start_time, "end_date": end_date, "end_time": end_time}


E5 = event("e5000000-0000-4000-8000-000000000005", "planning", "2026-11-11", "18:00:00", "2026-11-12", "09:30:00", "Overnight setup")
E1 = event("e1000000-0000-4000-8000-000000000001", "planning", "2026-11-12", "10:00:00", "2026-11-12", "11:00:00", "Alumni talk")
E2 = event("e2000000-0000-4000-8000-000000000002", "confirmed", "2026-11-12", "11:30:00", "2026-11-12", "13:00:00", "Board lunch")
OVERLAPPING = [E5, E1, E2]  # as the events service returns them: start order


def requirement(event_, item_id, quantity):
    return {"id": f"r-{event_['id'][:2]}-{item_id[-1]}", "event_id": event_["id"],
            "equipment_item_id": item_id, "required_quantity": quantity}


def requirements(e1_mics=5):
    return [requirement(E1, MIC, e1_mics), requirement(E2, MIC, 3),
            requirement(E5, MIC, 2), requirement(E5, PROJECTOR, 1)]


def arrange(services, *, overlapping=OVERLAPPING, catalogue=CATALOGUE, reqs=None):
    services.me = fake_response(200, user("technical_support", TS_ID))
    services.events.post = AsyncMock(return_value=fake_response(200, overlapping))
    reqs = requirements() if reqs is None else reqs

    async def equipment_get(path, **kwargs):
        if path == "/equipment":
            return fake_response(200, catalogue)
        assert path == "/internal/equipment-requirements", path
        return fake_response(200, reqs)

    services.equipment.get = AsyncMock(side_effect=equipment_get)


def check(client, **params):
    return client.get(PATH, params={**WINDOW, **params}, cookies={"sb_access_token": "token"})


def by_type(body):
    return {entry["type"]: entry for entry in body["items"]}


# --- TC-EQUIPMENTREQUIREMENTS-012 ----------------------------------------
def test_availability_counts_reserved_and_unavailable_units_for_the_window(client, services):
    arrange(services)

    response = check(client)

    assert response.status_code == 200, response.text
    body = response.json()
    datetime.fromisoformat(body["checked_at"])
    assert {key: body[key] for key in WINDOW} == WINDOW
    assert body["quantity"] is None
    assert [entry["type"] for entry in body["items"]] == ["Projector", "Wireless Microphone"]
    projector, mic = body["items"]
    assert {k: projector[k] for k in ("total", "reserved", "unavailable", "available", "over_reserved", "sufficient")} == {
        "total": 4, "reserved": 1, "unavailable": 4, "available": 0, "over_reserved": False, "sufficient": None}
    assert {k: mic[k] for k in ("total", "reserved", "unavailable", "available", "over_reserved", "sufficient")} == {
        "total": 12, "reserved": 10, "unavailable": 0, "available": 2, "over_reserved": False, "sufficient": None}
    assert [(r["event_name"], r["required_quantity"]) for r in mic["reservations"]] == [
        ("Overnight setup", 2), ("Alumni talk", 5), ("Board lunch", 3)]
    assert set(mic["reservations"][0]) == {"event_id", "event_name", "status", "start_date", "start_time",
                                           "end_date", "end_time", "required_quantity"}

    services.events.post.assert_awaited_once_with("/events/overlapping", json=WINDOW)
    requirement_call = services.equipment.get.await_args_list[1]
    assert requirement_call.kwargs["params"] == [("event_ids", e["id"]) for e in OVERLAPPING]
    assert services.equipment.get.await_args_list[0].kwargs["cookies"] == {"sb_access_token": "token"}


# --- TC-EQUIPMENTREQUIREMENTS-013 ----------------------------------------
@pytest.mark.parametrize("quantity, mic_enough", [(2, True), (3, False)])
def test_a_quantity_says_whether_each_item_is_enough(client, services, quantity, mic_enough):
    arrange(services)

    body = check(client, quantity=quantity).json()

    assert body["quantity"] == quantity
    assert by_type(body)["Wireless Microphone"]["sufficient"] is mic_enough
    assert by_type(body)["Projector"]["sufficient"] is False


# --- TC-EQUIPMENTREQUIREMENTS-014 ----------------------------------------
def test_over_reserved_pools_show_zero_never_a_negative(client, services):
    arrange(services, reqs=requirements(e1_mics=9))

    mic = by_type(check(client).json())["Wireless Microphone"]

    assert (mic["reserved"], mic["available"], mic["over_reserved"]) == (14, 0, True)


# --- TC-EQUIPMENTREQUIREMENTS-015 ----------------------------------------
@pytest.mark.parametrize("search, expected", [
    ("MICRO", ["Wireless Microphone"]),
    ("  ", ["Projector", "Wireless Microphone"]),
    ("drum", []),
])
def test_the_type_search_narrows_the_items(client, services, search, expected):
    arrange(services)

    response = check(client, type=search)

    assert response.status_code == 200
    assert [entry["type"] for entry in response.json()["items"]] == expected


# --- TC-EQUIPMENTREQUIREMENTS-016 ----------------------------------------
def test_no_overlapping_events_means_nothing_is_reserved(client, services):
    arrange(services, overlapping=[])

    body = check(client).json()

    assert by_type(body)["Wireless Microphone"]["reserved"] == 0
    assert by_type(body)["Wireless Microphone"]["available"] == 12
    assert by_type(body)["Projector"]["available"] == 0
    assert [call.args[0] for call in services.equipment.get.await_args_list] == ["/equipment"]


# --- TC-EQUIPMENTREQUIREMENTS-017 ----------------------------------------
@pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "venue_staff"])
def test_only_technical_support_can_check(client, services, role):
    arrange(services)
    services.me = fake_response(200, user(role))

    response = check(client)

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied"}
    services.events.post.assert_not_called()
    services.equipment.get.assert_not_called()


def test_no_session_cannot_check(client, services):
    arrange(services)
    services.me = fake_response(401, {"detail": "Not authenticated"})

    response = check(client)

    assert response.status_code == 401
    services.events.post.assert_not_called()


@pytest.mark.parametrize("changes, field", [
    ({"start_date": None}, "start_date"),
    ({"start_time": None}, "start_time"),
    ({"end_date": None}, "end_date"),
    ({"end_time": None}, "end_time"),
    ({"start_date": "12-11-2026"}, "start_date"),
    ({"quantity": "0"}, "quantity"),
    ({"quantity": "-1"}, "quantity"),
    ({"quantity": "two"}, "quantity"),
])
def test_a_malformed_check_is_refused_naming_the_field(client, services, changes, field):
    arrange(services)
    params = {key: value for key, value in {**WINDOW, **changes}.items() if value is not None}

    response = client.get(PATH, params=params)

    assert response.status_code == 422
    assert any(field in key for key in response.json()["errors"]), response.json()
    services.events.post.assert_not_called()
    services.equipment.get.assert_not_called()


@pytest.mark.parametrize("changes", [{"end_time": "09:00"}, {"end_date": "2026-11-11"}])
def test_the_end_must_be_after_the_start(client, services, changes):
    arrange(services)

    response = check(client, **changes)

    assert response.status_code == 422
    assert response.json()["errors"] == {"end_time": "The end must be after the start"}
    services.events.post.assert_not_called()
    services.equipment.get.assert_not_called()


# --- TC-EQUIPMENTREQUIREMENTS-018 ----------------------------------------
@pytest.mark.parametrize("failing, service", [
    ("events", "Events"), ("catalogue", "Equipment"), ("requirements", "Equipment"),
])
@pytest.mark.parametrize("failure", ["connect", "500"])
def test_a_failing_dependency_is_never_an_answer(client, services, failing, service, failure):
    arrange(services)
    broken = (AsyncMock(side_effect=httpx.ConnectError("refused")) if failure == "connect"
              else AsyncMock(return_value=fake_response(500, {"detail": "private"})))
    if failing == "events":
        services.events.post = broken
    else:
        working = services.equipment.get.side_effect

        async def equipment_get(path, **kwargs):
            if (failing == "catalogue") == (path == "/equipment"):
                return await broken(path, **kwargs)
            return await working(path, **kwargs)

        services.equipment.get = AsyncMock(side_effect=equipment_get)

    response = check(client)

    assert response.status_code == 502
    assert response.json() == {"detail": f"{service} service unavailable"}


# --- TC-EQUIPMENTREQUIREMENTS-019 ----------------------------------------
def test_every_check_reads_live_data(client, services):
    arrange(services)
    first = check(client).json()

    arrange(services, reqs=requirements(e1_mics=9))  # a requirement changed in between
    second = check(client).json()

    assert by_type(first)["Wireless Microphone"]["available"] == 2
    assert by_type(second)["Wireless Microphone"]["reserved"] == 14
    assert by_type(second)["Wireless Microphone"]["available"] == 0
    assert services.events.post.await_count == 1  # the fresh fake saw its own call
    assert datetime.fromisoformat(second["checked_at"]) >= datetime.fromisoformat(first["checked_at"])
