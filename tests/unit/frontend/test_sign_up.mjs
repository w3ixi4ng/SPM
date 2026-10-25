import assert from 'node:assert/strict'
import test from 'node:test'

import { signUp } from '../../../frontend/src/lib/auth.js'
import { SIGN_UP_ROLES, validateSignUp } from '../../../frontend/src/lib/signUp.js'

const FORM = {
  role: '',
  firstName: 'Ada',
  lastName: 'Lovelace',
  email: 'ada@example.com',
  password: 'correct-horse-battery-staple',
  confirmPassword: 'correct-horse-battery-staple',
}

// --- TC-FRONTEND-256 -------------------------------------------------------
test('sign-up offers exactly two roles, none chosen', () => {
  assert.deepEqual(
    SIGN_UP_ROLES.map(({ value, label }) => [value, label]),
    [['attendee', 'Attendee'], ['event_organiser', 'Event Organiser']],
  )
  assert.deepEqual(validateSignUp(FORM), {
    role: "Choose whether you're signing up as an Attendee or an Event Organiser.",
  })
})

// --- TC-FRONTEND-257 -------------------------------------------------------
test('the chosen role is sent with the sign-up', async (t) => {
  const calls = []
  const realFetch = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ id: 'u' }), { status: 201 })
  }
  t.after(() => { globalThis.fetch = realFetch })

  for (const role of ['attendee', 'event_organiser']) {
    assert.deepEqual(validateSignUp({ ...FORM, role }), {})
    await signUp({ name: 'Ada Lovelace', email: FORM.email, password: FORM.password, role })
  }

  assert.equal(calls.length, 2)
  for (const [index, role] of ['attendee', 'event_organiser'].entries()) {
    assert.equal(calls[index].url, '/api/users/signup')
    assert.equal(calls[index].options.method, 'POST')
    assert.deepEqual(JSON.parse(calls[index].options.body), {
      name: 'Ada Lovelace',
      email: 'ada@example.com',
      password: 'correct-horse-battery-staple',
      role,
    })
  }
})
