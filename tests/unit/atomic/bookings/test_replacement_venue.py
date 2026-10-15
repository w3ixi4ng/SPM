"""S-78: replacement requests and resolving the flag, TC-BOOKINGS-051..056."""
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import BOOKING, app, booking_row, database_module, lookups, table

E1 = BOOKING['event_id']
A_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
R1_ID = '11111111-1111-4111-8111-111111111111'
STUDIO_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
HALL_C = 'cccccccc-0000-4000-8000-000000000000'
STAFF = 'abababab-abab-4bab-8bab-abababababab'
C2 = '22222222-0000-4000-8000-000000000002'
COOKIE = {'sb_access_token': 'verified-token'}
SQL = Path(__file__).resolve().parents[4] / 'backend' / 'sql' / 'bookings.sql'

A = booking_row(id=A_ID, venue_id=STUDIO_B, status='confirmed', decided_by=STAFF,
                decided_at='2026-10-02T09:00:00+00:00')
R1_BODY = {**BOOKING, 'venue_id': HALL_C, 'venue_name': 'Hall C', 'replaces_booking_id': A_ID}


@pytest.fixture
def signed_in():
    fake = MagicMock()
    app.dependency_overrides[database_module.get_auth] = lambda: fake

    def as_role(role, user_id):
        fake.auth.get_user.return_value.user = SimpleNamespace(id=user_id, app_metadata={'role': role})

    as_role('event_coordinator', C2)
    yield as_role
    app.dependency_overrides.pop(database_module.get_auth, None)


def echo_insert(db):
    insert = table(db).insert
    insert.return_value.execute.side_effect = lambda: MagicMock(
        data=[{'id': R1_ID, **insert.call_args.args[0]}]
    )


# --- TC-BOOKINGS-051 ------------------------------------------------------
def test_a_replacement_is_stored_with_its_link(client, db):
    # The original, then the overlap and period checks.
    lookups(db, [A], [], [])
    echo_insert(db)

    response = client.post('/bookings', json=R1_BODY)

    assert response.status_code == 201, response.text
    inserted = table(db).insert.call_args.args[0]
    assert inserted['replaces_booking_id'] == A_ID
    assert inserted['status'] == 'pending'
    assert response.json()['replaces_booking_id'] == A_ID


def test_an_ordinary_request_has_no_link(client, db):
    lookups(db)
    echo_insert(db)

    response = client.post('/bookings', json=BOOKING)

    assert response.status_code == 201, response.text
    assert table(db).insert.call_args.args[0]['replaces_booking_id'] is None
    assert response.json()['replaces_booking_id'] is None


@pytest.mark.parametrize('original, message', [
    (None, "The booking being replaced doesn't exist"),
    ({**A, 'event_id': 'eeeeeeee-0000-4000-8000-000000000009'}, 'A replacement must be for the same event'),
])
def test_a_link_to_a_missing_or_foreign_booking_is_refused(client, db, original, message):
    lookups(db, [original] if original else [])

    response = client.post('/bookings', json=R1_BODY)

    assert response.status_code == 422
    assert response.json()['errors'] == {'replaces_booking_id': message}
    table(db).insert.assert_not_called()


@pytest.mark.parametrize('settled', ['rejected', 'replaced'])
def test_a_link_to_a_settled_booking_is_refused(client, db, settled):
    lookups(db, [{**A, 'status': settled}])

    response = client.post('/bookings', json=R1_BODY)

    assert (response.status_code, response.json()) == (409, {'detail': 'This booking can no longer be replaced'})
    table(db).insert.assert_not_called()


def test_a_replacement_still_gets_the_overlap_check(client, db):
    taken = {'id': 'f0000000-0000-4000-8000-000000000001', 'status': 'confirmed', 'event_name': 'Other',
             'venue_name': 'Hall C', 'booking_date': '2026-11-12', 'start_time': '10:00:00', 'end_time': '11:00:00'}
    lookups(db, [A], [taken], [])

    response = client.post('/bookings', json=R1_BODY)

    assert response.status_code == 409
    assert response.json()['detail'] == 'Hall C is already confirmed on 12 Nov 2026 from 10:00 to 11:00.'
    table(db).insert.assert_not_called()


# --- TC-BOOKINGS-052 / 053 / 054 -----------------------------------------
def prepare_decision(db, booking):
    query = table(db).select.return_value
    for method in ('eq', 'neq', 'in_', 'lt', 'gt', 'lte', 'gte', 'order', 'limit'):
        getattr(query, method).return_value = query
    query.execute.side_effect = [SimpleNamespace(data=[booking]), SimpleNamespace(data=[]), SimpleNamespace(data=[])]
    update = table(db).update.return_value
    update.eq.return_value = update
    update.in_.return_value = update
    update.execute.side_effect = lambda: SimpleNamespace(data=[{**booking, **table(db).update.call_args.args[0]}])
    return update


