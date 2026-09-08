"""Cluster a small weighted election directly with PAM, without a Gurobi license."""

import json

import numpy as np

from scottish_ballot_clustering.metrics import ballot_borda_vector
from scottish_ballot_clustering.pam import pam


def main() -> None:
    """Run weighted PAM and show medoids, membership weights, objective, and termination status.

    Membership rows follow ballot order; columns follow medoid_indices. A ballot tied between
    nearest medoids splits its frequency equally by default. Local optimality does not certify a
    global optimum.

    Returns:
        None: Print the complete PAM result as JSON and the medoid rankings.
    """
    ballots = [(0, 1, 2), (1, 2), (2, 0), (0,)]
    weights = np.array([5, 3, 2, 1])
    coordinates = np.array([ballot_borda_vector(ballot=list(b), n_candidates=3) for b in ballots])
    result = pam(coordinates, weights, n_clusters=2)
    print(json.dumps(result, indent=2))
    print("Medoid rankings:", [ballots[j] for j in result["medoid_indices"]])


if __name__ == "__main__":
    main()
