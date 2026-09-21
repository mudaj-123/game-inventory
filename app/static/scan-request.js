"use strict";
((root) => {
  function uuid(crypto) {
    if (crypto.randomUUID) return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  function createPending(crypto) {
    let pending = null;
    return {
      begin(barcode, operation) {
        if (pending && (pending.barcode !== barcode || pending.operation !== operation))
          throw new Error("上一笔结果未确认，请先重试上一笔，或到流水核对后处理。");
        pending ||= { barcode, operation, client_scan_id: uuid(crypto) };
        return { ...pending };
      },
      resolve() { pending = null; },
      get() { return pending && { ...pending }; },
    };
  }
  root.ScanRequest = { uuid, createPending };
  if (typeof module !== "undefined") module.exports = root.ScanRequest;
})(globalThis);
