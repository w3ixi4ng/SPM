"""TC-VENUEBOOKINGS-105: real decision and unchanged assignment boundary."""
import httpx
import pytest
from .conftest import GATEWAY_BASE_URL, cookie_for, requires_env, _make_user

pytestmark = requires_env


# S-75 adds a live clash warning to listed rows (and, on held/confirmed rows,
# the venue's setup and turnaround). These compare the booking itself.
S75_FIELDS = {"clashes", "setup_minutes", "turnaround_minutes"}


def booking_only(row):
    return {key: value for key, value in row.items() if key not in S75_FIELDS}


@pytest.fixture
def other_coordinators(admin):
    created = []
    try:
        for label in ('New assigned Coordinator', 'Unrelated Coordinator'):
            created.append(_make_user(admin, 'event_coordinator', label))
        yield created
    finally:
        for user in created:
            admin.auth.admin.delete_user(user['id'])


def unchanged(after: dict, before: dict) -> bool:
    """Every field the row had before still holds the same value. Columns
    added to the shared test project while the suite runs are not a rewrite
    by the decision, so they are ignored."""
    return {key: after.get(key) for key in before} == before


def test_saved_decisions_visible_only_under_existing_event_access(admin, auth_client, world, other_coordinators):
    coordinator = cookie_for(auth_client, world['coordinator'])
    staff = cookie_for(auth_client, world['staff'])
    event_id = world['event_id']
    before_event = admin.schema('events').table('events').select('*').eq('id', event_id).execute().data[0]
    before_venue = admin.schema('venues').table('venues').select('*').eq('id', world['venue_id']).execute().data[0]
    saved = []
    # S-30: holds are exclusive, so the two requests take different times.
    for (start, end), payload in [
        (('09:00', '12:00'), {'decision': 'approved'}),
        (('13:00', '15:00'), {'decision': 'rejected', 'reason': 'Room needs repairs', 'alternative': 'Try Studio C on Friday'}),
    ]:
        created = httpx.post(f'{GATEWAY_BASE_URL}/venue-bookings', headers=coordinator, json={
            'event_id': event_id, 'venue_id': world['venue_id'], 'booking_date': '2026-11-12',
            'start_time': start, 'end_time': end,
        }, timeout=20)
        assert created.status_code == 201, created.text
        booking_id = created.json()['id']
        result = httpx.post(f'{GATEWAY_BASE_URL}/venue-bookings/{booking_id}/decision', headers=staff, json=payload, timeout=20)
        assert result.status_code == 200, result.text
        saved.append(result.json())
    listed = httpx.get(f'{GATEWAY_BASE_URL}/venue-bookings', headers=coordinator, params={'event_id': event_id}, timeout=20)
    assert listed.status_code == 200 and [booking_only(row) for row in listed.json()] == saved
    assert [r['status'] for r in saved] == ['confirmed', 'rejected']
    assert saved[1]['decision_reason'] == 'Room needs repairs'
    assert saved[1]['decision_alternative'] == 'Try Studio C on Friday'
    pending = httpx.get(f'{GATEWAY_BASE_URL}/venue-bookings/pending', headers=staff, timeout=20)
    assert pending.status_code == 200
    assert not {r['id'] for r in saved} & {r['id'] for r in pending.json()}
    assert unchanged(admin.schema('events').table('events').select('*').eq('id', event_id).execute().data[0], before_event)
    assert unchanged(admin.schema('venues').table('venues').select('*').eq('id', world['venue_id']).execute().data[0], before_venue)
    # Existing access rule remains: even the requester loses access after reassignment.
    new_assigned, unrelated = other_coordinators
    admin.schema('events').table('events').update({'assigned_coordinator_id': new_assigned['id']}).eq('id', event_id).execute()
    assert httpx.get(f'{GATEWAY_BASE_URL}/venue-bookings', headers=coordinator,
                     params={'event_id': event_id}, timeout=20).status_code == 404
    for user, code in ((new_assigned, 200), (unrelated, 404)):
        response = httpx.get(f'{GATEWAY_BASE_URL}/venue-bookings', headers=cookie_for(auth_client, user),
                             params={'event_id': event_id}, timeout=20)
        assert response.status_code == code
        if code == 200:
            assert [booking_only(row) for row in response.json()] == saved