@pytest.mark.parametrize('payload, expected', [
    ({'decision': 'approved'}, 'confirmed'),
    ({'decision': 'rejected', 'reason': 'Hall C is being repainted'}, 'rejected'),
])
def test_deciding_a_replacement_writes_only_the_replacement(client, db, signed_in, payload, expected):
    signed_in('venue_staff', STAFF)
    r1 = booking_row(id=R1_ID, venue_id=HALL_C, venue_name='Hall C', replaces_booking_id=A_ID)
    update = prepare_decision(db, r1)

    response = client.post(f'/bookings/{R1_ID}/decision', json=payload, cookies=COOKIE)

    assert response.status_code == 200, response.text
    assert response.json()['status'] == expected
    assert response.json()['decided_by'] == STAFF
    # The original is replaced by the database trigger, in the same
    # transaction as this update -- never by a second write from here.
    table(db).update.assert_called_once()
    assert update.eq.call_args_list[0].args == ('id', R1_ID)


def test_the_trigger_replaces_a_standing_original_when_its_replacement_is_confirmed():
    block = SQL.read_text().split('-- BEGIN S-78 DATA-PRESERVING MIGRATION')[1]
    function = re.search(r'create or replace function bookings\.replace_original_on_confirm\(\).*?\$\$;', block, re.S)
    assert function, 'the S-78 block defines the trigger function'
    body = function.group(0)
    assert "set status = 'replaced'" in body
    assert 'replaced_by_booking_id = new.id' in body
    assert 'replaced_at = now()' in body
    # Only a pending, held or confirmed original; a rejected or already
    # replaced one is left alone.
    assert "status in ('pending', 'held', 'confirmed')" in body
    assert re.search(
        r"after update of status on bookings\.bookings.*?when \(new\.status = 'confirmed' "
        r"and old\.status is distinct from 'confirmed'\s+and new\.replaces_booking_id is not null\)",
        block, re.S,
    )
    assert "'replaced'" in re.search(r'bookings_status_allowed\s+check \(status in \(([^)]*)\)\)', block).group(1)


# --- TC-BOOKINGS-055 ------------------------------------------------------
def prepare_resolution(db, booking):
    query = table(db).select.return_value
    query.eq.return_value = query
    query.execute.return_value = SimpleNamespace(data=[booking] if booking else [])
    update = table(db).update.return_value
    update.eq.return_value = update
    update.in_.return_value = update
    update.execute.side_effect = lambda: SimpleNamespace(data=[{**booking, **table(db).update.call_args.args[0]}])
    return update


@pytest.mark.parametrize('live', ['confirmed', 'held'])
def test_a_coordinator_records_a_resolution_note(client, db, signed_in, live):
    original = {**A, 'status': live}
    update = prepare_resolution(db, original)
    before = datetime.now(timezone.utc)

    response = client.post(f'/bookings/{A_ID}/alternative-resolution',
                           json={'note': '  Moved online for this session  '}, cookies=COOKIE)

    assert response.status_code == 200, response.text
    values = table(db).update.call_args.args[0]
    assert set(values) == {'alternative_resolved_at', 'alternative_resolved_by', 'alternative_resolution_note'}
    assert values['alternative_resolution_note'] == 'Moved online for this session'
    assert values['alternative_resolved_by'] == C2
    assert datetime.fromisoformat(values['alternative_resolved_at']) >= before
    update.in_.assert_called_once_with('status', ['held', 'confirmed'])
    saved = response.json()
    assert saved['status'] == live
    assert saved['decided_by'] == original['decided_by']


# --- TC-BOOKINGS-056 ------------------------------------------------------
def test_the_resolution_needs_a_coordinator_session(client, db, signed_in):
    prepare_resolution(db, A)
    path = f'/bookings/{A_ID}/alternative-resolution'
    assert client.post(path, json={'note': 'Fine'}).status_code == 401
    signed_in('venue_staff', STAFF)
    response = client.post(path, json={'note': 'Fine'}, cookies=COOKIE)
    assert (response.status_code, response.json()) == (403, {'detail': 'Permission denied'})
    table(db).update.assert_not_called()


def test_the_resolution_of_an_unknown_booking_is_not_found(client, db, signed_in):
    prepare_resolution(db, None)
    response = client.post(f'/bookings/{A_ID}/alternative-resolution', json={'note': 'Fine'}, cookies=COOKIE)
    assert (response.status_code, response.json()) == (404, {'detail': 'Booking not found'})
    table(db).update.assert_not_called()


@pytest.mark.parametrize('settled', ['pending', 'rejected', 'replaced'])
def test_only_a_live_booking_can_be_resolved(client, db, signed_in, settled):
    prepare_resolution(db, {**A, 'status': settled})
    response = client.post(f'/bookings/{A_ID}/alternative-resolution', json={'note': 'Fine'}, cookies=COOKIE)
    assert (response.status_code, response.json()) == (
        409, {'detail': 'Only a held or confirmed booking can be resolved'}
    )
    table(db).update.assert_not_called()


@pytest.mark.parametrize('body', [
    {'note': '   '}, {}, {'note': 'x' * 501},
    {'note': 'Fine', 'alternative_resolved_by': C2},
    {'note': 'Fine', 'alternative_resolved_at': '2026-10-13T10:00:00Z'},
])
def test_a_bad_resolution_body_is_refused(client, db, signed_in, body):
    prepare_resolution(db, A)
    response = client.post(f'/bookings/{A_ID}/alternative-resolution', json=body, cookies=COOKIE)
    assert response.status_code == 422, response.text
    if set(body) <= {'note'}:
        assert 'note' in response.json()['errors']
    table(db).update.assert_not_called()
