try:
    from autonomy.autonomous_evolution import AutonomousEvolution
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.autonomy.autonomous_evolution import AutonomousEvolution

__all__ = ["AutonomousEvolution"]
