try:
    from autonomy.safety_layer import SafetyLayer
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.autonomy.safety_layer import SafetyLayer

__all__ = ["SafetyLayer"]
