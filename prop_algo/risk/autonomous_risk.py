try:
    from autonomy.autonomous_risk import AutonomousRisk
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.autonomy.autonomous_risk import AutonomousRisk

__all__ = ["AutonomousRisk"]
