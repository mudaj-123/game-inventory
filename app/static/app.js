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
  const pendingScan = globalThis.ScanRequest.createPending(crypto);
  let csrfToken = null;
  let mode = null;
  let keyBuffer = "";
  let submitting = false;
  let unknownScanId = null;

  const showLogin = () => {
    mode = null;
    reportGeneration += 1;
    productGeneration += 1;
    for (const id of ["product-list", "product-summary", "alert-list", "pending-products", "admin-feedback"]) document.querySelector(`#${id}`).replaceChildren();
    document.querySelector("#reports-panel").hidden = true;
    document.querySelector("#report-results").replaceChildren();
    document.querySelector("#admin-panel").hidden = true;
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
    document.querySelector("#admin-button").hidden = user.role !== "ADMIN";
    document.querySelector("#reports-button").hidden = user.role !== "ADMIN";
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
    if (submitting) return;
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
      const request = pendingScan.begin(barcode, mode);
      const clientScanId = request.client_scan_id;
      const response = await apiFetch("/api/scans", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const payload = await response.json().catch(() => ({}));
      if (response.status < 500 && payload.status) pendingScan.resolve();
      const labels = { SOLD_OUT: "已售罄", LOW_STOCK: "库存偏低", OVERSTOCK: "库存积压", STALE_STOCK: "长期未销售" };
      const warnings = (payload.alerts || []).map(kind => labels[kind] || kind).join("、");
      const message = (payload.message || payload.detail || "扫码处理失败") + (warnings ? ` 提醒：${warnings}` : "");
      if (payload.status === "SUCCESS") {
        showResult(message, "success");
        speak(message);
      } else if (payload.status === "OUT_OF_STOCK") {
        showResult(message, "error");
        speak(message);
      } else if (payload.status === "UNKNOWN_BARCODE_REQUIRES_INPUT") {
        showResult(message, "error");
        if (mode === "OUT") {
          showResult("未登记商品，无法出库。请先核对条码并切换入库登记。", "error");
          return;
        }
        unknownScanId = clientScanId;
        unknownBarcode.value = payload.barcode || barcode;
        unknownForm.hidden = false;
        unknownGameName.focus();
      } else {
        // OUT_OF_STOCK and every unknown business status are failures even on HTTP 200.
        showResult(message, "error");
        speak(message);
      }
    } catch (error) {
      const message = pendingScan.get() ? "上一笔结果未确认，请点击重试上一笔。不要刷新页面，请先核对流水。" : (error.message || "网络请求失败，请检查连接后重试");
      showResult(message, "error");
      speak(message);
    } finally {
      submitting = false;
      scannerInput.value = "";
      keyBuffer = "";
      readyState.textContent = "扫码枪已就绪";
      document.querySelector("#retry-scan").hidden = !pendingScan.get();
      focusScanner();
    }
  };

  document.querySelector("#retry-scan").addEventListener("click", () => {
    const pending = pendingScan.get();
    if (pending) { mode = pending.operation; void submitBarcode(pending.barcode); }
  });
  window.addEventListener("beforeunload", (event) => {
    if (pendingScan.get()) { event.preventDefault(); event.returnValue = ""; }
  });

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
    } catch (error) {
      const message = pendingScan.get() ? "上一笔结果未确认，请点击重试上一笔。不要刷新页面，请先核对流水。" : (error.message || "网络请求失败，请检查连接后重试");
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

  let productPage = 1;
  let productGeneration = 0;
  let productQuery = new URLSearchParams();
  let adjustmentPending = null;
  let reportPage = 1;
  let reportGeneration = 0;
  let reportQuery = new URLSearchParams({ period: "7d" });
  const reportPanel = document.querySelector("#reports-panel");
  const reportStatus = document.querySelector("#report-status");
  const reportResults = document.querySelector("#report-results");
  const reportPrev = document.querySelector("#report-prev");
  const reportNext = document.querySelector("#report-next");
  const loadReport = async () => {
    const generation = ++reportGeneration;
    reportPrev.disabled = true; reportNext.disabled = true;
    reportResults.replaceChildren(); reportStatus.textContent = "正在统计…";
    try {
      const query = new URLSearchParams(reportQuery);
      query.set("page", String(reportPage));
      const response = await apiFetch(`/api/admin/reports/sales?${query}`);
      const data = await response.json();
      if (generation !== reportGeneration || reportPanel.hidden) return;
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请检查日期范围（最多 366 天）");
      reportStatus.textContent = `${data.start} 至 ${data.end} · ${data.timezone} · 出库 ${data.totals.sold} · 撤销 ${data.totals.reversed} · 净出库 ${data.totals.net}`;
      const table = (title, headings, rows) => {
        const heading = document.createElement("h3"); heading.textContent = title;
        const container = document.createElement("div"); container.className = "report-table-scroll";
        const element = document.createElement("table");
        const caption = document.createElement("caption"); caption.textContent = title;
        element.append(caption);
        const head = element.createTHead().insertRow();
        for (const text of headings) { const cell = document.createElement("th"); cell.scope = "col"; cell.textContent = text; head.append(cell); }
        const body = element.createTBody();
        for (const values of rows) { const row = body.insertRow(); for (const value of values) row.insertCell().textContent = String(value); }
        container.append(element); reportResults.append(heading, container);
      };
      table("每日件数", ["日期", "出库", "撤销", "净出库"], data.daily.map(r => [r.date, r.sold, r.reversed, r.net]));
      table("平台件数", ["平台", "出库", "撤销", "净出库"], data.platforms.map(r => [r.platform, r.sold, r.reversed, r.net]));
      table(`游戏销量 · 第 ${data.page} 页 · 共 ${data.game_total} 项（按出库件数降序）`, ["游戏", "条码", "平台", "出库", "撤销", "净出库"], data.games.map(r => [r.game_name, r.barcode, r.platform, r.sold, r.reversed, r.net]));
      if (!data.game_total) { const empty = document.createElement("p"); empty.textContent = "所选期间没有销售或销售撤销记录。"; reportResults.append(empty); }
      reportPrev.disabled = reportPage <= 1;
      reportNext.disabled = data.page * data.page_size >= data.game_total;
    } catch (error) {
      if (generation === reportGeneration && !reportPanel.hidden) reportStatus.textContent = error.message;
    }
  };
  document.querySelector("#reports-button").addEventListener("click", () => {
    homePanel.hidden = true; reportPanel.hidden = false; reportPage = 1; void loadReport();
  });
  document.querySelector("#reports-back").addEventListener("click", () => {
    reportGeneration += 1; reportPanel.hidden = true; homePanel.hidden = false;
  });
  document.querySelector("#report-period").addEventListener("change", (event) => {
    const custom = event.target.value === "custom";
    document.querySelector("#report-dates").hidden = !custom;
    document.querySelector("#report-start").required = custom;
    document.querySelector("#report-end").required = custom;
  });
  document.querySelector("#reports-form").addEventListener("submit", (event) => {
    event.preventDefault();
    reportQuery = new URLSearchParams({ period: document.querySelector("#report-period").value });
    if (reportQuery.get("period") === "custom") {
      reportQuery.set("start", document.querySelector("#report-start").value);
      reportQuery.set("end", document.querySelector("#report-end").value);
    }
    reportPage = 1; void loadReport();
  });
  reportPrev.addEventListener("click", () => { reportPage -= 1; void loadReport(); });
  reportNext.addEventListener("click", () => { reportPage += 1; void loadReport(); });

  const adminFeedback = document.querySelector("#admin-feedback");
  const loadProducts = async () => {
    const generation = ++productGeneration;
    const summary = document.querySelector("#product-summary");
    document.querySelector("#products-prev").disabled = true;
    document.querySelector("#products-next").disabled = true;
    document.querySelector("#product-list").replaceChildren();
    summary.textContent = "正在查询…";
    try {
      const query = new URLSearchParams(productQuery); query.set("page", String(productPage));
      const response = await apiFetch(`/api/admin/products?${query}`);
      const payload = await response.json();
      if (generation !== productGeneration || document.querySelector("#admin-panel").hidden) return;
      if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "查询失败，请检查筛选条件及日期范围");
      summary.textContent = `共 ${payload.total} 项 · 第 ${payload.page} 页 · ${payload.start} 至 ${payload.end} · ${payload.timezone}`;
      const list = document.querySelector("#product-list"); list.replaceChildren();
      for (const p of payload.items) {
        const item = document.createElement("article");
        const label = document.createElement("p"); label.textContent = `${p.game_name} · ${p.platform} · ${p.barcode} · 库存 ${p.quantity}`;
        const cover = document.createElement("div"); cover.className = "product-cover"; cover.textContent = "暂无封面";
        if (p.cover_url) {
          const image = document.createElement("img"); image.src = p.cover_url; image.alt = `${p.game_name}封面`; image.loading = "lazy";
          image.addEventListener("error", () => { cover.textContent = "暂无封面"; }, { once: true });
          cover.replaceChildren(image);
        }
        const details = document.createElement("p");
        const states = { normal: "正常", low: "低库存", sold_out: "售罄", overstock: "库存偏多", stale: "长期无销售", pending: "待核实" };
        const lastSale = p.last_sale_at ? new Date(p.last_sale_at).toLocaleString("zh-CN", { timeZone: payload.timezone }) : "从未销售";
        details.textContent = `${p.region} · ${p.edition || "标准版/未填写"} · ${p.states.map(state => states[state]).join("、") || "无活动预警"}${p.active ? "" : " · 已停用"} · 期间出库 ${p.period_sales} 件 · 期间入库 ${p.period_inbound} 件 · 最近销售：${lastSale}`;
        const button = document.createElement("button"); button.textContent = "调整库存"; button.type = "button";
        button.addEventListener("click", async () => {
          if (adjustmentPending && adjustmentPending.productId !== p.id) {
            adminFeedback.textContent = "请先重试上一件商品的调整，核对流水后再继续。"; return;
          }
          if (!adjustmentPending) {
            const value = prompt("调整数量（增加填正数，减少填负数）：");
            if (value === null) return;
            const delta = Number(value);
            if (!Number.isInteger(delta) || !delta) return;
            const reason = prompt("请填写调整原因："); if (!reason?.trim()) return;
            adjustmentPending = { productId: p.id, body: { quantity_delta: delta, reason: reason.trim(), client_scan_id: globalThis.ScanRequest.uuid(crypto) } };
          }
          button.disabled = true;
          try {
            const response = await apiFetch(`/api/admin/products/${p.id}/adjust`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(adjustmentPending.body) });
            const body = await response.json();
            if (response.status < 500) adjustmentPending = null;
            if (!response.ok) throw new Error(body.detail || "调整失败");
            adminFeedback.textContent = `调整完成，当前库存 ${body.quantity_after}`;
            await loadProducts(); await loadAlerts();
          } catch (error) { adminFeedback.textContent = adjustmentPending ? "结果未确认，请再次点击同一商品的调整按钮重试；不要刷新。" : error.message; }
          finally { button.disabled = false; }
        });
        const edit = document.createElement("button"); edit.type = "button"; edit.textContent = "核实/编辑资料";
        edit.addEventListener("click", async () => {
          const name = prompt("商品名：", p.game_name); if (!name?.trim()) return;
          const platform = prompt("平台（PS5/PS4/SWITCH/SWITCH2）：", p.platform); if (!platform) return;
          const low = prompt("低库存下限：", String(p.low_stock_threshold)); if (low === null) return;
          const high = prompt("积压上限（留空不设上限）：", p.overstock_threshold === null ? "" : String(p.overstock_threshold)); if (high === null) return;
          try {
            const response = await apiFetch(`/api/admin/products/${p.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ game_name: name.trim(), platform, low_stock_threshold: Number(low), overstock_threshold: high.trim() ? Number(high) : null }) });
            if (!response.ok) throw new Error("保存失败，请核对平台及非负整数阈值");
            adminFeedback.textContent = "资料已核实，历史流水快照保留。";
            await loadProducts(); await loadAlerts();
          } catch (error) { adminFeedback.textContent = error.message; }
        });
        item.append(cover, label, details, button, edit); list.append(item);
      }
      document.querySelector("#products-prev").disabled = productPage <= 1;
      document.querySelector("#products-next").disabled = productPage * payload.page_size >= payload.total;
      if (!payload.items.length) list.textContent = "没有符合条件的商品。";
    } catch (error) {
      if (generation === productGeneration && !document.querySelector("#admin-panel").hidden) summary.textContent = error.message;
    }
  };
  const loadAlerts = async () => {
    const generation = productGeneration;
    try {
      const response = await apiFetch("/api/admin/alerts");
      if (!response.ok) throw new Error("读取预警失败");
      const payload = await response.json();
      if (generation !== productGeneration || document.querySelector("#admin-panel").hidden) return;
      const names = { LOW_STOCK: "低库存", SOLD_OUT: "售罄", OVERSTOCK: "积压", STALE_STOCK: "长期未销售" };
      for (const [id, items] of [["alert-list", payload.items], ["pending-products", payload.pending_products]]) {
        const list = document.querySelector(`#${id}`); list.replaceChildren();
        for (const item of items) {
          const p = document.createElement("p"); p.textContent = `${item.game_name} · ${item.barcode}${item.kind ? ` · ${names[item.kind]} · 库存 ${item.quantity}` : ""}`; list.append(p);
        }
        if (!items.length) list.textContent = "暂无记录";
      }
    } catch (error) { adminFeedback.textContent = error.message; }
  };
  document.querySelector("#admin-button").addEventListener("click", () => {
    homePanel.hidden = true; document.querySelector("#admin-panel").hidden = false;
    void loadProducts(); void loadAlerts();
  });
  document.querySelector("#admin-back").addEventListener("click", () => { productGeneration += 1; document.querySelector("#admin-panel").hidden = true; homePanel.hidden = false; });
  document.querySelector("#admin-refresh").addEventListener("click", loadAlerts);
  document.querySelector("#catalog-import").addEventListener("click", async (event) => {
    event.target.disabled = true;
    try {
      const response = await apiFetch("/api/admin/catalog/import", { method: "POST" });
      const report = await response.json();
      if (!response.ok) throw new Error(report.detail || "导入失败");
      adminFeedback.textContent = `新增 ${report.added}，跳过 ${report.skipped}，冲突 ${report.conflicts}，错误 ${report.error_count}。`;
      for (const error of report.errors || []) adminFeedback.textContent += ` 第 ${error.row} 行：${error.error}；`;
    } catch (error) { adminFeedback.textContent = error.message; }
    finally { event.target.disabled = false; }
  });
  const inventoryForm = document.querySelector("#product-search");
  const toggleInventoryDates = () => {
    const custom = inventoryForm.elements.period.value === "custom";
    document.querySelector("#inventory-dates").hidden = !custom;
    for (const name of ["start", "end"]) { inventoryForm.elements[name].disabled = !custom; inventoryForm.elements[name].required = custom; }
  };
  document.querySelector("#inventory-period").addEventListener("change", toggleInventoryDates);
  inventoryForm.addEventListener("submit", event => {
    event.preventDefault(); productQuery = new URLSearchParams(new FormData(inventoryForm)); productPage = 1; void loadProducts();
  });
  document.querySelector("#inventory-reset").addEventListener("click", () => {
    inventoryForm.reset(); toggleInventoryDates(); productQuery = new URLSearchParams(); productPage = 1; void loadProducts();
  });
  document.querySelector("#products-prev").addEventListener("click", () => { productPage--; void loadProducts(); });
  document.querySelector("#products-next").addEventListener("click", () => { productPage++; void loadProducts(); });

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
  const operationLabel = (operation) => operation === "IN" ? "入库" : operation === "SALE_OUT" ? "出库" : operation === "ADJUST" ? "调整" : "撤销";
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

  if ("serviceWorker" in navigator && window.isSecureContext) {
    let updateRequested = false;
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
        if (pendingScan.get() || submitting || unknownScanId || adjustmentPending) {
          alert("请先完成或核对当前操作，再更新页面。"); return;
        }
        updateRequested = true;
        registration.waiting?.postMessage({ type: "SKIP_WAITING" });
      });
      navigator.serviceWorker.addEventListener("controllerchange", () => {
        // First install calls clients.claim(); never erase a login or scan in progress.
        if (updateRequested) window.location.reload();
      });
    });
  }
})();
