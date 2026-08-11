class AnomalyDetector:
    def __init__(self):
        self.state = {"anomalies": []}

    def run(self, df=None, execution=None, liquidity=None):
        anomalies = []

        if df is not None:
            vol = df["close"].pct_change().std()
            if vol > 0.02:
                anomalies.append("Volatility spike")

        if execution and execution.get("routes"):
            if execution["routes"].count("MARKET") > 10:
                anomalies.append("Execution overload")

        if liquidity and liquidity.get("global_liquidity", 1) < 0.6:
            anomalies.append("Liquidity stress")

        self.state["anomalies"] = anomalies
        return anomalies
