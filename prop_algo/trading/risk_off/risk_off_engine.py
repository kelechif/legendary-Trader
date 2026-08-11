class RiskOffEngine:
    def compute(self, account, df, *args):
        dd = account["equity"] - account["balance"]
        if dd < -100:
            return 0.2, {"reason": "drawdown"}
        return 1.0, {"reason": "normal"}
