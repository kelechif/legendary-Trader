from prometheus_client import Gauge, start_http_server


class Metrics:
    def __init__(self, port):
        start_http_server(port)

        self.equity = Gauge("equity", "Account equity", ["account"])
        self.liquidity = Gauge("liquidity", "Global liquidity")
        self.anomaly_count = Gauge("anomaly_count", "Number of anomalies")
        self.unified_mode = Gauge("unified_mode", "Unified core mode")
        self.exec_latency = Gauge("exec_latency", "Execution latency")
        self.learning_fitness = Gauge("learning_fitness", "Fitness score", ["strategy"])
