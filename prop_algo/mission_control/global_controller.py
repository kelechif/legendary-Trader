try:
    from autonomy.global_controller import GlobalController
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.autonomy.global_controller import GlobalController

__all__ = ["GlobalController"]
