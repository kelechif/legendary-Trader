try:
    from autonomy.autonomous_governance import AutonomousGovernance
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.autonomy.autonomous_governance import AutonomousGovernance

__all__ = ["AutonomousGovernance"]
