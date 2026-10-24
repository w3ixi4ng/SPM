"""S-17: a replacement may point at a booking Venue Staff rejected."""

from .test_replacement_venue import A, R1_BODY, echo_insert, lookups, table


# --- TC-BOOKINGS-062 --------------------------------------------------------
def test_rejected_booking_accepts_replacement(client, db):
    lookups(db, [{**A, 'status': 'rejected'}], [], [])
    echo_insert(db)

    response = client.post('/bookings', json=R1_BODY)

    assert response.status_code == 201, response.text
    inserted = table(db).insert.call_args.args[0]
    assert inserted['status'] == 'pending'
    assert inserted['replaces_booking_id'] == A['id']


# --- TC-BOOKINGS-063 --------------------------------------------------------
def test_replaced_booking_still_refuses_replacement(client, db):
    lookups(db, [{**A, 'status': 'replaced'}])

    response = client.post('/bookings', json=R1_BODY)

    assert (response.status_code, response.json()) == (
        409, {'detail': 'This booking can no longer be replaced'}
    )
    table(db).insert.assert_not_called()
