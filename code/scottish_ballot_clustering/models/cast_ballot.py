"""Build weighted clustering models with centers drawn from cast ballots."""

from enum import StrEnum

import gurobipy as gp
from gurobipy import GRB
from numpy.typing import NDArray


class CastBallotModelName(StrEnum):
    """Identify the metric used to name a cast-ballot model.

    Attributes:
        BORDA (str): Model name for pessimistic Borda distances.
        HEAD_TO_HEAD (str): Model name for head-to-head distances.
    """

    BORDA = "cast_ballot_borda_pessimistic"
    HEAD_TO_HEAD = "cast_ballot_head_to_head"


def build_cast_ballot_model(
    *,
    model_name: str,
    n_ballots: int,
    weight_vector: NDArray,
    cost_matrix: NDArray,
    n_clusters: int = 2,
) -> gp.Model:
    """Build a weighted integer program with centers restricted to cast ballots.

    Exactly n_clusters centers are selected, every ballot is assigned to one center, and selected
    centers are assigned to themselves. The objective sums ``weight_vector[j] * cost_matrix[i, j]``
    for assignments of ballot j to center i. Assignment variables use
    ``(center ballot, assigned ballot)`` indexing.

    The caller must supply compatible array shapes and nonnegative, finite costs and weights. These
    preconditions are not validated here. The model is not optimized; the caller owns it and must
    dispose of it when finished.

    Args:
        model_name (str): Gurobi model label. It does not select or calculate distances.
        n_ballots (int): Positive number of distinct cast rankings.
        weight_vector (NDArray): Ballot frequencies of shape ``(n_ballots,)``.
        cost_matrix (NDArray): Unweighted distances of shape ``(n_ballots, n_ballots)``; row i is
            the candidate center and column j is the assigned ballot.
        n_clusters (int): Number of selected centers, default 2. Must lie between 1 and n_ballots
            for the intended clustering problem.

    Returns:
        gurobipy.Model: An unsolved model minimizing the total weighted assignment cost.

    Raises:
        gurobipy.GurobiError: If Gurobi cannot initialize or construct the model, including when a
            suitable license is unavailable.
    """
    model = gp.Model(model_name)

    # Centroid binary variables y_i
    # Assignment variables x_{i,j}
    y = model.addVars(n_ballots, vtype=GRB.BINARY, name="centroid_indicator")
    x = model.addVars(n_ballots, n_ballots, vtype=GRB.BINARY, name="cluster_assignment")

    # if the i's are the medians, then for each j, x_{i,j} is 1 if j is assigned to a cluster
    # with centroid i and y[i] == 1 if i is a centroid
    model.addConstrs(
        (x[i, j] <= y[i] for j in range(n_ballots) for i in range(n_ballots)),
        name="ballot_assignment",
    )

    # if the i's are the medians, then for each j, the sum over i of x_{i,j} is 1
    # so each j is assigned to exactly one median i
    model.addConstrs(
        (gp.quicksum(x[i, j] for i in range(n_ballots)) == 1 for j in range(n_ballots)),
        "ballot_to_single_cluster",
    )

    # All centroids must be assigned to their own cluster
    model.addConstrs(
        (y[i] == x[i, i] for i in range(n_ballots)),
        name="centroid_only_when_assigned_to_itself",
    )

    # The number of selected centroids must equal the number of clusters
    model.addConstr(gp.quicksum(y[i] for i in range(n_ballots)) == n_clusters, name="num_clusters")

    # (Whether j is assigned to i) * (cost of assigning j to i) * (weight of j)
    model.setObjective(
        gp.quicksum(
            x[i, j] * cost_matrix[i, j] * weight_vector[j]
            for i in range(n_ballots)
            for j in range(n_ballots)
        ),
        GRB.MINIMIZE,
    )

    return model
