import random


class LiquidityEngine:
    def __init__(self, registry):
        self.registry = registry

    def simulate(self, symbol, vol, size, platform, is_news, num_accounts):
        spread = 0.0005 + vol * 0.1
        slippage = vol * size * (1 + num_accounts * 0.1)
        latency = 0.1 + (0.05 if is_news else 0)

        return {
            "spread": spread,
            "slippage": slippage,
            "latency": latency,
            "liquidity_score": max(0.0, 1.0 - slippage),
        }

    def simulate_global(self):
        return {"global_liquidity": random.uniform(0.5, 1.0)}
