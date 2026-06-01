const output = document.querySelector("#output");
const statusBadge = document.querySelector("#apiStatus");
const form = document.querySelector("#purchaseForm");
const refreshStockButton = document.querySelector("#refreshStock");
const resetStockButton = document.querySelector("#resetStock");
const resetStockValue = document.querySelector("#resetStockValue");
const messageBox = document.querySelector("#message");
const currentStock = document.querySelector("#currentStock");
const apiWorkers = document.querySelector("#apiWorkers");
const startLoadTestButton = document.querySelector("#startLoadTest");
const stopLoadTestButton = document.querySelector("#stopLoadTest");
const safePresetButton = document.querySelector("#safePreset");
const mediumPresetButton = document.querySelector("#mediumPreset");
const hardPresetButton = document.querySelector("#hardPreset");
const loadOutput = document.querySelector("#loadOutput");

const loadInputs = {
  rps: document.querySelector("#rpsInput"),
  duration: document.querySelector("#durationInput"),
  concurrency: document.querySelector("#concurrencyInput"),
};

const metricElements = {
  status: document.querySelector("#loadStatus"),
  target: document.querySelector("#targetCount"),
  scheduled: document.querySelector("#scheduledCount"),
  completed: document.querySelector("#completedCount"),
  success: document.querySelector("#successCount"),
  conflict: document.querySelector("#conflictCount"),
  errors: document.querySelector("#errorCount"),
  dropped: document.querySelector("#droppedCount"),
  actualRps: document.querySelector("#actualRps"),
  inFlight: document.querySelector("#inFlightCount"),
};

let activeLoadTest = null;
let lastMetricsRenderAt = 0;
let pendingMetricsRender = null;
let metricsRenderTimer = null;

function show(value) {
  output.textContent = JSON.stringify(value, null, 2);
}

function showLoad(value) {
  loadOutput.textContent = JSON.stringify(value, null, 2);
}

function setMessage(text, type = "info") {
  messageBox.textContent = text;
  messageBox.className = `message ${type === "info" ? "" : type}`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw { status: response.status, data };
  }
  return data;
}

function getPurchasePayload() {
  const payload = Object.fromEntries(new FormData(form).entries());
  return {
    user_id: Number(payload.user_id),
    product_id: Number(payload.product_id),
    purchased_count: Number(payload.purchased_count),
  };
}

async function checkHealth() {
  try {
    await requestJson("/health");
    statusBadge.textContent = "online";
    statusBadge.className = "status ok";
  } catch (error) {
    statusBadge.textContent = "offline";
    statusBadge.className = "status error";
    setMessage("API недоступний. Перевір Docker і /health.", "error");
  }
}

async function loadRuntimeInfo() {
  try {
    const runtime = await requestJson("/system/runtime");
    apiWorkers.textContent = runtime.api_workers;
  } catch (error) {
    apiWorkers.textContent = "?";
  }
}

