from .risk_budget_state import RiskBudgetState


class RiskBudgetEngine:
    def __init__(self, registry):
        self.registry = registry
        self.state = RiskBudgetState()

    def compute(self):
        budgets = {}
        for name, profile in self.registry.accounts.items():
            acc = profile["adapter"].get_account_info()
            balance = acc["balance"]
            equity = acc["equity"]
            dd = equity - balance

            risk_score = 1.0
            if dd < -100:
                risk_score = 0.5
            if dd < -200:
                risk_score = 0.2

            budgets[name] = risk_score

        self.state.state["accounts"] = budgets
        self.state.save()
        return budgets
