import numpy as np

from .cluster_state import ClusterState


class ClusterDetector:
    def __init__(self, registry):
        self.registry = registry
        self.state = ClusterState()

    def detect(self):
        exposures = []
        for name, profile in self.registry.accounts.items():
            acc = profile["adapter"].get_account_info()
            exposures.append(acc["equity"])

        if len(exposures) < 2:
            return []

        # corrcoef on a 1D equity snapshot is not a 2x2 matrix; skip safely.
        mat = np.corrcoef(exposures)
        if getattr(mat, "ndim", 0) < 2 or mat.shape[0] < 2:
            self.state.state["clusters"] = []
            return []

        corr = mat[0][1]
        clusters = []
        if corr > 0.7:
            clusters.append("High correlation cluster")

        self.state.state["clusters"] = clusters
        return clusters
