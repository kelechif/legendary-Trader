/* global Chart */
let assets = [];
let selectedAsset = null;
let selectedTimeframe = "1m";
let isEquityMode = false;
let lastAlertCount = 0;
let alertConfig = { sound: true, popup: true, flash: true };
let backtestChart = null;
let equityChart = null;

function makeLineChart(ctx, label, color) {
    return new Chart(ctx, {
        type: "line",
        data: { labels: [], datasets: [{ label, data: [], borderColor: color, borderWidth: 2, tension: 0.2, pointRadius: 0 }] },
        options: { animation: false, scales: { x: { display: false }, y: { ticks: { color: "#aaa" } } }, plugins: { legend: { labels: { color: "#eee" } } } }
    });
}

function drawCandlestick(canvas, candles) {
    if (!canvas) return;
    const parent = canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(parent.clientWidth - 30, 200);
    const height = Math.max(parent.clientHeight - 50, 260);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#111";
    ctx.fillRect(0, 0, width, height);

    if (!candles || candles.length === 0) {
        ctx.fillStyle = "#666";
        ctx.font = "14px Arial";
        ctx.fillText("Waiting for candle data...", 16, 32);
        return;
    }

    const pad = { top: 12, right: 12, bottom: 24, left: 56 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;
    let min = Infinity, max = -Infinity;
    candles.forEach(c => { min = Math.min(min, c.low); max = Math.max(max, c.high); });
    const padY = (max - min) * 0.05 || 1;
    min -= padY; max += padY;
    const range = max - min || 1;
    const slot = plotW / candles.length;
    const bodyW = Math.max(2, slot * 0.6);

    candles.forEach((c, i) => {
        const x = pad.left + i * slot + slot / 2;
        const y = v => pad.top + plotH * (1 - (v - min) / range);
        const up = c.close >= c.open;
        const color = up ? "#26a69a" : "#ef5350";
        if (c.forming) ctx.globalAlpha = 0.65;
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(x, y(c.high));
        ctx.lineTo(x, y(c.low));
        ctx.stroke();
        const top = y(Math.max(c.open, c.close));
        const bottom = y(Math.min(c.open, c.close));
        ctx.fillRect(x - bodyW / 2, top, bodyW, Math.max(1, bottom - top));
        ctx.globalAlpha = 1;
    });

    ctx.fillStyle = "#aaa";
    ctx.font = "11px Arial";
    ctx.textAlign = "right";
    ctx.fillText(max.toFixed(2), pad.left - 6, pad.top + 10);
    ctx.fillText(min.toFixed(2), pad.left - 6, pad.top + plotH);
}

function playBeep() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = 880;
        gain.gain.value = 0.05;
        osc.start();
        osc.stop(ctx.currentTime + 0.15);
    } catch (_) { /* ignore */ }
}

function flashScreen(type) {
    if (!alertConfig.flash) return;
    const body = document.getElementById("body");
    body.classList.remove("flash-buy", "flash-sell");
    void body.offsetWidth;
    body.classList.add(type === "BUY" ? "flash-buy" : "flash-sell");
}

function showPopup(alert) {
    if (!alertConfig.popup || !("Notification" in window)) return;
    if (Notification.permission === "granted") {
        new Notification(`Quant: ${alert.category}`, { body: alert.message });
    } else if (Notification.permission !== "denied") {
        Notification.requestPermission();
    }
}

function handleNewAlerts(alerts) {
    if (alerts.length <= lastAlertCount) return;
    const fresh = alerts.slice(lastAlertCount);
    lastAlertCount = alerts.length;
    fresh.forEach(a => {
        if (alertConfig.sound) playBeep();
        if (a.category === "trade" && a.meta?.action) flashScreen(a.meta.action);
        showPopup(a);
    });
}

function syncAssetSelect(list) {
    if (!list || !list.length) return;
    const prev = selectedAsset;
    assets = list;
    const sel = document.getElementById("assetSelect");
    sel.innerHTML = assets.map(a => `<option value="${a}">${a}</option>`).join("");
    if (prev && assets.includes(prev)) {
        sel.value = prev;
        selectedAsset = prev;
    } else {
        selectedAsset = assets[0];
        sel.value = selectedAsset;
    }
}

