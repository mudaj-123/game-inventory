"use strict";

(() => {
  const shell = document.querySelector(".app-shell");
  const homePanel = document.querySelector("#home-panel");
  const scanPanel = document.querySelector("#scan-panel");
  const modeTitle = document.querySelector("#mode-title");
  const scannerInput = document.querySelector("#scanner-input");
  const readyState = document.querySelector("#ready-state");
  const result = document.querySelector("#result");
  const networkStatus = document.querySelector("#network-status");
  const manualForm = document.querySelector("#manual-form");
  const manualBarcode = document.querySelector("#manual-barcode");
  const unknownForm = document.querySelector("#unknown-form");
  const unknownBarcode = document.querySelector("#unknown-barcode");
  const unknownGameName = document.querySelector("#unknown-game-name");
  const loginPanel = document.querySelector("#login-panel");
  const sessionBar = document.querySelector("#session-bar");
  const transactionsPanel = document.querySelector("#transactions-panel");
  let csrfToken = null;
  let mode = null;
  let keyBuffer = "";
  let submitting = false;
  let unknownScanId = null;

  const showLogin = () => {
    csrfToken = null;
    loginPanel.hidden = false;
    homePanel.hidden = true;
    scanPanel.hidden = true;
    transactionsPanel.hidden = true;
    sessionBar.hidden = true;
    document.querySelector("#login-username").focus();
  };

  const apiFetch = async (url, options = {}) => {
    options.credentials = "same-origin";
    options.cache = "no-store";
    options.headers = { ...(options.headers || {}), ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}) };
    const response = await fetch(url, options);
    if (response.status === 401) showLogin();
    return response;
  };

  const showHome = (user) => {
    loginPanel.hidden = true; sessionBar.hidden = false; homePanel.hidden = false;
    document.querySelector("#current-user").textContent = `${user.username} · ${user.role}`;
  };

  document.querySelector("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const response = await apiFetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: document.querySelector("#login-username").value,
        password: document.querySelector("#login-password").value }) });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) { document.querySelector("#login-error").textContent = payload.detail || "登录失败"; return; }
    csrfToken = payload.csrf_token;
    document.querySelector("#login-password").value = "";
    showHome(payload);
  });

  document.querySelector("#logout").addEventListener("click", async () => {
    await apiFetch("/api/auth/logout", { method: "POST" }); showLogin();
  });

  const focusScanner = () => {
    if (mode && manualForm.hidden && unknownForm.hidden && !submitting) {
      scannerInput.focus({ preventScroll: true });
      readyState.textContent = "扫码枪已就绪";
    }
  };

  const showResult = (message, state = "info") => {
    result.textContent = message;
    result.dataset.state = state;
  };

  const speak = (message) => {
    if (!("speechSynthesis" in window)) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(message);
      utterance.lang = "zh-CN";
      window.speechSynthesis.speak(utterance);
    } catch (_error) {
      // 语音是辅助反馈；浏览器拒绝播报时不能影响库存请求。
    }
  };

  const updateNetwork = () => {
    const online = navigator.onLine;
    networkStatus.textContent = online ? "● 在线" : "○ 离线";
    networkStatus.dataset.online = String(online);
    if (!online && mode === "OUT") {
      showResult("当前离线，禁止出库", "error");
    }
  };

  const submitBarcode = async (rawBarcode) => {
    const barcode = rawBarcode.trim();
    if (!/^[0-9]{8,14}$/.test(barcode)) {
      const message = "条码无效，请扫描 8～14 位数字";
      showResult(message, "error");
      speak(message);
      focusScanner();
      return;
    }
    if (!navigator.onLine) {
      const message = mode === "OUT" ? "当前离线，禁止出库" : "当前离线，无法提交入库";
      showResult(message, "error");
      speak(message);
      focusScanner();
      return;
    }

    submitting = true;
    readyState.textContent = "正在提交…";
    showResult(`正在处理条码 ${barcode}…`);
    try {
      const clientScanId = crypto.randomUUID();
      const response = await apiFetch("/api/scans", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barcode, operation: mode, client_scan_id: clientScanId }),
      });
      const payload = await response.json().catch(() => ({}));
      const message = payload.message || payload.detail || "扫码处理失败";
      if (payload.status === "SUCCESS") {
        showResult(message, "success");
        speak(message);
      } else if (payload.status === "OUT_OF_STOCK") {
        showResult(message, "error");
        speak(message);
      } else if (payload.status === "UNKNOWN_BARCODE_REQUIRES_INPUT") {
        showResult(message, "error");
        unknownScanId = clientScanId;
        unknownBarcode.value = payload.barcode || barcode;
        unknownForm.hidden = false;
        unknownGameName.focus();
      } else {
        // OUT_OF_STOCK and every unknown business status are failures even on HTTP 200.
        showResult(message, "error");
        speak(message);
      }
    } catch (_error) {
      const message = "网络请求失败，请检查连接后重试";
      showResult(message, "error");
      speak(message);
    } finally {
      submitting = false;
      scannerInput.value = "";
      keyBuffer = "";
      readyState.textContent = "扫码枪已就绪";
      focusScanner();
    }
  };

  const closeUnknownForm = () => {
    unknownForm.reset();
    unknownForm.hidden = true;
    unknownScanId = null;
    focusScanner();
  };

  unknownForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!unknownScanId || submitting) return;
    submitting = true;
    const fields = new FormData(unknownForm);
    const body = {
      barcode: String(fields.get("barcode")),
      operation: "IN",
      client_scan_id: unknownScanId,
      game_name: String(fields.get("game_name")).trim(),
      platform: String(fields.get("platform")),
      region: String(fields.get("region")).trim() || "UNKNOWN",
      edition: String(fields.get("edition")).trim() || null,
    };
    try {
      const response = await apiFetch("/api/scans/resolve-unknown", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await response.json().catch(() => ({}));
      if (payload.status === "SUCCESS") {
        const message = `${payload.game_name}（${payload.platform}），入库成功，当前库存 ${payload.quantity_after} 件。`;
        showResult(message, "success");
        speak(message);
        closeUnknownForm();
      } else {
        const message = payload.message || payload.detail || "未知条码补录失败";
        showResult(message, "error");
        speak(message);
      }
    } catch (_error) {
      const message = "网络请求失败，请检查连接后重试";
      showResult(message, "error");
      speak(message);
    } finally {
      submitting = false;
      if (unknownForm.hidden) focusScanner(); else unknownGameName.focus();
    }
  });

  document.querySelector("#unknown-cancel").addEventListener("click", closeUnknownForm);

  const finishBufferedScan = () => {
    const barcode = keyBuffer || scannerInput.value;
    keyBuffer = "";
    scannerInput.value = "";
    if (barcode) void submitBarcode(barcode);
  };

  document.querySelectorAll("[data-mode-button]").forEach((button) => {
    button.addEventListener("click", () => {
      mode = button.dataset.modeButton;
      shell.dataset.mode = mode.toLowerCase();
      modeTitle.textContent = mode === "IN" ? "📦 连续入库" : "💰 连续出库";
      homePanel.hidden = true;
      scanPanel.hidden = false;
      showResult("请扫描 8～14 位商品条码");
      focusScanner();
    });
  });

  document.addEventListener("keydown", (event) => {
    if (!mode || !manualForm.hidden || !unknownForm.hidden || submitting) return;
    if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      finishBufferedScan();
    } else if (/^[0-9]$/.test(event.key)) {
      // 页面级缓冲保证焦点偶然丢失时 HID 扫码仍可完成。
      if (document.activeElement !== scannerInput) keyBuffer += event.key;
    }
  });

  scannerInput.addEventListener("input", () => { keyBuffer = ""; });
  document.querySelector("#restore-focus").addEventListener("click", focusScanner);
  document.querySelector("#exit-scan").addEventListener("click", () => {
    mode = null;
    scanPanel.hidden = true;
    homePanel.hidden = false;
    shell.dataset.mode = "home";
  });
  document.querySelector("#manual-toggle").addEventListener("click", () => {
    manualForm.hidden = !manualForm.hidden;
    if (manualForm.hidden) focusScanner(); else manualBarcode.focus();
  });
  manualForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const barcode = manualBarcode.value;
    manualBarcode.value = "";
    manualForm.hidden = true;
    void submitBarcode(barcode);
  });
  scanPanel.addEventListener("click", (event) => {
    if (!event.target.closest("button, input, form")) focusScanner();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") focusScanner();
  });
  window.addEventListener("online", updateNetwork);
  window.addEventListener("offline", updateNetwork);
  updateNetwork();

  const transactionList = document.querySelector("#transaction-list");
  const transactionFeedback = document.querySelector("#transaction-feedback");
  const transactionStats = document.querySelector("#transaction-stats");
  const reverseDialog = document.querySelector("#reverse-dialog");
  const reverseConfirmDetails = document.querySelector("#reverse-confirm-details");
  let transactionItems = [];
  let transactionGroups = [];
  let transactionFilter = "ALL";
  let pendingReverseItem = null;
  let reversingTransactionId = null;
  let preferredOpenTransactionId = null;

  const shanghaiFormatter = (withDate = false) => new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", ...(withDate ? { year: "numeric", month: "2-digit", day: "2-digit" } : {}),
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });
  const formatTime = (value, withDate = false) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "时间未知" : shanghaiFormatter(withDate).format(date).replaceAll("/", "-");
  };
  const operationLabel = (operation) => operation === "IN" ? "入库" : operation === "SALE_OUT" ? "出库" : "撤销";
  const signed = (value) => `${Number(value) > 0 ? "+" : ""}${Number(value) || 0}`;
  const appendText = (parent, tag, text, className = "") => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    parent.append(element);
    return element;
  };

  const renderReversal = (reversal) => {
    const child = document.createElement("div"); child.className = "reversal-record";
    appendText(child, "strong", `↳ 撤销流水 #${reversal.transaction_id ?? "?"}`);
    appendText(child, "p", `${formatTime(reversal.created_at)} · 操作人：${reversal.username ?? "未知"}`);
    appendText(child, "p", `库存 ${reversal.quantity_before ?? "?"} → ${reversal.quantity_after ?? "?"} · 原流水 #${reversal.related_transaction_id ?? "?"}`);
    return child;
  };

  const requestReverse = (item) => {
    if (!item.can_reverse || reversingTransactionId !== null) return;
    pendingReverseItem = item;
    reverseConfirmDetails.replaceChildren();
    const fields = [
      ["流水编号", `#${item.transaction_id}`], ["商品", item.game_name ?? "未知商品"],
      ["平台", item.platform ?? "未知平台"], ["条码", item.barcode ?? "未知条码"],
      ["操作", operationLabel(item.operation_type)],
      ["库存记录", `${item.quantity_before ?? "?"} → ${item.quantity_after ?? "?"}`],
      ["操作时间", formatTime(item.created_at, true)], ["操作人", item.username ?? "未知用户"],
    ];
    fields.forEach(([label, value]) => {
      appendText(reverseConfirmDetails, "dt", label);
      appendText(reverseConfirmDetails, "dd", value);
    });
    reverseDialog.showModal();
  };

  const renderTransactionDetail = (item) => {
    const detail = document.createElement("article"); detail.className = "transaction-detail";
    const heading = document.createElement("div"); heading.className = "transaction-detail-heading";
    appendText(heading, "strong", `#${item.transaction_id ?? "?"}`);
    appendText(heading, "time", formatTime(item.created_at));
    detail.append(heading);
    appendText(detail, "p", `${operationLabel(item.operation_type)} · 库存 ${item.quantity_before ?? "?"} → ${item.quantity_after ?? "?"} · 变化 ${signed(item.quantity_delta)}`);
    appendText(detail, "p", `操作人：${item.username ?? "未知"}`);
    appendText(detail, "p", `条码：${item.barcode ?? "未知"}`, "break-text");
    if (item.reversals?.length || item.reversed) appendText(detail, "span", "状态：已撤销", "reversed-badge");
    if (item.can_reverse) {
      const button = appendText(detail, "button", reversingTransactionId === item.transaction_id ? "正在撤销…" : "撤销此笔", "danger-button reverse-item-button");
      button.type = "button";
      button.disabled = reversingTransactionId === item.transaction_id;
      button.addEventListener("click", () => requestReverse(item));
    } else {
      appendText(detail, "p", item.reverse_block_reason || "当前不可撤销", "reverse-block-reason");
    }
    (item.reversals || []).forEach((reversal) => detail.append(renderReversal(reversal)));
    return detail;
  };

  const renderGroup = (group) => {
    const details = document.createElement("details"); details.className = "transaction-group";
    if (group.items.some((item) => item.transaction_id === preferredOpenTransactionId)) details.open = true;
    const summary = document.createElement("summary");
    appendText(summary, "strong", `${group.game_name} · ${group.platform}`, "group-title");
    if (group.is_orphan_reversal_group) {
      appendText(summary, "span", `${group.items.length}笔记录 · 需要审计`, "group-line orphan-label");
    } else {
      appendText(summary, "span", `${operationLabel(group.operation_type)} ${group.transaction_count}笔 · 库存轨迹 ${group.first_quantity_before} → ${group.last_original_quantity_after}`, "group-line");
      appendText(summary, "span", `${formatTime(group.started_at, true)}–${formatTime(group.ended_at)} · ${group.username}`, "group-line");
      appendText(summary, "span", group.reversed_count ? `已撤销${group.reversed_count}笔 · 本组有效净变化 ${signed(group.active_delta_total)}` : `净变化 ${signed(group.original_delta_total)}`, "group-line group-net");
      appendText(summary, "span", `查看${group.transaction_count}条明细`, "group-expand");
    }
    details.append(summary);
    const body = document.createElement("div"); body.className = "group-details";
    if (group.is_orphan_reversal_group) group.items.forEach((item) => body.append(renderReversal(item)));
    else group.items.forEach((item) => body.append(renderTransactionDetail(item)));
    details.append(body);
    return details;
  };

  const renderTransactions = () => {
    const visible = transactionGroups.filter((group) => transactionFilter === "ALL"
      || group.operation_type === transactionFilter
      || (transactionFilter === "REVERSED" && (group.reversed_count > 0 || group.is_orphan_reversal_group)));
    const originals = transactionGroups.reduce((sum, group) => sum + group.transaction_count, 0);
    const reversed = transactionGroups.reduce((sum, group) => sum + group.reversed_count, 0);
    transactionStats.textContent = `共${transactionGroups.length}个连续操作组，${originals}笔原始操作，${reversed}笔已撤销`;
    if (!visible.length) {
      const empty = appendText(document.createDocumentFragment(), "p", transactionItems.length ? "当前筛选没有流水" : "今日暂无流水", "transaction-empty");
      transactionList.replaceChildren(empty);
      return;
    }
    transactionList.replaceChildren(...visible.map(renderGroup));
  };

  const loadAllTransactions = async ({ feedback = "" } = {}) => {
    transactionFeedback.className = "transaction-feedback loading";
    transactionFeedback.textContent = "正在加载流水…";
    transactionList.replaceChildren();
    const all = [];
    try {
      let page = 1;
      let total = Number.POSITIVE_INFINITY;
      while (all.length < total && page <= 50 && all.length < 5000) {
        const response = await apiFetch(`/api/transactions?page=${page}&page_size=100`);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.detail || "读取流水失败");
        const pageItems = Array.isArray(payload.items) ? payload.items : [];
        total = Number.isFinite(Number(payload.total)) ? Number(payload.total) : all.length + pageItems.length;
        all.push(...pageItems);
        if (!pageItems.length || all.length >= total) break;
        page += 1;
      }
      transactionItems = all.slice(0, 5000);
      transactionGroups = globalThis.TransactionGroups.groupTransactions(transactionItems);
      const truncated = transactionItems.length < total;
      transactionFeedback.className = `transaction-feedback ${truncated ? "warning" : "success"}`;
      transactionFeedback.textContent = truncated ? `已达到安全上限，仅加载 ${transactionItems.length} 条流水，请联系管理员审计。` : feedback;
      renderTransactions();
    } catch (error) {
      transactionFeedback.className = "transaction-feedback error";
      transactionFeedback.textContent = error.message || "读取流水失败";
      const retry = appendText(transactionList, "button", "重新加载", "secondary-button retry-button");
      retry.type = "button"; retry.addEventListener("click", () => void loadAllTransactions());
    }
  };

  document.querySelector("#transactions-button").addEventListener("click", () => {
    homePanel.hidden = true; transactionsPanel.hidden = false;
    void loadAllTransactions();
  });
  document.querySelector("#transaction-filters").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-filter]");
    if (!button) return;
    transactionFilter = button.dataset.filter;
    document.querySelectorAll("#transaction-filters button").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    renderTransactions();
  });
  document.querySelector("#transactions-back").addEventListener("click", () => {
    transactionsPanel.hidden = true; homePanel.hidden = false;
  });
  reverseDialog.addEventListener("close", async () => {
    if (reverseDialog.returnValue !== "confirm" || !pendingReverseItem || reversingTransactionId !== null) {
      pendingReverseItem = null; return;
    }
    const item = pendingReverseItem;
    pendingReverseItem = null;
    reversingTransactionId = item.transaction_id;
    preferredOpenTransactionId = item.transaction_id;
    renderTransactions();
    try {
      const response = await apiFetch(`/api/transactions/${item.transaction_id}/reverse`, { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      const message = response.ok ? (payload.message || "撤销成功") : (payload.detail || "撤销失败");
      if (response.ok) speak(message);
      await loadAllTransactions({ feedback: message });
      if (!response.ok) transactionFeedback.className = "transaction-feedback error";
    } catch (_error) {
      await loadAllTransactions({ feedback: "网络请求失败，流水已重新加载" });
      transactionFeedback.className = "transaction-feedback error";
    } finally {
      reversingTransactionId = null;
      renderTransactions();
    }
  });

  void apiFetch("/api/auth/me").then(async (response) => {
    if (response.ok) { const user = await response.json(); csrfToken = user.csrf_token; showHome(user); } else showLogin();
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", async () => {
      const registration = await navigator.serviceWorker.register("/service-worker.js", { scope: "/" });
      registration.addEventListener("updatefound", () => {
        const worker = registration.installing;
        worker?.addEventListener("statechange", () => {
          if (worker.state === "installed" && navigator.serviceWorker.controller) {
            document.querySelector("#update-notice").hidden = false;
          }
        });
      });
      document.querySelector("#apply-update").addEventListener("click", () => {
        registration.waiting?.postMessage({ type: "SKIP_WAITING" });
      });
      navigator.serviceWorker.addEventListener("controllerchange", () => window.location.reload());
    });
  }
})();