async function refreshStock(message = "Залишок оновлено.") {
  const productId = getPurchasePayload().product_id;
  try {
    const product = await requestJson(`/products/${productId}`);
    currentStock.textContent = product.stock;
    show(product);
    setMessage(`${message} Поточний stock для product_id=${productId}: ${product.stock}.`, "ok");
    return product;
  } catch (error) {
    show(error);
    setMessage("Не вдалося оновити залишок. Перевір product_id або API.", "error");
    return null;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = getPurchasePayload();

  try {
    const result = await requestJson("/purchase", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    show(result);
    setMessage(`Покупка успішна. Списано ${payload.purchased_count} одиниць.`, "ok");
    await refreshStock("Залишок після покупки оновлено.");
  } catch (error) {
    show(error);
    if (error.status === 409) {
      setMessage("Покупка не виконана: товару недостатньо на складі.", "error");
    } else {
      setMessage("Покупка не виконана. Подивись JSON-відповідь нижче.", "error");
    }
  }
});

refreshStockButton.addEventListener("click", async () => {
  refreshStockButton.disabled = true;
  await refreshStock();
  refreshStockButton.disabled = false;
});

resetStockButton.addEventListener("click", async () => {
  const productId = getPurchasePayload().product_id;
  const stock = Number(resetStockValue.value);

  if (!Number.isInteger(stock) || stock < 0) {
    setMessage("Новий залишок має бути цілим числом від 0 і більше.", "error");
    return;
  }

  resetStockButton.disabled = true;
  try {
    const product = await requestJson(`/products/${productId}/reset`, {
      method: "POST",
      body: JSON.stringify({ stock }),
    });
    currentStock.textContent = product.stock;
    show(product);
    setMessage(`Залишок скинуто. Тепер product_id=${productId} має stock=${product.stock}.`, "ok");
  } catch (error) {
    show(error);
    setMessage("Не вдалося скинути залишок. Перевір product_id або API.", "error");
  } finally {
    resetStockButton.disabled = false;
  }
});

function updateMetrics(state, force = false) {
  const now = performance.now();
  if (!force && now - lastMetricsRenderAt < 250) {
    pendingMetricsRender = state;
    if (!metricsRenderTimer) {
      metricsRenderTimer = window.setTimeout(() => {
        metricsRenderTimer = null;
        if (pendingMetricsRender) {
          updateMetrics(pendingMetricsRender, true);
          pendingMetricsRender = null;
        }
      }, 250);
    }
    return;
  }

  lastMetricsRenderAt = now;
  const elapsedSeconds = state.startedAt ? (now - state.startedAt) / 1000 : 0;
  const completed = state.success + state.conflict + state.errors;
  const actualRps = elapsedSeconds > 0 ? completed / elapsedSeconds : 0;

  metricElements.status.textContent = state.status;
  metricElements.target.textContent = state.target_requests;
  metricElements.scheduled.textContent = state.scheduled;
  metricElements.completed.textContent = completed;
  metricElements.success.textContent = state.success;
  metricElements.conflict.textContent = state.conflict;
  metricElements.errors.textContent = state.errors;
  metricElements.dropped.textContent = state.dropped;
  metricElements.actualRps.textContent = actualRps.toFixed(1);
  metricElements.inFlight.textContent = state.inFlight;

  showLoad({
    status: state.status,
    elapsed_seconds: Number(elapsedSeconds.toFixed(2)),
    scheduled_requests: state.scheduled,
    target_requests: state.target_requests,
    completed_requests: completed,
    successful_purchases: state.success,
    stock_conflicts: state.conflict,
    timeout_or_other_errors: state.errors,
    dropped_by_browser: state.dropped,
    in_flight: state.inFlight,
    actual_rps: Number(actualRps.toFixed(1)),
    target: state.target,
    note: "Це браузерний навчальний RPS-тест. Якщо Dropped велике, браузер не встигає створити цільовий RPS. Для точнішого benchmark використовуй Locust або tests/load_test.py.",
  });
}

async function sendPurchase(payload, timeoutMs, state) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);

  state.inFlight += 1;
  updateMetrics(state);

  try {
    const response = await fetch("/purchase", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
      cache: "no-store",
    });

    if (response.status === 200) {
      state.success += 1;
    } else if (response.status === 409) {
      state.conflict += 1;
    } else {
      state.errors += 1;
    }
  } catch (error) {
    state.errors += 1;
  } finally {
    window.clearTimeout(timer);
    state.inFlight -= 1;
    updateMetrics(state);
  }
}

