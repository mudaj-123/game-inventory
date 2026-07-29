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

  document.querySelector("#transactions-button").addEventListener("click", async () => {
    const response = await apiFetch("/api/transactions");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) { showResult(payload.detail || "读取流水失败", "error"); return; }
    const list = document.querySelector("#transaction-list");
    list.replaceChildren(...payload.items.map((item) => {
      const card = document.createElement("article"); card.className = "transaction-card";
      const title = document.createElement("strong"); title.textContent = `${item.game_name} · ${item.operation_type}`;
      const detail = document.createElement("p"); detail.textContent = `${item.barcode}｜${item.username}｜库存 ${item.quantity_before} → ${item.quantity_after}${item.reversed ? "｜已撤销" : ""}`;
      card.append(title, detail); return card;
    }));
    homePanel.hidden = true; transactionsPanel.hidden = false;
  });
  document.querySelector("#transactions-back").addEventListener("click", () => {
    transactionsPanel.hidden = true; homePanel.hidden = false;
  });
  document.querySelector("#undo-button").addEventListener("click", async () => {
    const preview = await apiFetch("/api/transactions?page_size=1");
    const data = await preview.json().catch(() => ({}));
    const item = data.items?.find((entry) => !entry.reversed && entry.operation_type !== "REVERSAL");
    if (!item) { window.alert("没有可撤销的流水"); return; }
    if (!window.confirm(`确认撤销 ${item.game_name} 的 ${item.operation_type}？`)) return;
    const response = await apiFetch("/api/transactions/undo-last", { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    showResult(response.ok ? payload.message : (payload.detail || "撤销失败"), response.ok ? "success" : "error");
    if (response.ok) { speak(payload.message); focusScanner(); }
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
