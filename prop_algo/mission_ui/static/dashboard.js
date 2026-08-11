(() => {
  const statusEl = document.getElementById("status");
  const modeEl = document.getElementById("mode");
  const alertsEl = document.getElementById("alerts");
  const eventsEl = document.getElementById("events");
  const rawEl = document.getElementById("raw");
  const footerEl = document.getElementById("footer");
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

  function setStatus(text, state) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.dataset.state = state || "bad";
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

  connect();
})();
