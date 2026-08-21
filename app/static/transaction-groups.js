"use strict";

(function expose(factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof globalThis !== "undefined") globalThis.TransactionGroups = api;
})(() => {
  const DEFAULT_GAP_MS = 10 * 60 * 1000;
  const timestamp = (item) => {
    const value = Date.parse(item?.created_at);
    return Number.isFinite(value) ? value : null;
  };
  const compare = (left, right) => {
    const leftTime = timestamp(left);
    const rightTime = timestamp(right);
    if (leftTime === null && rightTime !== null) return 1;
    if (leftTime !== null && rightTime === null) return -1;
    if (leftTime !== rightTime) return (leftTime ?? 0) - (rightTime ?? 0);
    return Number(left?.transaction_id || 0) - Number(right?.transaction_id || 0);
  };

  const summarize = (items, groupKey) => {
    const first = items[0];
    const reversedCount = items.filter((item) => item.reversals.length > 0 || item.reversed).length;
    return {
      group_key: groupKey,
      game_name: first.game_name ?? "未知商品",
      barcode: first.barcode ?? "未知条码",
      platform: first.platform ?? "未知平台",
      operation_type: first.operation_type,
      username: first.username ?? "未知用户",
      started_at: first.created_at ?? null,
      ended_at: items.at(-1)?.created_at ?? null,
      transaction_count: items.length,
      reversed_count: reversedCount,
      active_count: items.length - reversedCount,
      first_quantity_before: first.quantity_before,
      last_original_quantity_after: items.at(-1)?.quantity_after,
      original_delta_total: items.reduce((sum, item) => sum + Number(item.quantity_delta || 0), 0),
      active_delta_total: items.reduce(
        (sum, item) => sum + (item.reversals.length > 0 || item.reversed ? 0 : Number(item.quantity_delta || 0)), 0,
      ),
      items,
      is_orphan_reversal_group: false,
    };
  };

  function groupTransactions(input, options = {}) {
    const maxGapMs = Number.isFinite(options.maxGapMs) ? options.maxGapMs : DEFAULT_GAP_MS;
    const sorted = Array.isArray(input) ? [...input].sort(compare) : [];
    const originals = new Set(sorted.filter((item) => item.operation_type !== "REVERSAL")
      .map((item) => Number(item.transaction_id)));
    const reversalsByOriginalId = new Map();
    const orphans = [];
    for (const item of sorted) {
      if (item.operation_type !== "REVERSAL") continue;
      const relatedId = Number(item.related_transaction_id);
      if (!Number.isFinite(relatedId) || !originals.has(relatedId)) {
        orphans.push({ ...item });
        continue;
      }
      const attached = reversalsByOriginalId.get(relatedId) || [];
      attached.push({ ...item });
      reversalsByOriginalId.set(relatedId, attached);
    }

    const groups = [];
    let current = [];
    let previousSequenceItem = null;
    const flush = () => {
      if (!current.length) return;
      groups.push(summarize(current, `group-${current[0].transaction_id}`));
      current = [];
    };
    for (const sequenceItem of sorted) {
      if (sequenceItem.operation_type === "REVERSAL") {
        flush();
        previousSequenceItem = sequenceItem;
        continue;
      }
      const item = { ...sequenceItem,
        reversals: reversalsByOriginalId.get(Number(sequenceItem.transaction_id)) || [] };
      const previous = current.at(-1);
      const currentTime = timestamp(item);
      const previousTime = timestamp(previous);
      const continuous = Boolean(previous) && previousSequenceItem?.operation_type !== "REVERSAL";
      const joins = continuous && item.barcode === previous.barcode
        && item.operation_type === previous.operation_type && item.username === previous.username
        && currentTime !== null && previousTime !== null
        && currentTime - previousTime >= 0 && currentTime - previousTime <= maxGapMs;
      if (!joins) flush();
      current.push(item);
      previousSequenceItem = sequenceItem;
    }
    flush();
    if (orphans.length) {
      groups.push({
        group_key: `orphan-reversals-${orphans.map((item) => item.transaction_id).join("-")}`,
        game_name: "无法关联的撤销记录", barcode: "—", platform: "—",
        operation_type: "REVERSAL", username: "—", started_at: orphans[0].created_at ?? null,
        ended_at: orphans.at(-1)?.created_at ?? null, transaction_count: 0,
        reversed_count: 0, active_count: 0, first_quantity_before: null,
        last_original_quantity_after: null, original_delta_total: 0, active_delta_total: 0,
        items: orphans, orphan_reversals: orphans, is_orphan_reversal_group: true,
      });
    }
    return groups;
  }
  return { groupTransactions };
});