function renderStatusBar(data, health) {
    const mode = data.trading_mode || "tick";
    const safe = data.safe_mode ? "SAFE MODE" : "LIVE SIM";
    const count = data.asset_count || assets.length;
    const cacheBadge = health
        ? `<span class="badge ${health.ready ? 'badge-ok' : 'badge-warn'}">Klines: ${health.cached}/${health.total}</span> `
        : "";
    document.getElementById("statusBar").innerHTML =
        `<span class="badge">${mode.toUpperCase()}</span> ` +
        `<span class="badge ${data.safe_mode ? 'badge-warn' : 'badge-ok'}">${safe}</span> ` +
        `<span class="badge">Universe: ${count}</span> ` +
        cacheBadge +
        `<span class="badge">Strategy: ${data.strategy}</span>`;
}

function renderPortfolio(portfolio) {
    const openCount = portfolio.holdings.filter(h => h.position !== 0).length;
    let summary = `
        <div class="stat"><div class="val">$${portfolio.total_equity.toLocaleString()}</div><div class="lbl">Total Equity</div></div>
        <div class="stat"><div class="val ${portfolio.pnl >= 0 ? 'pos-long' : 'pos-short'}">${portfolio.pnl >= 0 ? '+' : ''}$${portfolio.pnl.toLocaleString()}</div><div class="lbl">Total P&L</div></div>
        <div class="stat"><div class="val">${openCount}</div><div class="lbl">Open Positions</div></div>`;

    if (portfolio.mode === "equity") {
        summary += `
        <div class="stat"><div class="val">$${(portfolio.cash || 0).toLocaleString()}</div><div class="lbl">Cash</div></div>
        <div class="stat"><div class="val">${portfolio.exposure_pct || 0}%</div><div class="lbl">Exposure</div></div>`;
    }

    document.getElementById("portfolioSummary").innerHTML = summary;

    const tbody = document.querySelector("#portfolioTable tbody");
    const rows = portfolio.holdings
        .filter(h => h.position !== 0 || (h.shares && h.shares > 0))
        .slice(0, 50);
    const display = rows.length ? rows : portfolio.holdings.slice(0, 15);

    tbody.innerHTML = display.map(h => `
        <tr>
            <td>${h.asset}</td>
            <td class="pos-${h.position_label.toLowerCase()}">${h.position_label}</td>
            <td>${h.shares ?? '—'}</td>
            <td>${h.price ? h.price.toFixed(2) : '—'}</td>
            <td>$${(h.market_value ?? h.equity ?? 0).toLocaleString()}</td>
            <td>${h.allocation_pct}%</td>
            <td>${h.trade_count}</td>
        </tr>`).join("");
}

function renderSignals(signals) {
    if (!signals || !signals.summary) {
        document.getElementById("signalSummary").innerHTML = "";
        document.querySelector("#signalTable tbody").innerHTML =
            "<tr><td colspan=5>Run daily cycle to scan universe</td></tr>";
        return;
    }
    const s = signals.summary;
    document.getElementById("signalSummary").innerHTML = `
        <div class="stat"><div class="val">${s.buy || 0}</div><div class="lbl">Buy Signals</div></div>
        <div class="stat"><div class="val">${s.bull || 0}</div><div class="lbl">Bull Regime</div></div>
        <div class="stat"><div class="val">${s.bear || 0}</div><div class="lbl">Bear</div></div>
        <div class="stat"><div class="val">${s.sideways || 0}</div><div class="lbl">Sideways</div></div>`;

    const rows = (signals.entries || []).slice(0, 15);
    document.querySelector("#signalTable tbody").innerHTML = rows.length
        ? rows.map(r => `
            <tr>
                <td>${r.asset}</td>
                <td class="pos-long">${r.signal}</td>
                <td>${r.score}</td>
                <td>${r.rsi14 != null ? r.rsi14.toFixed(1) : '—'}</td>
                <td>${r.regime_label || (r.regime ? 'BULL' : '—')}</td>
            </tr>`).join("")
        : "<tr><td colspan=5>No ranked entries today</td></tr>";
}

function renderMetrics(performance) {
    const p = performance.portfolio;
    document.getElementById("perfPortfolio").innerHTML = `
        <div class="metric"><div class="val">${p.sharpe}</div><div class="lbl">Sharpe</div></div>
        <div class="metric"><div class="val">${p.max_drawdown_pct}%</div><div class="lbl">Max DD</div></div>
        <div class="metric"><div class="val">${p.win_rate_pct}%</div><div class="lbl">Win Rate</div></div>
        <div class="metric"><div class="val">${p.total_trades}</div><div class="lbl">Trades</div></div>`;

    const assetMetrics = Object.entries(performance.assets || {});
    document.getElementById("perfAssets").innerHTML = assetMetrics.length
        ? assetMetrics.map(([a, m]) =>
            `<div><b>${a}</b>: Sharpe ${m.sharpe} | DD ${m.max_drawdown_pct}% | Win ${m.win_rate_pct}%</div>`
        ).join("")
        : "<div>Portfolio-level metrics (multi-asset equity mode)</div>";
}

