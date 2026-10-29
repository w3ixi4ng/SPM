"""S-82: an accepted requirement change adds one entry to its event's change
history. TC-EQUIPMENTREQUIREMENTS-032 and -033."""

import logging
from unittest.mock import AsyncMock

import pytest

from .conftest import COORDINATOR_ID, EVENT_ID, ITEM_ID, fake_response, requirement, user

PATH = f"/equipment-requirements/{EVENT_ID}/{ITEM_ID}"
HISTORY = f"/internal/events/{EVENT_ID}/history"


@pytest.fixture
def history(services):
    def post(path, **kwargs):
        return fake_response(201, {"id": 1}) if path.endswith("/history") else services.cleared

    services.events.post = AsyncMock(side_effect=post)
    return services


def entries(services):
    return [call.kwargs["json"] for call in services.events.post.await_args_list if call.args[0] == HISTORY]


def listing(services, *answers):
    services.equipment.get = AsyncMock(side_effect=[fake_response(200, rows) for rows in answers])


def change(action, before, after):
    return {
        "actor_id": COORDINATOR_ID, "actor_role": "event_coordinator", "action": action,
        "details": {"equipment_item_id": ITEM_ID, "item_name": "Wireless Microphone",
                    "from_quantity": before, "to_quantity": after},
    }


# --- TC-EQUIPMENTREQUIREMENTS-032 -------------------------------------------
def test_a_requirement_change_is_recorded(client, history):
    listing(history, [], [requirement(2)])
    history.saved = fake_response(200, requirement(2))
    assert client.put(PATH, json={"required_quantity": 2, "impact_accepted": True}).status_code == 200

    listing(history, [requirement(2)])
    history.saved = fake_response(200, requirement(5))
    assert client.put(PATH, json={"required_quantity": 5, "impact_accepted": True}).status_code == 200

    listing(history, [requirement(5)])
    assert client.delete(PATH, params={"impact_accepted": True}).status_code == 204

    assert entries(history) == [
        change("equipment_requirement_set", None, 2),
        change("equipment_requirement_set", 2, 5),
        change("equipment_requirement_removed", 5, None),
    ]


# --- TC-EQUIPMENTREQUIREMENTS-033 -------------------------------------------
def test_refused_or_failed_recording_leaves_the_change(client, history, caplog):
    history.me = fake_response(200, user(role="technical_support"))
    assert client.put(PATH, json={"required_quantity": 5, "impact_accepted": True}).status_code == 403

    history.me = fake_response(200, user())
    history.events.post = AsyncMock(return_value=fake_response(500, {"detail": "boom"}))
    assert client.put(PATH, json={"required_quantity": 5, "impact_accepted": True}).status_code == 502
    history.equipment.put.assert_not_awaited()
    assert entries(history) == []

    def history_fails(path, **kwargs):
        return fake_response(500, {"detail": "boom"}) if path.endswith("/history") else history.cleared

    history.events.post = AsyncMock(side_effect=history_fails)
    listing(history, [requirement(2)])
    history.saved = fake_response(200, requirement(5))
    with caplog.at_level(logging.ERROR):
        response = client.put(PATH, json={"required_quantity": 5, "impact_accepted": True})

    assert response.status_code == 200
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert EVENT_ID in errors[0] and "equipment_requirement_set" in errors[0]
