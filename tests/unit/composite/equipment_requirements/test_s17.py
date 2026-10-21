"""S-17: Technical Support sign-off on an event's equipment arrangements."""

from unittest.mock import AsyncMock

import httpx
import pytest

from .conftest import (
    COORDINATOR_ID,
    EVENT_ID,
    ITEM_ID,
    SECOND_EVENT_ID,
    SUPPORT_ID,
    event,
    fake_response,
    user,
)

OTHER_SUPPORT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SIGN_OFF = f"/equipment-requirements/{EVENT_ID}/sign-off"


def scheduled(**changes):
    row = event(**changes)
    row.update(
        start_date="2026-11-20", start_time="09:00:00",
        end_date="2026-11-20", end_time="17:00:00",
    )
    return row


PROJECTOR = {
    "id": ITEM_ID,
    "type": "Projector",
    "description": None,
    "total_quantity": 5,
    "operational_status": "available",
    "lifecycle_status": "active",
}


def needs(event_id, quantity):
    return {"event_id": event_id, "equipment_item_id": ITEM_ID, "required_quantity": quantity}


def as_support(services, the_event=None, *, others_reserve=0, support_id=SUPPORT_ID):
    """E1 needs 4 projectors of 5; E2 overlaps and reserves `others_reserve`."""
    services.me = fake_response(200, user("technical_support", support_id))
    services.support_event = fake_response(200, the_event or scheduled())
    overlapping = [scheduled()]
    requirements = [needs(EVENT_ID, 4)]
    if others_reserve:
        overlapping.append(scheduled(event_id=SECOND_EVENT_ID))
        requirements.append(needs(SECOND_EVENT_ID, others_reserve))
    services.events.post = AsyncMock(return_value=fake_response(200, overlapping))

    def equipment_get(path, *args, **kwargs):
        if path == "/equipment":
            return fake_response(200, [PROJECTOR])
        return fake_response(200, requirements)

    services.equipment.get = AsyncMock(side_effect=equipment_get)


# --- TC-EQUIPMENTREQUIREMENTS-023 -----------------------------------------
def test_approve_without_shortage(client, services):
    as_support(services)

    response = client.post(SIGN_OFF, json={"decision": "approved"})

    assert response.status_code == 200, response.text
    services.events.put.assert_awaited_once_with(
        f"/internal/events/{EVENT_ID}/technical-signoff",
        json={"technical_support_id": SUPPORT_ID, "decision": "approved"},
    )


# --- TC-EQUIPMENTREQUIREMENTS-024 -----------------------------------------
def test_shortage_blocks_approval(client, services):
    as_support(services, others_reserve=3)

    response = client.post(SIGN_OFF, json={"decision": "approved"})

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Some equipment is short for this event",
        "short": [{"equipment_item_id": ITEM_ID, "name": "Projector", "required": 4, "available": 2}],
    }
    services.events.put.assert_not_called()


# --- TC-EQUIPMENTREQUIREMENTS-025 -----------------------------------------
def test_shortage_override_requires_comment(client, services):
    as_support(services, others_reserve=3)

    blank = client.post(SIGN_OFF, json={"decision": "approved", "override_comment": "   "})
    assert blank.status_code == 422
    services.events.put.assert_not_called()

    response = client.post(SIGN_OFF, json={
        "decision": "approved",
        "override_comment": "Borrowing 2 projectors from Library",
    })
    assert response.status_code == 200, response.text
    services.events.put.assert_awaited_once_with(
        f"/internal/events/{EVENT_ID}/technical-signoff",
        json={
            "technical_support_id": SUPPORT_ID,
            "decision": "approved",
            "override_comment": "Borrowing 2 projectors from Library",
        },
    )


# --- TC-EQUIPMENTREQUIREMENTS-026 -----------------------------------------
def test_decline_requires_reason(client, services):
    as_support(services)

    missing = client.post(SIGN_OFF, json={"decision": "declined"})
    assert missing.status_code == 422
    services.events.put.assert_not_called()

    response = client.post(SIGN_OFF, json={
        "decision": "declined", "reason": "Only one sound desk exists",
    })
    assert response.status_code == 200, response.text
    services.events.put.assert_awaited_once_with(
        f"/internal/events/{EVENT_ID}/technical-signoff",
        json={
            "technical_support_id": SUPPORT_ID,
            "decision": "declined",
            "reason": "Only one sound desk exists",
        },
    )
    # A decline needs no availability check.
    services.events.post.assert_not_called()
    services.equipment.get.assert_not_called()


# --- TC-EQUIPMENTREQUIREMENTS-027 -----------------------------------------
def test_signoff_limited_to_assigned_support(client, services):
    as_support(services, support_id=OTHER_SUPPORT_ID)
    services.support_event = fake_response(404, {"detail": "Event not found"})
    assert client.post(SIGN_OFF, json={"decision": "approved"}).status_code == 404

    services.me = fake_response(200, user())
    assert client.post(SIGN_OFF, json={"decision": "approved"}).status_code == 403

    services.me = fake_response(401, {"detail": "Not authenticated"})
    assert client.post(SIGN_OFF, json={"decision": "approved"}).status_code == 401

    as_support(services, scheduled(status="pending_safety_check"))
    refused = client.post(SIGN_OFF, json={"decision": "approved"})
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Technical Support sign-off can only change while the event is in planning"
    )

    services.events.put.assert_not_called()


# --- TC-EQUIPMENTREQUIREMENTS-028 -----------------------------------------
@pytest.mark.parametrize("action", ["put", "delete"])
def test_requirement_change_clears_signoff(client, services, action):
    order = []
    services.events.post = AsyncMock(
        side_effect=lambda *a, **k: order.append("clear") or services.cleared
    )
    # The browser DELETE is implemented by the audited atomic POST route.
    write = services.equipment.put if action == "put" else services.equipment.post
    previous = write.side_effect
    write.side_effect = lambda *a, **k: order.append("write") or previous(*a, **k)

    path = f"/equipment-requirements/{EVENT_ID}/{ITEM_ID}"
    if action == "put":
        response = client.put(path, json={
            "required_quantity": 5,
            "impact_accepted": True,
        })
        assert response.status_code == 200, response.text
    else:
        response = client.delete(path, params={"impact_accepted": True})
        assert response.status_code == 204, response.text

    assert order == ["clear", "write"]
    services.events.post.assert_awaited_once_with(
        f"/internal/events/{EVENT_ID}/technical-signoff/clear"
    )


# --- TC-EQUIPMENTREQUIREMENTS-029 -----------------------------------------
@pytest.mark.parametrize(
    "failure",
    [fake_response(500, {"detail": "boom"}), httpx.ConnectError("down")],
)
def test_failed_clear_blocks_requirement_change(client, services, failure):
    if isinstance(failure, Exception):
        services.events.post = AsyncMock(side_effect=failure)
    else:
        services.events.post = AsyncMock(return_value=failure)

    response = client.put(
        f"/equipment-requirements/{EVENT_ID}/{ITEM_ID}",
        json={"required_quantity": 5, "impact_accepted": True},
    )

    assert response.status_code == 502
    services.equipment.put.assert_not_called()
    assert services.me.json()["id"] == COORDINATOR_ID