function renderOrderBook(book) {
    const bids = book.bids || [];
    const asks = book.asks || [];
    document.querySelector("#bidsTable tbody").innerHTML = bids.map(([p, s]) =>
        `<tr><td class="pos-long">${p.toFixed(2)}</td><td>${s.toFixed(4)}</td></tr>`).join("") || "<tr><td colspan=2>No data</td></tr>";
    document.querySelector("#asksTable tbody").innerHTML = asks.map(([p, s]) =>
        `<tr><td class="pos-short">${p.toFixed(2)}</td><td>${s.toFixed(4)}</td></tr>`).join("") || "<tr><td colspan=2>No data</td></tr>";
}

function renderAlerts(alerts) {
    document.getElementById("alertLog").innerHTML = alerts.slice().reverse().map(a =>
        `<div class="alert-${a.level === 'warning' ? 'warning' : a.category === 'trade' ? 'trade' : 'info'}">${a.time} [${a.category}] ${a.message}</div>`
    ).join("");
    handleNewAlerts(alerts);
}

function renderParamsForm(schema, currentParams) {
    const form = document.getElementById("paramsForm");
    form.innerHTML = Object.entries(schema).map(([key, meta]) =>
        `<label>${key}<input name="${key}" type="number" step="any" value="${currentParams[key] ?? meta.default}"></label>`
    ).join("");
}

function ensureEquityChart() {
    if (equityChart) return;
    equityChart = new Chart(document.getElementById("equityChart").getContext("2d"), {
        type: "line",
        data: { labels: [], datasets: [{ label: "Portfolio", data: [], borderColor: "#8cf", borderWidth: 2, tension: 0.2, pointRadius: 0 }] },
        options: { animation: false, scales: { x: { display: false }, y: { ticks: { color: "#aaa" } } }, plugins: { legend: { labels: { color: "#eee" } } } }
    });
}

function updateEquityChart(data) {
    ensureEquityChart();
    if (isEquityMode && data.equity.PORTFOLIO) {
        equityChart.data.labels = data.equity_labels;
        equityChart.data.datasets = [{
            label: "Portfolio NAV",
            data: data.equity.PORTFOLIO,
            borderColor: "#8cf",
            borderWidth: 2,
            tension: 0.2,
            pointRadius: 0
        }];
    } else {
        const colors = ["cyan", "magenta", "yellow", "orange", "lime"];
        equityChart.data.labels = data.equity_labels;
        equityChart.data.datasets = assets.slice(0, 5).map((a, i) => ({
            label: a,
            data: data.equity[a] || [],
            borderColor: colors[i % colors.length],
            borderWidth: 2,
            tension: 0.2,
            pointRadius: 0
        }));
    }
    equityChart.update("none");
}

async function loadStrategies() {
    const res = await fetch("/api/strategies");
    const data = await res.json();
    const sel = document.getElementById("strategySelect");
    sel.innerHTML = data.strategies.map(s => `<option value="${s}">${s}</option>`).join("");
    renderParamsForm(data.schemas[data.strategy] || {}, data.params || {});
}

const priceChart = makeLineChart(document.getElementById("priceChart").getContext("2d"), "Price", "cyan");

document.getElementById("assetSelect").addEventListener("change", e => { selectedAsset = e.target.value; });
document.getElementById("timeframeSelect").addEventListener("change", e => { selectedTimeframe = e.target.value; });

document.getElementById("strategySelect").addEventListener("change", async e => {
    await fetch("/api/strategy/" + e.target.value, { method: "POST" });
    await loadStrategies();
});

document.getElementById("saveParams").addEventListener("click", async () => {
    const strategy = document.getElementById("strategySelect").value;
    const form = document.getElementById("paramsForm");
    const params = {};
    form.querySelectorAll("input").forEach(inp => { params[inp.name] = parseFloat(inp.value); });
    await fetch("/api/strategy/" + strategy + "/params", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params)
    });
    document.getElementById("strategyLabel").textContent = "Parameters saved";
    setTimeout(() => document.getElementById("strategyLabel").textContent = "", 2000);
});

