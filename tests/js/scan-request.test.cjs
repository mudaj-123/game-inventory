const test = require('node:test');
const assert = require('node:assert/strict');
const { webcrypto } = require('node:crypto');
const { uuid, createPending } = require('../../app/static/scan-request.js');
test('same request survives lost response; conflicting next scan is blocked', () => {
  const state = createPending(webcrypto);
  const original = state.begin('00001111', 'IN');
  assert.deepEqual(state.begin('00001111', 'IN'), original);
  assert.throws(() => state.begin('00001111', 'OUT'));
  assert.throws(() => state.begin('00002222', 'IN'));
  state.resolve();
  assert.notEqual(state.begin('00001111', 'IN').client_scan_id, original.client_scan_id);
});
test('LAN HTTP without randomUUID still uses cryptographic UUID v4', () => {
  const value = uuid({ getRandomValues: value => webcrypto.getRandomValues(value) });
  assert.match(value, /^[a-f\d]{8}-[a-f\d]{4}-4[a-f\d]{3}-[89ab][a-f\d]{3}-[a-f\d]{12}$/);
});
