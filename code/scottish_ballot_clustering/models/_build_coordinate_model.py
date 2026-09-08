"""Construct shared coordinate-assignment and distance-cost constraints."""

from typing import TypedDict, cast

import gurobipy as gp
import numpy as np
from gurobipy import GRB, Model, Var, tupledict
from numpy.typing import NDArray


class CoordinateModelState(TypedDict):
    """Hold the shared coordinate model and references to its decision variables.

    Indices i, j, and r denote coordinates, cast ballots, and clusters respectively; v is a
    coordinate value. Variable dictionaries belong to model and share its lifetime.

    Attributes:
        model (gurobipy.Model): Unsolved model with assignment and coordinate-cost constraints.
        values (list[int]): Allowed coordinate values in increasing order.
        dimension (int): Number of coordinates per embedded ballot.
        n_candidates (int): Number of candidates represented by the embedding.
        n_clusters (int): Number of labeled clusters, including any empty clusters.
        coordinate_weights (gurobipy.tupledict): Integer
            variables W[i, r, v] totaling the weight of assigned ballots whose coordinate i equals
            v, regardless of the center's coordinate value.
        assignments (gurobipy.tupledict): Binary assignment variables x[j, r].
        center_values (gurobipy.tupledict): Binary center-value indicators z[i, r, v].
        costs (gurobipy.tupledict): Integer costs C[i, r] for each
            coordinate and cluster.
        cost_bound (int): Total ballot weight times coordinate range; bounds each coordinate cost.
    """

    model: Model
    values: list[int]
    dimension: int
    n_candidates: int
    n_clusters: int
    coordinate_weights: tupledict[tuple[int, int, int], Var]
    assignments: tupledict[tuple[int, int], Var]
    center_values: tupledict[tuple[int, int, int], Var]
    costs: tupledict[tuple[int, int], Var]
    cost_bound: int


def build_coordinate_constraints(
    *,
    model_name: str,
    ballots_as_coordinates_array: NDArray,
    weight_vector: NDArray,
    value_vector: NDArray,
    n_candidates: int,
    n_clusters: int = 2,
) -> CoordinateModelState:
    """Build shared assignment, center-value, and coordinate-cost constraints.

    Each ballot is assigned once, each center coordinate selects one allowed value, and clusters are
    ordered by their number of distinct assigned ballots. Empty clusters are allowed. This function
    does not set a minimization objective or require centers to be weighted medians or consistent
    rankings.

    Args:
        model_name (str): Gurobi model label.
        ballots_as_coordinates_array (NDArray): Embedded ballots of shape ``(b, d)``, where b is the
            positive ballot count and d is the coordinate count.
        weight_vector (NDArray): Nonnegative integer-valued frequencies of shape ``(b,)``.
        value_vector (NDArray): Nonempty one-dimensional array of distinct integer-valued allowed
            coordinates. Every ballot coordinate must appear in this array.
        n_candidates (int): Positive candidate count, recorded for ranking constraints.
        n_clusters (int): Positive number of labeled clusters, default 2.

    Returns:
        CoordinateModelState: The unsolved model, dimensions, value list, and variable dictionaries.
        The caller owns the model and must dispose of it when finished.

    Raises:
        ValueError: If weights or allowed values are not integer-valued, a ballot coordinate is not
            allowed, or value_vector is empty.
        gurobipy.GurobiError: If Gurobi cannot initialize or construct the model.
    """
    values = _validate_coordinate_inputs(ballots_as_coordinates_array, weight_vector, value_vector)
    n_ballots, dimension = ballots_as_coordinates_array.shape
    cost_bound = int(weight_vector.sum()) * (values[-1] - values[0])
    setup = _create_coordinate_variables(
        model_name, n_ballots, dimension, n_candidates, n_clusters, values, cost_bound
    )

    _add_assignment_constraints(setup, n_ballots)
    _add_coordinate_weight_constraints(setup, ballots_as_coordinates_array, weight_vector)
    _add_coordinate_cost_constraints(setup)

    return setup


def _validate_coordinate_inputs(
    coordinates: NDArray, weights: NDArray, values: NDArray
) -> list[int]:
    """Validate integer weights and allowed coordinates before creating a solver model.

    Args:
        coordinates (NDArray): Ballot embeddings whose values must occur in values.
        weights (NDArray): Integer-valued ballot frequencies.
        values (NDArray): Nonempty integer-valued array of allowed center coordinates.

    Returns:
        list[int]: Allowed coordinate values in ascending order.

    Raises:
        ValueError: If weights or allowed values are not integer-valued, values is empty, or a
            ballot coordinate is not allowed.
    """
    if not (values.astype(np.int64) == values).all():
        raise ValueError("Value vector must be integer type")

    sorted_values = sorted(values.astype(int).tolist())

    if not sorted_values:
        raise ValueError("Value vector must be nonempty")

    if not (weights.astype(np.int64) == weights).all():
        raise ValueError("Weight vector must be integer type")

    allowed = set(map(float, sorted_values))

    for ballot_row in coordinates:
        if not set(map(float, ballot_row)).issubset(allowed):
            raise ValueError(
                "All coordinates in ballots must be in the value vector. "
                f"Ballot {ballot_row} contains values not in {sorted_values}."
            )

    return sorted_values