let lastWfoConsensus = null;

document.getElementById("runWfo").addEventListener("click", async () => {
    const strategy = document.getElementById("strategySelect").value;
    document.getElementById("backtestStatus").textContent = "Running walk-forward optimization...";
    document.getElementById("wfoResults").innerHTML = "";
    document.getElementById("backtestContributors").innerHTML = "";
    document.getElementById("applyWfoParams").disabled = true;
    lastWfoConsensus = null;

    const res = await fetch("/api/wfo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy, limit: 50, folds: 2, grid: "expanded", max_combos: 64 })
    });
    const data = await res.json();
    if (data.error && !data.fold_results) {
        document.getElementById("backtestStatus").textContent = data.error;
        return;
    }

    lastWfoConsensus = data.consensus_params || null;
    document.getElementById("applyWfoParams").disabled = !lastWfoConsensus;

    document.getElementById("backtestStatus").textContent =
        `WFO — ${data.folds} folds, ${data.param_combos} combos, avg OOS Sharpe ${data.avg_oos_sharpe}`;

    const consensus = data.consensus_params || {};
    document.getElementById("wfoResults").innerHTML = `
        <div><b>Consensus params</b></div>
        ${Object.entries(consensus).map(([k, v]) => `<div>${k}: ${v}</div>`).join("")}
        <div style="margin-top:8px"><b>Fold OOS Sharpe</b></div>
        ${(data.fold_results || []).map(f =>
            `<div>Fold ${f.fold}: ${(f.oos_metrics && f.oos_metrics.sharpe != null) ? f.oos_metrics.sharpe : "—"}</div>`
        ).join("")}`;

    document.getElementById("backtestResults").innerHTML = `
        <div class="metric"><div class="val">${data.avg_oos_sharpe}</div><div class="lbl">Avg OOS Sharpe</div></div>
        <div class="metric"><div class="val">${data.avg_oos_max_drawdown_pct}%</div><div class="lbl">Avg OOS Max DD</div></div>
        <div class="metric"><div class="val">${data.folds}</div><div class="lbl">Folds</div></div>
        <div class="metric"><div class="val">${data.dates || "—"}</div><div class="lbl">Trading Days</div></div>`;
});

document.getElementById("applyWfoParams").addEventListener("click", async () => {
    if (!lastWfoConsensus) return;
    const strategy = document.getElementById("strategySelect").value;
    await fetch("/api/strategy/" + strategy + "/params", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lastWfoConsensus)
    });
    document.getElementById("backtestStatus").textContent = "WFO consensus params applied to live strategy";
    await loadStrategies();
});

document.getElementById("runUniverseBacktest").addEventListener("click", async () => {
    const strategy = document.getElementById("strategySelect").value;
    document.getElementById("backtestStatus").textContent = "Running universe backtest...";
    document.getElementById("backtestContributors").innerHTML = "";
    const res = await fetch("/api/backtest/universe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy })
    });
    const data = await res.json();
    if (data.error) {
        document.getElementById("backtestStatus").textContent = data.error;
        return;
    }
    document.getElementById("backtestStatus").textContent =
        `Universe — ${data.tickers} tickers, ${data.dates} days, ${data.trades.length} trades`;
    const m = data.metrics;
    document.getElementById("backtestResults").innerHTML = `
        <div class="metric"><div class="val">${m.sharpe}</div><div class="lbl">Sharpe</div></div>
        <div class="metric"><div class="val">${m.max_drawdown_pct}%</div><div class="lbl">Max DD</div></div>
        <div class="metric"><div class="val">${m.total_trades}</div><div class="lbl">Trades</div></div>
        <div class="metric"><div class="val">$${m.current_equity.toFixed(0)}</div><div class="lbl">Final Equity</div></div>`;
    document.getElementById("backtestContributors").innerHTML =
        (data.top_contributors || []).map(c =>
            `<div><b>${c.ticker}</b>: ${c.pnl >= 0 ? '+' : ''}$${c.pnl}</div>`
        ).join("") || "";

    const ctx = document.getElementById("backtestChart").getContext("2d");
    if (backtestChart) backtestChart.destroy();
    backtestChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: data.equity_curve.map((_, i) => i),
            datasets: [{ label: "Universe Equity", data: data.equity_curve, borderColor: "#fc8", borderWidth: 2, pointRadius: 0 }]
        },
        options: { animation: false, scales: { x: { display: false }, y: { ticks: { color: "#aaa" } } } }
    });
});

