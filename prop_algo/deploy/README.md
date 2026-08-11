# prop_algo deploy

**Compose is the primary local path.** Kubernetes under `k8s/` is an optional mirror of the same light stack (not production-complete). Compose/k8s default to `BROKER_ADAPTER=mock`. Live MT5/cTrader are host-oriented (see Brokers below). MARL/simulation need torch and stay out of the default image.

## Compose (primary)

Brings up Redis plus Phase 1–2 style services, mission aggregation, autonomy /
multi-agent (no torch), and Mission UI.

### Services

| Service | Entrypoint | Notes |
|---------|------------|--------|
| `redis` | Redis 7 | Stream bus (`REDIS_HOST=redis`) |
| `market_data_service` | `python -m services.market_data_service.main` | metrics `:8000` |
| `strategy_service` | `python -m services.strategy_service.main` | |
| `risk_service` | `python -m services.risk_service.main` | metrics `:8001` |
| `governance_service` | `python -m services.governance_service.main` | |
| `unified_core_service` | `python -m services.unified_core_service.main` | metrics `:8004` |
| `execution_service` | `python -m services.execution_service.main` | metrics `:8002` |
| `learning_service` | `python -m services.learning_service.main` | metrics `:8003` |
| `mission_control_service` | `python -m services.mission_control_service.main` | aggregates → `mission_stream` |
| `autonomy_service` | `python -m services.autonomy_service.main` | torch-free |
| `multi_agent_service` | `python -m services.multi_agent_service.main` | torch-free rule agents |
| `mission_ui` | `uvicorn mission_ui.app:app` | UI + WS `:8080` |

Skipped in this lean image (need **torch**): `marl_service`, `simulation_service`.

### Requirements

- Root `requirements.txt` includes `redis`, `prometheus_client`, and `requests` for local/dev.
- The image installs the lean set in `prop_algo/deploy/requirements.txt` (no torch / MetaTrader5 / moomoo-api).

### Bring up

From this directory:

```bash
docker compose up --build
```

Detached:

```bash
docker compose up --build -d
```

Stop:

```bash
docker compose down
```

### Env

- `REDIS_HOST` (default `redis`) and `REDIS_PORT` (default `6379`) are read by `infra.stream.Stream`.
- `STREAM_BLOCK_MS` (default `1000`) — blocking timeout for Redis `XREADGROUP` in `infra.stream.Stream.consume` (avoids busy-polling empty streams).
- `LEARNING_LOOP_SLEEP` (default `2`) — seconds to sleep after each `learning_service` cycle so hot `risk_stream` traffic does not peg CPU; compose sets this explicitly. Optional: `LEARNING_NUM_NEW` (candidates per cycle, default `1`).
- `MARL_LOOP_SLEEP` (default `2`) — seconds to sleep after each `marl_service` train step so hot `mission_stream` / `autonomy_stream` traffic does not peg CPU; set in `docker-compose.torch.yml`. Optional: `MARL_TORCH_THREADS` (default `1`).
- `BROKER_ADAPTER=mock` (compose/k8s default) — see Brokers below.
- `NEURAL_EXECUTION=1|0` (compose default `1` on `execution_service`) — optional neural/heuristic execution advice. When enabled, `execution_service` publishes `route` / `slippage` / `volatility` / `size` on `execution_stream` (Mission UI exec tiles). Works without torch via heuristics; set `NEURAL_MODEL_DIR` to load `route.pt` / `slippage.pt` / `volatility.pt` / `sizing.pt` when torch is available. Set `0` to disable.
- `RISK_OFF_ENABLED=1|0` (compose/k8s default `1`) — `risk_service` evaluates `RiskOffEngine` from account equity/balance and publishes `risk_off` on `risk_stream`. `execution_service` zeros size / skips orders when risk-off is active or unified mode is `SAFE_MODE`, and publishes `risk_off` / `blocked` / `block_reason` on `execution_stream` (Mission UI **Risk-off** tile + alert). Mock equity wobble (±50) stays above the −100 drawdown trip, so the stack remains tradeable unless SAFE_MODE or a real drawdown hits. Set `0` to disable the gate.
- `AUTOPILOT_ENABLED=1|0` (compose/k8s default `1`) — `AutopilotEngine` gates strategy→execution in `execution_service`. When off (`0`) or paused (`AUTOPILOT_PAUSED=1`, Mission Control shared state, gov `HALT`, `SAFE_MODE`, or active risk-off), size is zeroed and no new orders are placed; `autopilot` / `blocked` / `block_reason` are published on `execution_stream` (Mission UI **Autopilot** tile + alert). Strategy still publishes signals; the order gate lives in execution. Set `0` to force autopilot off (no autonomous orders).
- Image `PYTHONPATH=/app` so `core`, `infra`, `trading`, `risk`, `learning`, `services`, `mission_ui`, `autonomy`, `neural_execution`, and `agents` imports resolve.

### Operator control plane (pause / resume)