async function runLoadTest() {
  if (activeLoadTest) {
    setMessage("RPS-тест уже запущений.", "error");
    return;
  }

  const rps = Number(loadInputs.rps.value);
  const duration = Number(loadInputs.duration.value);
  const concurrency = Number(loadInputs.concurrency.value);
  const productId = getPurchasePayload().product_id;
  const purchasedCount = 1;
  const timeoutMs = 5000;
  const values = [rps, duration, concurrency, productId, purchasedCount, timeoutMs];
  const targetRequests = Math.round(rps * duration);

  if (values.some((value) => !Number.isFinite(value) || value <= 0)) {
    setMessage("Усі поля RPS-тесту мають бути числами більше 0.", "error");
    return;
  }

  let initialMessage = `RPS-тест запущено: ${rps} RPS на ${duration} секунд.`;
  try {
    const product = await requestJson(`/products/${productId}`);
    currentStock.textContent = product.stock;
    if (product.stock <= 0) {
      setMessage("RPS-тест не запущено: залишок товару 0. Спочатку натисни “Скинути залишок”.", "error");
      show(product);
      return;
    }
    if (product.stock < targetRequests * purchasedCount) {
      initialMessage =
        `RPS-тест запущено, але stock=${product.stock} менший за ціль ${targetRequests}. ` +
        "Товар закінчиться раніше, і тест зупиниться після 409 Conflict.";
    }
  } catch (error) {
    setMessage("Не вдалося перевірити залишок перед RPS-тестом. Перевір product_id або API.", "error");
    show(error);
    return;
  }

  const state = {
    status: "running",
    startedAt: performance.now(),
    scheduled: 0,
    success: 0,
    conflict: 0,
    errors: 0,
    dropped: 0,
    inFlight: 0,
    stopRequested: false,
    target_requests: targetRequests,
    target: {
      rps,
      duration,
      concurrency,
      product_id: productId,
      purchased_count: purchasedCount,
      timeout_ms: timeoutMs,
      expected_stock_spend: targetRequests * purchasedCount,
      source: "browser",
    },
  };

  activeLoadTest = state;
  startLoadTestButton.disabled = true;
  stopLoadTestButton.disabled = false;
  setMessage(initialMessage, "ok");
  updateMetrics(state, true);

  const stopAt = performance.now() + duration * 1000;
  const intervalMs = 1000 / rps;
  let nextRequestAt = performance.now();
  let userId = Date.now();

  while (!state.stopRequested && performance.now() < stopAt) {
    const now = performance.now();
    if (now < nextRequestAt) {
      await new Promise((resolve) => window.setTimeout(resolve, nextRequestAt - now));
    }

    if (state.inFlight < concurrency) {
      state.scheduled += 1;
      userId += 1;
      sendPurchase(
        {
          user_id: userId,
          product_id: productId,
          purchased_count: purchasedCount,
        },
        timeoutMs,
        state
      );
    } else {
      state.dropped += 1;
    }

    if (state.conflict > 0) {
      state.stopRequested = true;
      setMessage("Тест зупиняється: товар закінчився, API повернув 409 Conflict.", "error");
    }

    nextRequestAt += intervalMs;
    updateMetrics(state);
  }

  state.status = "draining";
  setMessage("RPS-тест завершується, чекаємо останні відповіді.", "ok");
  updateMetrics(state, true);

  const drainUntil = performance.now() + timeoutMs + 500;
  while (state.inFlight > 0 && performance.now() < drainUntil) {
    await new Promise((resolve) => window.setTimeout(resolve, 100));
  }

  state.status = state.stopRequested ? "stopped" : "finished";
  updateMetrics(state, true);
  if (metricsRenderTimer) {
    window.clearTimeout(metricsRenderTimer);
    metricsRenderTimer = null;
    pendingMetricsRender = null;
  }
  setMessage(state.stopRequested ? "RPS-тест зупинено." : "RPS-тест завершено.", "ok");
  await refreshStock("Залишок після RPS-тесту оновлено.");

  activeLoadTest = null;
  startLoadTestButton.disabled = false;
  stopLoadTestButton.disabled = true;
}

startLoadTestButton.addEventListener("click", runLoadTest);

stopLoadTestButton.addEventListener("click", () => {
  if (activeLoadTest) {
    activeLoadTest.stopRequested = true;
    setMessage("Отримано команду зупинити RPS-тест.", "ok");
  }
});

function applyPreset(rps, duration, concurrency) {
  loadInputs.rps.value = rps;
  loadInputs.duration.value = duration;
  loadInputs.concurrency.value = concurrency;
  setMessage(`Обрано пресет: ${rps} RPS, ${duration} сек, concurrency ${concurrency}.`, "ok");
}

safePresetButton.addEventListener("click", () => applyPreset(50, 10, 10));
mediumPresetButton.addEventListener("click", () => applyPreset(100, 10, 25));
hardPresetButton.addEventListener("click", () => applyPreset(300, 15, 50));

checkHealth();
loadRuntimeInfo();
refreshStock("Початковий залишок завантажено.");
