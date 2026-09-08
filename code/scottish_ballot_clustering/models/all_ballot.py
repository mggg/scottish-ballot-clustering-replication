"""Build weighted clustering models with centers constrained to partial rankings."""

import difflib
from collections.abc import Iterable, Mapping
from enum import StrEnum
from itertools import combinations, permutations, product

import gurobipy as gp
from gurobipy import GRB
from numpy.typing import NDArray

from ._build_coordinate_model import CoordinateModelState, build_coordinate_constraints


class AllBallotModelName(StrEnum):
    """Select the embedding whose ranking constraints apply to all-ballot centers.

    Attributes:
        BORDA (str): Model name selecting pessimistic Borda ranking constraints.
        HEAD_TO_HEAD (str): Model name selecting pairwise ranking-consistency constraints.
    """

    BORDA = "all_ballot_borda_pessimistic"
    HEAD_TO_HEAD = "all_ballot_head_to_head"


def _coerce_all_ballot_model_name(model_name: str | AllBallotModelName) -> AllBallotModelName:
    """Resolve an all-ballot model name to its enum member.

    Args:
        model_name (str | AllBallotModelName): An enum member or its exact, case-sensitive value.

    Returns:
        AllBallotModelName: The matching member; an existing member is returned unchanged.

    Raises:
        ValueError: If model_name is not a recognized model value. The message lists allowed values
            and suggests a close match when available.
    """
    if isinstance(model_name, AllBallotModelName):
        return model_name

    try:
        return AllBallotModelName(model_name)
    except ValueError as exc:
        choices: Iterable[str] = (m.value for m in AllBallotModelName)
        hint = difflib.get_close_matches(model_name, list(choices), n=1)
        msg = f"Unknown model_name {model_name!r}. Allowed: {[m.value for m in AllBallotModelName]}"

        if hint:
            msg += f". Did you mean {hint[0]!r}?"

        raise ValueError(msg) from exc


def _add_all_ballot_head_to_head_constraints(state: CoordinateModelState) -> gp.Model:
    """Constrain center vectors to consistent partial-ranking embeddings in place.

    Preferences are transitive and asymmetric. A tied pair consists of two unranked candidates, and
    ranked candidates precede all unranked candidates. The empty ballot is allowed. This function
    adds constraints and auxiliary variables without changing the model's objective.

    Args:
        state (CoordinateModelState): Shared model state with ``[-1, 0, 1]`` as the allowed values
            and ``n_candidates * (n_candidates - 1) // 2`` coordinates in lexicographic pair order.
            The caller must ensure these preconditions.

    Returns:
        gurobipy.Model: The same model with ranking-consistency constraints added.

    Raises:
        KeyError: If a required center-value indicator is missing from state.
        gurobipy.GurobiError: If Gurobi cannot add the variables or constraints.
    """
    model = state["model"]
    n_clusters = state["n_clusters"]
    n_candidates = state["n_candidates"]
    # n[l,r]: 1 iff candidate l is absent from cluster r's ballot.
    cand_l_not_on_centroid_r_ballot = {
        (l, r): model.addVar(vtype=GRB.BINARY, name=f"n[{l},{r}]")
        for l in range(n_candidates)
        for r in range(n_clusters)
    }

    # NOTE: Uncomment to remove the empty-ballot centers from the feasible space.
    # model.addConstrs(
    #     (
    #         gp.quicksum(cand_l_not_on_centroid_r_ballot[l, r] for l in range(n_candidates))
    #         <= n_candidates - 1
    #         for r in range(n_clusters)
    #     ),
    #     name="nonempty_centroid_ballot",
    # )

    # p[l,m,r]: 1 iff cluster r prefers candidate l to candidate m.
    preferences = {
        (l, m, r): model.addVar(vtype=GRB.BINARY, name=f"p[{l},{m},{r}]")
        for l in range(n_candidates)
        for m in range(n_candidates)
        for r in range(n_clusters)
        if l != m
    }

    _link_pairwise_center_values(state, cand_l_not_on_centroid_r_ballot, preferences)
    _add_preference_order_constraints(
        model, n_candidates, n_clusters, cand_l_not_on_centroid_r_ballot, preferences
    )

    return model