def _create_coordinate_variables(
    model_name: str,
    n_ballots: int,
    dimension: int,
    n_candidates: int,
    n_clusters: int,
    values: list[int],
    cost_bound: int,
) -> CoordinateModelState:
    """Create the shared coordinate model's variables and dimension metadata.

    Args:
        model_name (str): Solver model label.
        n_ballots (int): Number of distinct ballots.
        dimension (int): Number of coordinates per ballot.
        n_candidates (int): Candidate count represented by the embedding.
        n_clusters (int): Number of labeled clusters.
        values (list[int]): Sorted allowed coordinate values.
        cost_bound (int): Total ballot weight times the coordinate range.

    Returns:
        CoordinateModelState: New solver model and variable dictionaries. Assignments use
        (ballot, cluster) indices, unlike cast-ballot assignments. Center indicators and weights use
        (coordinate, cluster, value); costs use (coordinate, cluster). The caller owns the model.

    Raises:
        gurobipy.GurobiError: If model or variable creation fails.
    """
    model = gp.Model(model_name)
    assignments = cast(
        tupledict[tuple[int, int], Var],
        model.addVars(
            n_ballots, n_clusters, vtype=GRB.BINARY, name="ballot_j_to_cluster_r_indicator"
        ),
    )
    center_values = model.addVars(
        range(dimension),
        range(n_clusters),
        values,
        vtype=GRB.BINARY,
        name="coord_i_in_centroid_r_is_v",
    )
    coordinate_weights = model.addVars(
        range(dimension),
        range(n_clusters),
        values,
        vtype=GRB.INTEGER,
        name="wt_given_to_coord_i_in_cluster_r_with_centroid_value_v",
    )
    costs = cast(
        tupledict[tuple[int, int], Var],
        model.addVars(
            dimension, n_clusters, vtype=GRB.INTEGER, name="contribution_of_coord_i_to_cluster_r"
        ),
    )

    return CoordinateModelState(
        model=model,
        values=values,
        dimension=dimension,
        n_candidates=n_candidates,
        n_clusters=n_clusters,
        cost_bound=cost_bound,
        assignments=assignments,
        center_values=center_values,
        coordinate_weights=coordinate_weights,
        costs=costs,
    )


def _add_assignment_constraints(setup: CoordinateModelState, n_ballots: int) -> None:
    """Assign each ballot once and select one value per center coordinate in place.

    Cluster labels are ordered by distinct ballot count, not voter weight. Empty clusters remain
    feasible and still select a value in every coordinate.

    Args:
        setup (CoordinateModelState): Shared coordinate model and variables.
        n_ballots (int): Number of distinct ballots in the assignment array.

    Returns:
        None: Add assignment, center-selection, and cluster-ordering constraints to setup's model.

    Raises:
        gurobipy.GurobiError: If Gurobi cannot add the constraints.
    """
    model = setup["model"]
    assignments = setup["assignments"]
    center_values = setup["center_values"]
    n_clusters = setup["n_clusters"]

    model.addConstrs(
        (gp.quicksum(assignments[j, r] for r in range(n_clusters)) == 1 for j in range(n_ballots)),
        name="ballot_to_single_cluster",
    )
    model.addConstrs(
        (
            gp.quicksum(center_values[i, r, v] for v in setup["values"]) == 1
            for i in range(setup["dimension"])
            for r in range(n_clusters)
        ),
        name="single_centroid_value_per_cluster",
    )

    model.addConstrs(
        (assignments.sum("*", r) <= assignments.sum("*", r + 1) for r in range(n_clusters - 1)),
        name="nondecreasing_cluster_sizes",
    )


def _add_coordinate_weight_constraints(
    setup: CoordinateModelState, coordinates: NDArray, weights: NDArray
) -> None:
    """Link cluster coordinate-weight totals to ballot assignments in place.

    Args:
        setup (CoordinateModelState): Shared coordinate model and variables.
        coordinates (NDArray): Ballot embeddings in assignment-row order.
        weights (NDArray): Integer ballot frequencies in the same order.

    Returns:
        None: Constrain W[i, r, v] to the assigned weight whose coordinate i equals v, regardless
        of the selected center value.

    Raises:
        gurobipy.GurobiError: If Gurobi cannot add the constraints.
    """
    assignments = setup["assignments"]
    coordinate_weights = setup["coordinate_weights"]
    matching_ballots = {
        (i, v): [j for j in range(len(coordinates)) if coordinates[j, i] == v]
        for i in range(setup["dimension"])
        for v in setup["values"]
    }

    setup["model"].addConstrs(
        (
            coordinate_weights[i, r, v]
            == gp.quicksum(weights[j] * assignments[j, r] for j in matching_ballots[i, v])
            for i in range(setup["dimension"])
            for r in range(setup["n_clusters"])
            for v in setup["values"]
        ),
        name="maximum_weight_per_coordinate_and_centroid_value",
    )


def _add_coordinate_cost_constraints(setup: CoordinateModelState) -> None:
    """Bind each coordinate cost to the selected center value using paired big-M bounds.

    Args:
        setup (CoordinateModelState): Shared coordinate model with cost_bound equal to total weight
            times coordinate range. This bounds the largest weighted distance for one coordinate.

    Returns:
        None: Add both sides of each conditional distance equality in place.

    Raises:
        gurobipy.GurobiError: If Gurobi cannot add the constraints.
    """
    model = setup["model"]
    center_values = setup["center_values"]
    coordinate_weights = setup["coordinate_weights"]
    costs = setup["costs"]
    values = setup["values"]
    cost_bound = setup["cost_bound"]

    model.addConstrs(
        costs[i, r]
        - gp.quicksum(abs(target - v) * coordinate_weights[i, r, v] for v in values)
        - cost_bound * (1 - center_values[i, r, target])
        <= 0
        for i in range(setup["dimension"])
        for r in range(setup["n_clusters"])
        for target in values
    )
    model.addConstrs(
        gp.quicksum(abs(target - v) * coordinate_weights[i, r, v] for v in values)
        - costs[i, r]
        - cost_bound * (1 - center_values[i, r, target])
        <= 0
        for i in range(setup["dimension"])
        for r in range(setup["n_clusters"])
        for target in values
    )
