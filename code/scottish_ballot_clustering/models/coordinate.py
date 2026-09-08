"""Build weighted clustering models with independent coordinate medians."""

import difflib
from collections.abc import Iterable
from enum import StrEnum

import gurobipy as gp
from gurobipy import GRB
from numpy.typing import NDArray

from ._build_coordinate_model import CoordinateModelState, build_coordinate_constraints


class CoordinateModelName(StrEnum):
    """Identify the metric used to name a coordinate-center model.

    Attributes:
        BORDA (str): Model name for pessimistic Borda coordinates.
        HEAD_TO_HEAD (str): Model name for head-to-head coordinates.
    """

    BORDA = "coordinate_borda_pessimistic"
    HEAD_TO_HEAD = "coordinate_head_to_head"


def _coerce_coordinate_model_name(model_name: str | CoordinateModelName) -> CoordinateModelName:
    """Resolve a coordinate-model name to its enum member.

    Args:
        model_name (str | CoordinateModelName): An enum member or its exact, case-sensitive value.

    Returns:
        CoordinateModelName: The matching member; an existing member is returned unchanged.

    Raises:
        ValueError: If model_name is not a recognized model value. The message lists allowed values
            and suggests a close match when available.
    """
    if isinstance(model_name, CoordinateModelName):
        return model_name

    try:
        return CoordinateModelName(model_name)
    except ValueError as exc:
        choices: Iterable[str] = (m.value for m in CoordinateModelName)
        hint = difflib.get_close_matches(model_name, list(choices), n=1)
        msg = (
            f"Unknown model_name {model_name!r}. Allowed: {[m.value for m in CoordinateModelName]}"
        )

        if hint:
            msg += f". Did you mean {hint[0]!r}?"

        raise ValueError(msg) from exc


def build_coordinate_model(
    *,
    model_name: str | CoordinateModelName,
    ballots_as_coordinates_array: NDArray,
    weight_vector: NDArray,
    value_vector: NDArray,
    n_candidates: int,
    n_clusters: int = 2,
) -> gp.Model:
    """Build a weighted integer program with independent coordinate medians.

    Each cluster center chooses a weighted median in every coordinate. The resulting vector need not
    represent a consistent ballot. The objective is total weighted Manhattan distance; empty
    clusters are allowed, and labels are ordered by distinct ballot count rather than voter weight.
    Model names label the metric but do not construct or validate the embedding.

    Args:
        model_name (str | CoordinateModelName): Coordinate-model enum member or its case-sensitive
            string value.
        ballots_as_coordinates_array (NDArray): Embedded ballots of shape ``(b, d)``, with positive
            ballot count b and coordinates in value_vector.
        weight_vector (NDArray): Nonnegative integer-valued frequencies of shape ``(b,)``.
        value_vector (NDArray): Nonempty one-dimensional array of distinct integer-valued center
            coordinates. Use ``0..n_candidates-1`` for Borda or ``[-1, 0, 1]`` for head-to-head
            embeddings.
        n_candidates (int): Positive number of candidates represented by the embedding.
        n_clusters (int): Positive number of labeled clusters, default 2.

    Returns:
        gurobipy.Model: An unsolved model minimizing weighted coordinate distance. The caller owns
        the model and must dispose of it when finished.

    Raises:
        ValueError: If the model name is unknown, weights or allowed values are not integer-valued,
            a coordinate is not allowed, or value_vector is empty.
        gurobipy.GurobiError: If Gurobi cannot initialize or construct the model.
    """
    model_name = _coerce_coordinate_model_name(model_name)

    state: CoordinateModelState = build_coordinate_constraints(
        model_name=model_name,
        ballots_as_coordinates_array=ballots_as_coordinates_array,
        weight_vector=weight_vector,
        value_vector=value_vector,
        n_clusters=n_clusters,
        n_candidates=n_candidates,
    )

    _add_weighted_median_constraints(state, weight_vector.sum())

    model = state["model"]
    costs = state["costs"]
    dimension = state["dimension"]
    model.setObjective(
        gp.quicksum(costs[i, r] for i in range(dimension) for r in range(n_clusters)),
        GRB.MINIMIZE,
    )

    return model


def _add_weighted_median_constraints(state: CoordinateModelState, total_weight: int) -> None:
    """Require each selected coordinate value to be a weighted median in place.

    The two balance inequalities belong together: at least half the weight is at or below the
    selected value, and at most half is strictly below it. Total weight, independent of coordinate
    spacing, bounds the relaxation for an unselected value.

    Args:
        state (CoordinateModelState): Shared coordinate model, center indicators, and weight totals.
        total_weight (int): Sum of all ballot frequencies, used as the median big-M bound.

    Returns:
        None: Add left- and right-balance constraints without changing the objective.

    Raises:
        gurobipy.GurobiError: If Gurobi cannot add the constraints.
    """
    model = state["model"]
    sorted_value_list = state["values"]
    dimension = state["dimension"]
    n_clusters = state["n_clusters"]
    coordinate_weights = state["coordinate_weights"]
    center_values = state["center_values"]
    M = total_weight

    # --
    # Encode the weighted median test using big-M constraints
    # --
    v_to_values_lt_v = {v: [v2 for v2 in sorted_value_list if v2 < v] for v in sorted_value_list}
    v_to_values_leq_v = {v: [v2 for v2 in sorted_value_list if v2 <= v] for v in sorted_value_list}
    total_weight_at_coord_i_in_cluster_r = {
        (i, r): gp.quicksum(coordinate_weights[i, r, v] for v in sorted_value_list)
        for i in range(dimension)
        for r in range(n_clusters)
    }

    model.addConstrs(
        (
            2 * gp.quicksum(coordinate_weights[i, r, vle] for vle in v_to_values_leq_v[v_target])
            >= total_weight_at_coord_i_in_cluster_r[i, r] - M * (1 - center_values[i, r, v_target])
            for i in range(dimension)
            for r in range(n_clusters)
            for v_target in sorted_value_list
        ),
        name="median_right_balance_all",
    )
    model.addConstrs(
        (
            2 * gp.quicksum(coordinate_weights[i, r, vl] for vl in v_to_values_lt_v[v_target])
            <= total_weight_at_coord_i_in_cluster_r[i, r] + M * (1 - center_values[i, r, v_target])
            for i in range(dimension)
            for r in range(n_clusters)
            for v_target in sorted_value_list
        ),
        name="median_left_balance_all",
    )