def _link_pairwise_center_values(
    setup: CoordinateModelState,
    absent: Mapping[tuple[int, int], gp.Var],
    preferences: Mapping[tuple[int, int, int], gp.Var],
) -> None:
    """Link pairwise center coordinates to missing-candidate and preference indicators.

    Args:
        setup (CoordinateModelState): Shared model with lexicographic candidate-pair coordinates.
        absent (dict): Binary variables keyed by (candidate, cluster).
        preferences (dict): Binary variables keyed by (preferred candidate, other, cluster).

    Returns:
        None: Add constraints in place. A zero coordinate requires both candidates to be absent;
        positive and negative coordinates select the corresponding preference direction.

    Raises:
        KeyError: If a required coordinate value or preference indicator is absent.
        gurobipy.GurobiError: If Gurobi cannot add the constraints.
    """
    model = setup["model"]
    center_values = setup["center_values"]
    pairs = list(combinations(range(setup["n_candidates"]), 2))
    clusters = range(setup["n_clusters"])

    # Ties can occur only between two absent candidates.
    model.addConstrs(
        (
            center_values[i, r, 0] <= absent[l, r]
            for r in clusters
            for i, (l, _) in enumerate(pairs)
        ),
        name="tie_between_l_and_m_implies_l_not_on_ballot",
    )
    model.addConstrs(
        (
            center_values[i, r, 0] <= absent[m, r]
            for r in clusters
            for i, (_, m) in enumerate(pairs)
        ),
        name="tie_between_l_and_m_implies_m_not_on_ballot",
    )

    # Positive coordinates prefer the first candidate in the pair.
    for r, (i, (first, second)) in product(clusters, enumerate(pairs)):
        model.addLConstr(center_values[i, r, 1] <= preferences[first, second, r])
        model.addLConstr(center_values[i, r, -1] <= preferences[second, first, r])


def _add_preference_order_constraints(
    model: gp.Model,
    n_candidates: int,
    n_clusters: int,
    absent: Mapping[tuple[int, int], gp.Var],
    preferences: Mapping[tuple[int, int, int], gp.Var],
) -> None:
    """Enforce a transitive, asymmetric ranking above the absent candidates in place.

    Args:
        model (gurobipy.Model): Model owning the supplied indicators.
        n_candidates (int): Number of indexed candidates.
        n_clusters (int): Number of labeled clusters.
        absent (dict): Missing-candidate indicators keyed by (candidate, cluster).
        preferences (dict): Preference indicators keyed by (preferred candidate, other, cluster).

    Returns:
        None: Add ranking constraints. Missing candidates cannot beat anyone, and ranked
        candidates must precede missing candidates.

    Raises:
        gurobipy.GurobiError: If Gurobi cannot add the constraints.
    """
    candidates = range(n_candidates)

    for r, (first, second) in product(range(n_clusters), permutations(candidates, 2)):
        # An absent candidate cannot be preferred to another candidate.
        model.addLConstr(absent[first, r] <= 1 - preferences[first, second, r])

        # A ranked candidate precedes an absent candidate.
        model.addLConstr(absent[second, r] <= preferences[first, second, r] + absent[first, r])

        # Preferences are asymmetric.
        model.addLConstr(preferences[first, second, r] + preferences[second, first, r] <= 1)

    # Preferences are transitive for every distinct candidate triple.
    for r, (first, second, third) in product(range(n_clusters), permutations(candidates, 3)):
        model.addLConstr(
            preferences[first, second, r] + preferences[second, third, r]
            <= 1 + preferences[first, third, r]
        )


