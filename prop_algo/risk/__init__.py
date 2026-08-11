"""Risk subsystem (budgets, anomalies, clusters, liquidity, governance, unified core).

Heavy autonomy re-exports are available as ``risk.autonomous_governance`` /
``risk.autonomous_risk`` and are not imported here so light services can load
``risk.*`` without pulling optional MARL/torch deps.
"""

__all__: list[str] = []