document.getElementById("runBacktest").addEventListener("click", async () => {
    const strategy = document.getElementById("strategySelect").value;
    document.getElementById("backtestStatus").textContent = "Running...";
    const res = await fetch("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy, asset: selectedAsset })
    });
    const data = await res.json();
    if (data.error) {
        document.getElementById("backtestStatus").textContent = data.error;
        return;
    }
    document.getElementById("backtestStatus").textContent = `Done — ${data.data_points} bars`;
    const m = data.metrics;
    document.getElementById("backtestResults").innerHTML = `
        <div class="metric"><div class="val">${m.sharpe}</div><div class="lbl">Sharpe</div></div>
        <div class="metric"><div class="val">${m.max_drawdown_pct}%</div><div class="lbl">Max DD</div></div>
        <div class="metric"><div class="val">${m.win_rate_pct}%</div><div class="lbl">Win Rate</div></div>
        <div class="metric"><div class="val">$${m.current_equity.toFixed(0)}</div><div class="lbl">Final Equity</div></div>`;

    const ctx = document.getElementById("backtestChart").getContext("2d");
    if (backtestChart) backtestChart.destroy();
    backtestChart = new Chart(ctx, {
        type: "line",
        data: { labels: data.equity_curve.map((_, i) => i), datasets: [{ label: "Backtest Equity", data: data.equity_curve, borderColor: "#8cf", borderWidth: 2, pointRadius: 0 }] },
        options: { animation: false, scales: { x: { display: false }, y: { ticks: { color: "#aaa" } } } }
    });
});

let universeHealth = null;

async function update() {
    const res = await fetch("/data");
    const data = await res.json();

    isEquityMode = data.trading_mode === "equity";
    if (isEquityMode) {
        try {
            const hres = await fetch("/api/universe/health");
            universeHealth = await hres.json();
        } catch (_) { /* ignore */ }
    }

    syncAssetSelect(data.assets || assets);

    selectedAsset = document.getElementById("assetSelect").value || selectedAsset;
    selectedTimeframe = document.getElementById("timeframeSelect").value;

    if (isEquityMode) {
        document.getElementById("orderBookSection").style.display = "none";
        if (document.getElementById("timeframeSelect").value === "1m") {
            document.getElementById("timeframeSelect").value = "1d";
            selectedTimeframe = "1d";
        }
    } else {
        document.getElementById("orderBookSection").style.display = "";
    }

    renderStatusBar(data, universeHealth);
    document.getElementById("priceTitle").textContent = `${selectedAsset} Price`;
    document.getElementById("candleTitle").textContent = `${selectedAsset} Candles (${selectedTimeframe})`;

    const prices = data.prices[selectedAsset] || [];
    priceChart.data.labels = prices.map((_, i) => i);
    priceChart.data.datasets[0].data = prices;
    priceChart.data.datasets[0].label = selectedAsset;
    priceChart.update("none");

    const candles = (data.candles[selectedAsset] || {})[selectedTimeframe] || [];
    drawCandlestick(document.getElementById("candleCanvas"), candles);

    renderPortfolio(data.portfolio);
    renderSignals(data.signals);
    renderMetrics(data.performance);
    if (!isEquityMode) renderOrderBook((data.order_books || {})[selectedAsset] || {});
    renderAlerts(data.alerts || []);

    alertConfig = data.alert_config || alertConfig;
    document.getElementById("alertConfig").textContent =
        `Sound: ${alertConfig.sound} | Popup: ${alertConfig.popup} | Flash: ${alertConfig.flash}`;

    const tradeAssets = isEquityMode ? assets : assets.slice(0, 10);
    const lines = [];
    tradeAssets.forEach(a => {
        (data.trades[a] || []).slice(-5).forEach(t => {
            const sh = t.shares ? ` x${t.shares}` : "";
            lines.push(`<div>${t.time} — <b>${t.action}</b> ${a}${sh} @ ${Number(t.price).toFixed(2)}</div>`);
        });
    });
    document.getElementById("tradeLog").innerHTML = lines.reverse().join("") || "<div>No trades yet</div>";

    updateEquityChart(data);
    document.getElementById("metricsLog").textContent = JSON.stringify(data.system_metrics, null, 2);
    document.getElementById("strategySelect").value = data.strategy;
}

loadStrategies();
setInterval(update, 2000);
update();