def _add_all_ballot_borda_pessimistic_constraints(state: CoordinateModelState) -> gp.Model:
    """Constrain center vectors to pessimistic Borda rankings in place.

    Each positive score appears at most once, and using a positive score requires using every larger
    score. Zero may repeat, so omitted candidates and the empty ballot are allowed. The model's
    objective is not changed.

    Args:
        state (CoordinateModelState): Shared model state with one coordinate per candidate and
            sorted allowed values ``0..n_candidates-1``.

    Returns:
        gurobipy.Model: The same model with Borda-ranking constraints added.

    Raises:
        ValueError: If the allowed values are not consecutive or do not start at zero.
        gurobipy.GurobiError: If Gurobi cannot add the constraints.
    """
    model = state["model"]
    z = state["center_values"]

    n_clusters = state["n_clusters"]
    dimension = state["dimension"]
    values_list = state["values"]

    # This model is specifically for pessimistic Borda values, which should be consecutive ints
    # 0..n-1.
    if values_list != list(range(values_list[0], values_list[0] + len(values_list))):
        raise ValueError(
            "Borda pessimistic constraints require consecutive integer values "
            f"(e.g. [0,1,2,...]). Got sorted_value_list={values_list!r}."
        )

    if values_list[0] != 0:
        raise ValueError(
            f"Borda pessimistic constraints expect values starting at 0. Got {values_list!r}."
        )

    # NOTE: Uncomment to remove the empty-ballot centers from the feasible space.
    # model.addConstrs(
    #     (
    #         gp.quicksum(z[i, r, values_list[-1]] for i in range(dimension)) == 1
    #         for r in range(n_clusters)
    #     ),
    #     name="nonempty_centroid_ballot",
    # )

    # For each centroid, each value other than 0 appears at most once
    model.addConstrs(
        (
            gp.quicksum(z[i, r, v] for i in range(dimension)) <= 1
            for r in range(n_clusters)
            for v in values_list[1:]
        ),
        name="borda_value_gt0_at_most_once",
    )

    # If one of the coordinates is v, then also one of the coordinates must be v+1
    # i.e., count(v) - count(v+1) <= 0  for v = 1..n-2
    model.addConstrs(
        (
            gp.quicksum(z[i, r, v] for i in range(dimension))
            - gp.quicksum(z[i, r, v + 1] for i in range(dimension))
            <= 0
            for r in range(n_clusters)
            for v in values_list[1:-1]
        ),
        name="borda_prefix_contiguity",
    )

    return model


def build_all_ballot_model(
    *,
    model_name: str | AllBallotModelName,
    ballots_as_coordinates_array: NDArray,
    weight_vector: NDArray,
    value_vector: NDArray,
    n_candidates: int,
    n_clusters: int = 2,
) -> gp.Model:
    """Build a weighted integer program whose centers represent partial rankings.

    Centers need not be cast ballots, but must satisfy the selected embedding's ranking constraints.
    Empty ballots and empty clusters are allowed. Cluster labels are ordered by distinct ballot
    count, not voter weight. The objective is total weighted Manhattan distance; center coordinates
    are not required to be independent coordinate medians.

    Args:
        model_name (str | AllBallotModelName): All-ballot enum member or its case-sensitive value,
            selecting Borda or head-to-head ranking constraints.
        ballots_as_coordinates_array (NDArray): Embedded ballots of shape ``(b, d)`` with positive
            b. Borda uses one coordinate per candidate; head-to-head uses one per unordered
            candidate pair in lexicographic order.
        weight_vector (NDArray): Nonnegative integer-valued frequencies of shape ``(b,)``.
        value_vector (NDArray): Distinct allowed values: ``0..n_candidates-1`` for Borda or
            ``[-1, 0, 1]`` for head-to-head. Every ballot coordinate must be included.
        n_candidates (int): Positive number of candidates represented by the embedding.
        n_clusters (int): Positive number of labeled clusters, default 2.

    Returns:
        gurobipy.Model: An unsolved model minimizing weighted distance to valid centers. The caller
        owns the model and must dispose of it when finished.

    Raises:
        ValueError: If the model name is unknown, weights or values are not integer-valued, a ballot
            coordinate is not allowed, value_vector is empty, or Borda values are not consecutive
            integers starting at zero.
        KeyError: If the head-to-head value set or dimensions omit a required indicator.
        gurobipy.GurobiError: If Gurobi cannot initialize or construct the model.
    """
    model_name = _coerce_all_ballot_model_name(model_name)

    state: CoordinateModelState = build_coordinate_constraints(
        model_name=model_name,
        ballots_as_coordinates_array=ballots_as_coordinates_array,
        weight_vector=weight_vector,
        value_vector=value_vector,
        n_clusters=n_clusters,
        n_candidates=n_candidates,
    )

    if model_name == AllBallotModelName.BORDA:
        model = _add_all_ballot_borda_pessimistic_constraints(state)

    else:
        model = _add_all_ballot_head_to_head_constraints(state)

    costs = state["costs"]
    dimension = state["dimension"]

    model.setObjective(
        gp.quicksum(costs[i, r] for i in range(dimension) for r in range(n_clusters)),
        GRB.MINIMIZE,
    )

    return model
