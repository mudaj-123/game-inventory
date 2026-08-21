"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { groupTransactions } = require("../../app/static/transaction-groups.js");

const tx = (id, overrides = {}) => ({
  transaction_id: id, game_name: "塞尔达", barcode: "00001234", platform: "SWITCH",
  operation_type: "IN", username: "admin", created_at: new Date(Date.UTC(2026, 6, 30, 9, 0, id)).toISOString(),
  quantity_before: id - 1, quantity_after: id, quantity_delta: 1, reversed: false,
  related_transaction_id: null, can_reverse: true, reverse_block_reason: null, ...overrides,
});

test("nine consecutive inbound operations become one group with a 0 to 9 trail", () => {
  const groups = groupTransactions(Array.from({ length: 9 }, (_, index) => tx(index + 1,
    { quantity_before: index, quantity_after: index + 1 })));
  assert.equal(groups.length, 1); assert.equal(groups[0].transaction_count, 9);
  assert.equal(groups[0].first_quantity_before, 0); assert.equal(groups[0].last_original_quantity_after, 9);
});

test("barcode, direction and user changes create groups", () => {
  assert.equal(groupTransactions([tx(1), tx(2, { barcode: "99999999" })]).length, 2);
  assert.equal(groupTransactions([tx(1), tx(2, { operation_type: "SALE_OUT", quantity_delta: -1 })]).length, 2);
  assert.equal(groupTransactions([tx(1), tx(2, { username: "staff" })]).length, 2);
});

test("a gap over ten minutes creates a group", () => {
  assert.equal(groupTransactions([tx(1), tx(2, { created_at: "2026-07-30T09:11:00Z" })]).length, 2);
});

test("an intervening product prevents non-adjacent operations from merging", () => {
  const groups = groupTransactions([tx(1), tx(2, { barcode: "99999999" }), tx(3)]);
  assert.equal(groups.length, 3);
});

test("reversal interrupts grouping, attaches, and updates active totals", () => {
  const reversal = tx(3, { operation_type: "REVERSAL", related_transaction_id: 1,
    quantity_delta: -1, quantity_before: 2, quantity_after: 1 });
  const groups = groupTransactions([tx(1), tx(2), reversal, tx(4)]);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].items[0].reversals[0].transaction_id, 3);
  assert.equal(groups[0].reversed_count, 1); assert.equal(groups[0].active_count, 1);
  assert.equal(groups[0].active_delta_total, 1); assert.equal(groups[0].original_delta_total, 2);
});

test("orphan reversals are retained in an audit group", () => {
  const groups = groupTransactions([tx(1, { operation_type: "REVERSAL", related_transaction_id: 99 })]);
  assert.equal(groups.length, 1); assert.equal(groups[0].is_orphan_reversal_group, true);
  assert.equal(groups[0].items[0].transaction_id, 1);
});

test("does not mutate input and tolerates invalid timestamps", () => {
  const input = [tx(2), tx(1, { created_at: "invalid" })];
  const snapshot = structuredClone(input);
  assert.doesNotThrow(() => groupTransactions(input));
  assert.deepEqual(input, snapshot);
});
