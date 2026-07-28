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
  let mode = null;
  let keyBuffer = "";
  let submitting = false;
  let pendingUnknownScanId = null;

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
    const clientScanId = crypto.randomUUID();
    readyState.textContent = "正在提交…";
    showResult(`正在处理条码 ${barcode}…`);
    try {
      const response = await fetch("/api/scans", {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barcode, operation: mode, client_scan_id: clientScanId }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message = payload.message || "扫码处理失败";
        showResult(message, "error");
        speak(message);
      } else if (payload.status === "SUCCESS") {
        showResult(payload.message || "扫码处理成功", "success");
        speak(payload.message || "扫码处理成功");
      } else if (payload.status === "OUT_OF_STOCK") {
        showResult(payload.message || "库存不足，无法出库", "error");
        speak(payload.message || "库存不足，无法出库");
      } else if (payload.status === "UNKNOWN_BARCODE_REQUIRES_INPUT" && mode === "IN") {
        pendingUnknownScanId = clientScanId;
        unknownBarcode.value = barcode;
        unknownForm.hidden = false;
        showResult("未找到该条码，请补充商品资料", "error");
        unknownGameName.focus();
      } else {
        const message = payload.message || "扫码返回未知状态，请重试";
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
  unknownForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!pendingUnknownScanId || submitting) return;
    submitting = true;
    const form = new FormData(unknownForm);
    const request = {
      barcode: unknownBarcode.value,
      game_name: String(form.get("game_name") || "").trim(),
      platform: form.get("platform"),
      region: String(form.get("region") || "").trim() || "UNKNOWN",
      edition: String(form.get("edition") || "").trim() || null,
      operation: "IN",
      client_scan_id: pendingUnknownScanId,
    };
    readyState.textContent = "正在登记…";
    try {
      const response = await fetch("/api/scans/resolve-unknown", {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const payload = await response.json().catch(() => ({}));
      if (response.ok && payload.status === "SUCCESS") {
        const message = `${payload.game_name}（${payload.platform}），入库成功，当前库存 ${payload.quantity_after} 件。`;
        showResult(message, "success");
        speak(message);
        unknownForm.reset();
        unknownForm.hidden = true;
        pendingUnknownScanId = null;
      } else {
        const message = payload.message || "商品登记失败，请检查后重试";
        showResult(message, "error");
        speak(message);
      }
    } catch (_error) {
      showResult("网络请求失败，补录内容仍保留，请重试", "error");
    } finally {
      submitting = false;
      readyState.textContent = "扫码枪已就绪";
      if (unknownForm.hidden) focusScanner();
    }
  });
  document.querySelector("#unknown-cancel").addEventListener("click", () => {
    unknownForm.reset();
    unknownForm.hidden = true;
    pendingUnknownScanId = null;
    showResult("已取消补录，未产生库存变化");
    focusScanner();
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