Mission UI exposes an **auth-free** local control API (compose only — do not expose
port 8080 to untrusted networks without a reverse-proxy auth layer):

| Method | Path | Effect |
|--------|------|--------|
| `GET` | `/api/control` | Current flags (`autopilot_paused`, `trading_halt`, `force_safe`) |
| `POST` | `/api/control/autopilot/pause` | Pause autopilot |
| `POST` | `/api/control/autopilot/resume` | Resume autopilot |
| `POST` | `/api/control/safe` | Body `{"active": true\|false}` — force / clear SAFE note |
| `POST` | `/api/control/halt` | Body `{"active": true\|false}` — trading halt flag |

State is persisted in Redis key `mission:control` (override with
`MISSION_CONTROL_REDIS_KEY`) and mirrored to `state/control.json` when the
filesystem is writable. `execution_service` / `AutopilotEngine` re-read this each
cycle (in addition to env `AUTOPILOT_PAUSED`), so operators can pause/resume
without restarting containers. The Mission UI header row has **Pause / Resume /
Force SAFE / Clear SAFE** buttons; results show in the connection/status area
and the operator control strip.

### UI

Open [http://127.0.0.1:8080](http://127.0.0.1:8080) after `mission_ui` is up.

The dashboard WebSocket is same-origin (`ws://<host>:8080/ws`) and streams the latest
`mission_stream` snapshot. The UI shows mode, key metrics, alerts/events, connection
state, operator pause/resume controls, and broker adapter mode in the footer (raw JSON remains under a collapsible section).
When torch/autonomy publishers are up, optional **Autonomy / MARL / Simulation** tiles
populate from fields folded into `mission_stream`.
Image needs `websockets` so uvicorn can upgrade `/ws`.

### Smoke test (host → localhost)

With the stack already up (compose ports published):

```bash
# from repo root
python prop_algo/deploy/smoke_test.py
python prop_algo/deploy/smoke_test.py --check-streams --torch-streams
```

Checks Redis PING, Mission UI HTTP 200, a WebSocket mission payload that includes
`adapter`, and optionally Redis stream lengths (`mission_stream` must be non-empty).
Uses `REDIS_HOST` / `REDIS_PORT` / `MISSION_UI_URL` if set (defaults: `127.0.0.1:6379`,
`http://127.0.0.1:8080`). Prefer host `redis` + `websocket-client` packages; if the
`redis` package is missing, Redis checks fall back to
`docker exec prop_algo-redis-1 redis-cli …`.

## Brokers (Mock default; MT5/cTrader on host)

Adapter selection is env-driven via `core.adapters.factory` (`BROKER_ADAPTER`).
`market_data_service`, `execution_service`, `mission_control_service`, and monolith
`prop_algo/main.py` all call `register_broker_accounts()`.

| Value | Use |
|-------|-----|
| `mock` (default) | Synthetic data/fills — **compose, k8s light, and torch overlay stay here** |
| `mt5` | Windows host + MetaTrader 5 terminal + `MetaTrader5` pip package |
| `ctrader` | Host/local with a reachable cTrader-style gateway |

**Do not run MetaTrader 5 inside Linux Docker.** The light/torch images do not install
`MetaTrader5`. Leave `BROKER_ADAPTER=mock` in compose unless you mount a custom host
setup (not supported by the default images).

### Required env vars

**Common**

| Variable | Default | Notes |
|----------|---------|--------|
| `BROKER_ADAPTER` | `mock` | `mock` \| `mt5` \| `ctrader` |
| `BROKER_ACCOUNTS` | `ACC1,ACC2` (mock) / `ACC1` (live) | Comma-separated registry ids |

**MT5** (`BROKER_ADAPTER=mt5`)

| Variable | Required | Notes |
|----------|----------|--------|
| `MT5_LOGIN` | yes | Integer account number |
| `MT5_PASSWORD` | yes | |
| `MT5_SERVER` | yes | Broker server name as in MT5 |
| `MT5_PATH` | no | Path to `terminal64.exe` if auto-detect fails |
| `MT5_SYMBOLS` | no | Watchlist, default `EURUSD,GBPUSD` |

**cTrader** (`BROKER_ADAPTER=ctrader`)

| Variable | Required | Notes |
|----------|----------|--------|
| `CTRADER_CLIENT_ID` | yes | |
| `CTRADER_CLIENT_SECRET` | yes | |
| `CTRADER_ACCESS_TOKEN` | yes | Bearer token |
| `CTRADER_BASE_URL` | yes | Gateway base URL (REST + `/stream`) |
| `CTRADER_SYMBOLS` | no | Watchlist, default `EURUSD,GBPUSD` |

Missing deps/creds raise clear `AdapterConfigError` / `RuntimeError` messages — adapters
do **not** invent live fills when the broker is unreachable.

### Host run (MT5 on Windows)

With compose Redis (and the rest of the stack) already up on mock:

```powershell
# from repo root
$env:REDIS_HOST = "127.0.0.1"
$env:PYTHONPATH = "prop_algo"
$env:BROKER_ADAPTER = "mt5"
$env:MT5_LOGIN = "12345678"
$env:MT5_PASSWORD = "secret"
$env:MT5_SERVER = "YourBroker-Server"
# optional: $env:MT5_PATH = "C:\Program Files\MetaTrader 5\terminal64.exe"
pip install MetaTrader5
python -m services.market_data_service.main
python -m services.execution_service.main
# or monolith:
python prop_algo/main.py
```

Stop the compose `market_data_service` / `execution_service` containers first if you
want the host processes to be the only publishers on those streams.

### Host run (cTrader)

```powershell
$env:BROKER_ADAPTER = "ctrader"
$env:CTRADER_CLIENT_ID = "..."
$env:CTRADER_CLIENT_SECRET = "..."
$env:CTRADER_ACCESS_TOKEN = "..."
$env:CTRADER_BASE_URL = "https://your-gateway.example"
```

## Kubernetes (optional)

`k8s/` mirrors the light compose stack with runnable manifests (Redis + all light services + Mission UI). It is **not** a production chart: no HA Redis, no ingress TLS, no broker credentials, no HPA.

### Layout

| Manifest | Purpose |
|----------|---------|
| `namespace.yaml` | `prop-algo` namespace |
| `redis.yaml` | Redis Deployment + Service (`REDIS_HOST=redis`) |
| `light-services.yaml` | ConfigMap + Deployments/Services for compose app services |
| `mission-ui.yaml` | UI on `:8080` (NodePort `30080`) |
| `kustomization.yaml` | Applies the light path above |
| `grafana.yaml` | Optional Grafana (NodePort `30300`) |
| `prometheus.yaml` / `servicemonitor.yaml` | Optional; need **prometheus-operator** CRDs |

### Build and load the image

From the **repo root** (same Dockerfile as compose):

```bash
docker build -f prop_algo/deploy/Dockerfile -t prop_algo:light .
```

Load into a local cluster (pick one):

```bash
# kind
kind load docker-image prop_algo:light

# minikube
minikube image load prop_algo:light
```

Compose builds per-service tags (`prop_algo-mission_ui:latest`, etc.); k8s uses one shared tag `prop_algo:light` with `imagePullPolicy: IfNotPresent`.

### Apply light path

```bash
cd prop_algo/deploy/k8s
kubectl apply -k .
# or: kubectl apply -f namespace.yaml -f redis.yaml -f light-services.yaml -f mission-ui.yaml
```

Wait for pods, then open the UI:

```bash
kubectl -n prop-algo get pods
kubectl -n prop-algo port-forward svc/mission-ui 8080:8080
# or NodePort http://<node>:30080
```

Optional monitoring:

```bash
kubectl apply -f grafana.yaml
# only if prometheus-operator is installed:
kubectl apply -f prometheus.yaml -f servicemonitor.yaml
```

Metrics Services are labeled `app: prop-service` with port name `metrics` (ports 8000–8004 as in compose).

### Roll out a single service

Each Deployment in `light-services.yaml` only differs by `command` (same pattern as compose). To add another process later: copy a Deployment block, change `metadata.name` / labels / `command`.

## MARL / simulation (torch, optional overlay)

`marl_service` and `simulation_service` import `torch` via `marl.*`. They are **not**
in the lean image (`Dockerfile` / default compose). Use `Dockerfile.torch` +
`docker-compose.torch.yml` (profile `torch`) instead.

| Artifact | Role |
|----------|------|
| `Dockerfile` | Light image (no torch) |
| `Dockerfile.torch` | Light deps + CPU `torch` (PyTorch CPU wheel index) → tag `prop_algo:torch` |
| `requirements-torch.txt` | Extra pip deps for the torch image only |
| `docker-compose.torch.yml` | Profile `torch`: `marl_service`, `simulation_service` |

`Dockerfile.torch` installs torch from `https://download.pytorch.org/whl/cpu`. Plain
`pip install torch` on Linux often pulls multi-GB CUDA wheels — avoid that for this overlay.

### Compose overlay (opt-in)

From `prop_algo/deploy` (keeps the light stack; adds MARL + simulation):

```bash
docker compose -f docker-compose.yml -f docker-compose.torch.yml --profile torch up -d --build
```

Only the torch services:

```bash
docker compose -f docker-compose.yml -f docker-compose.torch.yml --profile torch up -d --build marl_service simulation_service
```

Stop torch services (light stack stays up):

```bash
docker compose -f docker-compose.yml -f docker-compose.torch.yml --profile torch stop marl_service simulation_service
```

### Host (against compose Redis)

```bash
# from repo root, with Redis already up (compose redis or local)
set REDIS_HOST=127.0.0.1
set PYTHONPATH=prop_algo
pip install torch
python -m services.marl_service.main
python -m services.simulation_service.main
```
