(() => {
  const statusEl = document.getElementById("status");
  const modeEl = document.getElementById("mode");
  const alertsEl = document.getElementById("alerts");
  const eventsEl = document.getElementById("events");
  const rawEl = document.getElementById("raw");
  const footerEl = document.getElementById("footer");
  const ctrlStatusEl = document.getElementById("ctrl-status");
  const btnPause = document.getElementById("btn-pause");
  const btnResume = document.getElementById("btn-resume");
  const btnSafe = document.getElementById("btn-safe");
  const btnClearSafe = document.getElementById("btn-clear-safe");
  const metricEls = Object.fromEntries(
    [...document.querySelectorAll("#metrics [data-k]")].map((el) => [el.dataset.k, el])
  );

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${location.host}/ws`;
  const MAX_EVENTS = 40;
  const eventLog = [];
  let ws;
  let lastAlertKey = "";
  let msgCount = 0;
  let controlBusy = false;
  let lastControl = null;

  function setStatus(text, state) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.dataset.state = state || "bad";
  }

  function controlSummary(ctrl) {
    if (!ctrl) return { text: "control: —", state: "" };
    const flags = [];
    if (ctrl.trading_halt) flags.push("halt");
    if (ctrl.autopilot_paused) flags.push("paused");
    if (ctrl.force_safe) flags.push("SAFE");
    if (!flags.length) {
      return { text: "control: running", state: "running" };
    }
    const state = ctrl.trading_halt
      ? "halt"
      : ctrl.force_safe
        ? "safe"
        : "paused";
    return { text: `control: ${flags.join(" · ")}`, state };
  }

  function renderControl(ctrl) {
    lastControl = ctrl;
    const { text, state } = controlSummary(ctrl);
    if (ctrlStatusEl) {
      ctrlStatusEl.textContent = text;
      ctrlStatusEl.dataset.state = state;
    }
    if (btnPause) btnPause.disabled = controlBusy || !!(ctrl && ctrl.autopilot_paused);
    if (btnResume) btnResume.disabled = controlBusy || !(ctrl && ctrl.autopilot_paused);
    if (btnSafe) btnSafe.disabled = controlBusy || !!(ctrl && ctrl.force_safe);
    if (btnClearSafe) btnClearSafe.disabled = controlBusy || !(ctrl && ctrl.force_safe);
  }

  async function fetchControl() {
    try {
      const resp = await fetch("/api/control", { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      renderControl(data);
      return data;
    } catch (err) {
      if (ctrlStatusEl) {
        ctrlStatusEl.textContent = `control: error (${err.message || err})`;
        ctrlStatusEl.dataset.state = "";
      }
      return null;
    }
  }

  async function postControl(path, body, label) {
    if (controlBusy) return;
    controlBusy = true;
    renderControl(lastControl);
    setStatus(`${label}…`, "warn");
    try {
      const opts = {
        method: "POST",
        headers: { Accept: "application/json" },
      };
      if (body !== undefined) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
      const resp = await fetch(path, opts);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      renderControl(data);
      pushEvent(`${label}: ${controlSummary(data).text}`);
      setStatus(`Live — ${controlSummary(data).text}`, "ok");
    } catch (err) {
      pushEvent(`${label} failed: ${err.message || err}`);
      setStatus(`${label} failed`, "bad");
      await fetchControl();
    } finally {
      controlBusy = false;
      renderControl(lastControl);
    }
  }

  function fmtNum(n, digits = 2) {
    if (n == null || n === "" || Number.isNaN(Number(n))) return "—";
    return Number(n).toLocaleString(undefined, {
      maximumFractionDigits: digits,
      minimumFractionDigits: 0,
    });
  }

  function setMetric(key, text, muted = false) {
    const el = metricEls[key];
    if (!el) return;
    el.textContent = text == null || text === "" ? "—" : String(text);
    el.classList.toggle("muted", muted || text == null || text === "—" || text === "");
  }

  function renderList(el, items, emptyText, itemClass) {
    el.innerHTML = "";
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = emptyText;
      el.appendChild(li);
      return;
    }
    for (const item of items) {
      const li = document.createElement("li");
      if (itemClass) li.className = itemClass;
      if (typeof item === "string") {
        li.textContent = item;
      } else {
        li.textContent = item.text;
        if (item.ts) {
          const ts = document.createElement("span");
          ts.className = "ts";
          ts.textContent = item.ts;
          li.appendChild(ts);
        }
      }
      el.appendChild(li);
    }
  }

  function pushEvent(text) {
    const ts = new Date().toLocaleTimeString();
    eventLog.unshift({ text, ts });
    if (eventLog.length > MAX_EVENTS) eventLog.length = MAX_EVENTS;
    renderList(eventsEl, eventLog, "No events yet", "action");
  }

  function alertKey(alerts) {
    return JSON.stringify(alerts || []);
  }

  function renderPayload(payload) {
    msgCount += 1;
    const dash = payload.dashboard || {};
    const exec = payload.execution || {};
    const alerts = Array.isArray(payload.alerts) ? payload.alerts : [];
    const actions = Array.isArray(payload.actions) ? payload.actions : [];
    const mode = payload.global_mode || dash.risk_mode || "—";

    modeEl.textContent = mode;
    modeEl.dataset.mode = String(mode);

    const anomalies = dash.anomalies;
    const anomalyCount = Array.isArray(anomalies)
      ? anomalies.length
      : anomalies == null
        ? "—"
        : String(anomalies);

    setMetric("equity", fmtNum(dash.equity, 2));
    setMetric("risk_mode", dash.risk_mode ?? "—");
    setMetric("unified_mode", dash.unified_mode ?? "—");
    setMetric(
      "liquidity",
      dash.liquidity == null ? "—" : fmtNum(dash.liquidity, 3)
    );
    setMetric("anomalies", anomalyCount);
    setMetric("learning_meta_mode", dash.learning_meta_mode ?? "—");
    setMetric("exec_route", exec.route ?? "—");
    setMetric(
      "slippage",
      exec.slippage == null ? "—" : fmtNum(exec.slippage, 5)
    );
    setMetric(
      "exec_size",
      exec.size == null ? "—" : fmtNum(exec.size, 3)
    );

    const riskOffTile =
      dash.risk_off ??
      (exec.risk_off
        ? exec.risk_off.active || exec.blocked
          ? `ACTIVE (${exec.block_reason || exec.risk_off.reason || "risk_off"})`
          : exec.risk_off.enabled === false
            ? "off"
            : "normal"
        : null);
    setMetric("risk_off", riskOffTile ?? "—", !riskOffTile);

    const ap = exec.autopilot;
    const autopilotTile =
      dash.autopilot ??
      (ap
        ? ap.enabled === false || ap.state === "off"
          ? "off"
          : ap.paused || ap.allow === false
            ? `paused (${ap.reason || "paused"})`
            : "running"
        : null);
    setMetric("autopilot", autopilotTile ?? "—", !autopilotTile);

    const autonomy = payload.autonomy || {};
    const autonomyMode =
      dash.autonomy_mode ?? autonomy.global_mode ?? null;
    setMetric("autonomy_mode", autonomyMode ?? "—", !autonomyMode);

    const marlStatus =
      dash.marl_status ??
      (payload.marl
        ? typeof payload.marl === "object" && payload.marl.actions
          ? `agents=${Object.keys(payload.marl.actions).length}`
          : "active"
        : null);
    setMetric("marl_status", marlStatus ?? "—", !marlStatus);

    const sim = payload.simulation;
    let simStatus = dash.simulation_status ?? null;
    if (!simStatus && sim && typeof sim === "object") {
      simStatus =
        sim.status != null && sim.steps != null
          ? `${sim.status} (${sim.steps} steps)`
          : sim.status ?? "active";
    }
    setMetric("simulation_status", simStatus ?? "—", !simStatus);

    renderList(
      alertsEl,
      alerts.length ? alerts : [],
      "No active alerts",
      "alert"
    );

    const key = alertKey(alerts);
    if (key !== lastAlertKey) {
      if (alerts.length) {
        pushEvent(`Alerts: ${alerts.join("; ")}`);
      } else if (lastAlertKey && lastAlertKey !== "[]") {
        pushEvent("Alerts cleared");
      }
      lastAlertKey = key;
    }

    if (actions.length && msgCount % 8 === 1) {
      const labels = actions.map((a) =>
        typeof a === "string" ? a : a.action || a.type || JSON.stringify(a)
      );
      pushEvent(`Actions: ${labels.join(", ")}`);
    }

    if (msgCount === 1) {
      pushEvent("First mission_stream snapshot received");
    }

    rawEl.textContent = JSON.stringify(payload, null, 2);
    if (footerEl) {
      const adapter = payload.adapter || "—";
      footerEl.textContent = `broker: ${adapter}`;
    }
    setStatus(`Live — mission_stream · ${msgCount} update${msgCount === 1 ? "" : "s"}`, "ok");
  }

  function connect() {
    setStatus(`Connecting ${url}…`, "warn");
    ws = new WebSocket(url);

    ws.onopen = () => setStatus("Live — mission_stream", "ok");

    ws.onmessage = (event) => {
      try {
        renderPayload(JSON.parse(event.data));
      } catch {
        rawEl.textContent = String(event.data);
        setStatus("Live — non-JSON frame", "warn");
      }
    };

    ws.onclose = () => {
      setStatus("Disconnected — retrying in 2s", "bad");
      setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      setStatus("WebSocket error", "bad");
      ws.close();
    };
  }

  if (btnPause) {
    btnPause.addEventListener("click", () =>
      postControl("/api/control/autopilot/pause", undefined, "Pause autopilot")
    );
  }
  if (btnResume) {
    btnResume.addEventListener("click", () =>
      postControl("/api/control/autopilot/resume", undefined, "Resume autopilot")
    );
  }
  if (btnSafe) {
    btnSafe.addEventListener("click", () =>
      postControl("/api/control/safe", { active: true }, "Force SAFE")
    );
  }
  if (btnClearSafe) {
    btnClearSafe.addEventListener("click", () =>
      postControl("/api/control/safe", { active: false }, "Clear SAFE")
    );
  }

  fetchControl();
  setInterval(fetchControl, 5000);
  connect();
})();
