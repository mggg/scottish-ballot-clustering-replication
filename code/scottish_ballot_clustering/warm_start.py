"""Prepare MIP starts from cast-ballot partitions or PAM medoids."""

import json
from collections.abc import Sequence
from operator import index
from pathlib import Path
from typing import cast

import gurobipy as gp
import numpy as np
from numpy.typing import NDArray

from .extract_results import extract_solution, validate_solution_profile
from .load_election import validate_profile
from .metrics import pairwise_manhattan
from .saved_solutions import load_saved_solution


def load_pam_medoids(
    path: Path, coordinates: NDArray, weights: NDArray, n_clusters: int
) -> list[int]:
    """Read PAM stdout JSON and check its medoids, memberships, and cost against the profile.

    Use the same election, metric, and loader ordering as the PAM run. Index-only JSON cannot
    establish ballot identity, even when its dimensions and objective agree. Split memberships
    are checked but replaced with whole-ballot assignments when installing the MIP start.
    Malformed or incompatible results raise ValueError before any model starts are changed.
    """
    result = json.loads(path.read_text())
    if not isinstance(result, dict):
        raise ValueError("PAM start must be a JSON object")  # noqa: TRY004
    try:
        medoids = _validate_medoids(result["medoid_indices"], len(coordinates), n_clusters)
        memberships = np.asarray(result["assignment_weights"], dtype=float)
        objective = float(result["objective"])
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError(
            "PAM start requires medoid_indices, assignment_weights, and objective"
        ) from exc
    distances = pairwise_manhattan(coordinates, coordinates[medoids])
    nearest = distances.min(axis=1)
    if (
        memberships.shape != (len(coordinates), n_clusters)
        or not np.isfinite(memberships).all()
        or (memberships < 0).any()
        or not np.allclose(memberships.sum(axis=1), weights, rtol=0, atol=1e-7)
        or ((memberships > 0) & (distances != nearest[:, None])).any()
        or not np.isfinite(objective)
        or not np.isclose(objective, weights @ nearest, rtol=0, atol=1e-6)
    ):
        raise ValueError("PAM start memberships or objective do not match the election and metric")
    return medoids


def _validate_medoids(medoids: Sequence[int], n_ballots: int, n_clusters: int) -> list[int]:
    """Require distinct in-range integer ballot indices, preserving source column order."""
    try:
        indices = [index(i) for i in medoids if not isinstance(i, (bool, np.bool_))]
    except TypeError as exc:
        raise ValueError("PAM medoid indices must be integers") from exc
    if (
        len(indices) != len(medoids)
        or len(indices) != n_clusters
        or not 1 <= n_clusters <= n_ballots
        or len(set(indices)) != n_clusters
        or any(not 0 <= i < n_ballots for i in indices)
    ):
        raise ValueError(
            "PAM medoid indices must be distinct, in range, and match the cluster count"
        )
    return indices


def apply_pam_warm_start(
    model: gp.Model,
    medoid_indices: Sequence[int],
    coordinates: NDArray,
    weights: NDArray,
    n_clusters: int,
) -> None:
    """Prepare target-model centers from PAM's nearest-medoid partition and install a MIP start.

    Embeddings and weights must be the inputs used to build the model. Equal distances choose
    the lowest ballot-index medoid, except that each medoid owns itself. Coordinate-based models
    reorder centers and labels together by distinct ballot count. Coordinate models require
    weighted medians, so they replace medoids with lower weighted medians of the PAM partition.
    Cast-ballot models choose a member medoid for each cluster. All-ballot models optimize valid
    ranking centers with the partition fixed. This auxiliary solve inherits the target settings,
    including a separate time limit of the same duration. Bounds stay free on the target model;
    Gurobi completes auxiliary start variables.

    Args:
        model (gurobipy.Model): Unsolved clustering IP with its solver settings configured.
        medoid_indices (Sequence[int]): Distinct PAM medoid ballot indices for this profile.
        coordinates (NDArray): Embedded ballots in the target model's ballot order.
        weights (NDArray): Positive integer ballot frequencies in the same order.
        n_clusters (int): Target cluster count, matching the number of supplied medoids.

    Returns:
        None: Set assignment and center starts without restricting the target's feasible region.

    Raises:
        ValueError: If medoids or dimensions are invalid, or center preparation finds no incumbent.
        gurobipy.GurobiError: If the auxiliary model cannot be solved or starts cannot be installed.
    """
    medoids = sorted(_validate_medoids(medoid_indices, len(coordinates), n_clusters))
    if coordinates.ndim != 2 or not np.isfinite(coordinates).all():
        raise ValueError("Warm-start coordinates must be a finite matrix")
    if (
        weights.shape != (len(coordinates),)
        or not np.isfinite(weights).all()
        or (weights <= 0).any()
        or (weights != np.floor(weights)).any()
    ):
        raise ValueError("PAM warm-start weights must be positive integer frequencies")
    distances = pairwise_manhattan(coordinates, coordinates[medoids])
    labels = distances.argmin(axis=1)
    labels[medoids] = np.arange(n_clusters)
    apply_warm_start(model, labels.tolist(), coordinates, weights, n_clusters)


def _set_cast_ballot_start(model: gp.Model, medoids: list[int], labels: list[int]) -> None:
    """Install a validated partition whose medoids each belong to their own cluster.

    Args:
        model (gurobipy.Model): Updated cast-ballot model with free optimization bounds.
        medoids (list[int]): Distinct in-range ballot indices, one per cluster in label order.
        labels (list[int]): Valid cluster indices in ballot order, with each medoid owning itself.

    Returns:
        None: Set center and assignment starts without changing bounds or constraints.

    Raises:
        ValueError: If variable dimensions or the model's cluster count disagree with the start.
    """
    assignments = _index_indicator_variables(model, "cluster_assignment")
    centers = _index_indicator_variables(model, "centroid_indicator")
    n_ballots = len(labels)
    count = model.getConstrByName("num_clusters")
    if (
        assignments.keys() != {(i, j) for i in range(n_ballots) for j in range(n_ballots)}
        or centers.keys() != {(i,) for i in range(n_ballots)}
        or count is None
        or count.RHS != len(medoids)
    ):
        raise ValueError("Warm-start dimensions do not match the cast-ballot model")

    for (i,), variable in centers.items():
        variable.Start = int(i in medoids)

    for (i, j), variable in assignments.items():
        variable.Start = int(i == medoids[labels[j]])


def load_starting_assignments(
    path: Path,
    ballots: Sequence[Sequence[int]],
    weights: NDArray,
    candidates: Sequence[str],
    run_type: str,
    n_clusters: int,
) -> list[int]:
    """Extract a compatible cast-ballot partition in the target election's ballot order.

    Saved-solution JSON is matched by ranking and frequency, retaining its stored memberships
    even on distance ties. Candidate names and order must match. A SOL requires the original
    election and loader ordering because it contains no rankings to verify ballot identity.

    Args:
        path (Path): Complete cast-ballot SOL or individual saved-solution JSON from this package.
        ballots (Sequence[Sequence[int]]): Target election's indexed rankings in model order.
        weights (NDArray): Corresponding ballot frequencies.
        candidates (Sequence[str]): Candidate names in model order.
        run_type (str): Target metric, borda or head_to_head.
        n_clusters (int): Target cluster count, which must match the source solution.

    Returns:
        list[int]: Source cluster labels, one per target ballot.

    Raises:
        OSError: If the solution cannot be read.
        ValueError: If the solution is malformed or its model, metric, dimensions, or JSON
            candidate labels and weighted ballot profile do not match.
    """
    metric = "borda_pessimistic" if run_type == "borda" else run_type
    if path.suffix.lower() == ".json":
        return _load_saved_assignments(path, ballots, weights, candidates, metric, n_clusters)

    solution = extract_solution(path)

    if solution["model"] != f"cast_ballot_{metric}":
        raise ValueError("Warm start requires a cast-ballot solution using the same metric")

    if len(solution["centers"]) != n_clusters:
        raise ValueError("Warm-start cluster count does not match the target model")

    validate_solution_profile(solution, ballots, weights, candidates)

    return solution["assignments"]


def _load_saved_assignments(
    path: Path,
    ballots: Sequence[Sequence[int]],
    weights: NDArray,
    candidates: Sequence[str],
    metric: str,
    n_clusters: int,
) -> list[int]:
    """Match a validated saved cast-ballot partition to the target's weighted rankings.

    Args:
        path (Path): Individual saved-solution JSON with both membership representations.
        ballots (Sequence[Sequence[int]]): Distinct zero-based target rankings in model order.
        weights (NDArray): Frequencies corresponding to the target rankings.
        candidates (Sequence[str]): Target candidate names in index order.
        metric (str): Target embedding, borda_pessimistic or head_to_head.
        n_clusters (int): Required number of cluster slots, including empty slots.

    Returns:
        list[int]: Stored cluster indices aligned to the target ballot order, preserving ties.

    Raises:
        OSError: If the JSON cannot be read.
        ValueError: If solution validation fails or metadata or weighted rankings do not match.
    """
    solution = load_saved_solution(path)
    if solution["optimization_model"] != "cast_ballot" or solution["embedding"] != metric:
        raise ValueError("Warm start requires a cast-ballot solution using the same metric")
    if len(solution["centers"]) != n_clusters:
        raise ValueError("Warm-start cluster count does not match the target model")
    if solution["candidates"] != list(candidates):
        raise ValueError("Warm-start candidate names and order do not match the election")

    memberships: dict[tuple[int, ...], tuple[int, int]] = {}
    for cluster, entries in enumerate(solution["ballot_clusters_from_cvr"]):
        for entry in entries:
            ranking, frequency = cast(list[int], entry[0]), cast(int, entry[1])
            memberships[tuple(candidate - 1 for candidate in ranking)] = (frequency, cluster)

    validate_profile(ballots, weights, len(candidates))
    expected_weights = {tuple(ballot): weight for ballot, weight in zip(ballots, weights)}
    stored_weights = {ranking: weight for ranking, (weight, _) in memberships.items()}
    if len(expected_weights) != len(ballots) or expected_weights != stored_weights:
        raise ValueError("Warm-start weighted ballot profile does not match the election")

    return [memberships[tuple(ballot)][1] for ballot in ballots]


def apply_warm_start(
    model: gp.Model,
    assignments: Sequence[int],
    coordinates: NDArray,
    weights: NDArray,
    n_clusters: int,
) -> None:
    """Set assignment and center starts on an unsolved clustering IP.

    Cluster labels are reordered by distinct ballot count to satisfy symmetry constraints.
    Cast-ballot centers minimize weighted distance among members of each supplied cluster, which
    must be nonempty. Coordinate centers use lower weighted medians; all-ballot centers come from
    a copy with assignments fixed.
    The original model's bounds and constraints remain unchanged. Auxiliary starts are left for
    Gurobi to complete. Configure solver parameters before calling: the auxiliary solve inherits
    them, except that its logging is disabled. Its time limit is separate from the final solve's.

    Args:
        model (gurobipy.Model): Unsolved cast-ballot, coordinate, or all-ballot model from this package.
        assignments (Sequence[int]): Starting cluster label for each ballot, in model ballot order.
        coordinates (NDArray): The same embedded ballots used to build the model, shape (b, d).
        weights (NDArray): Nonnegative integer frequencies with positive total weight.
        n_clusters (int): Number of clusters in the model, including any empty clusters.

    Returns:
        None: Set Start attributes for assignment and center indicators in place.

    Raises:
        ValueError: If the model family, partition, or profile dimensions are invalid, or the
            auxiliary optimization finds no incumbent.
        gurobipy.GurobiError: If the model cannot be copied, optimized, or assigned start values.
    """
    model.update()
    family = model.ModelName
    if family.startswith("cast_ballot_"):
        labels = _order_assignments(assignments, len(coordinates), n_clusters)
        medoids = _choose_cluster_medoids(coordinates, weights, labels, n_clusters)
        _set_cast_ballot_start(model, medoids, labels)
        return

    if not family.startswith(("coordinate_", "all_ballot_")):
        raise ValueError("Warm starts require a cast-ballot, coordinate, or all-ballot model")

    x = _index_indicator_variables(model, "ballot_j_to_cluster_r_indicator")
    z = _index_indicator_variables(model, "coord_i_in_centroid_r_is_v")
    _validate_dimensions(x, z, coordinates, weights, n_clusters)
    labels = _order_assignments(assignments, len(coordinates), n_clusters)

    if family.startswith("coordinate_"):
        centers = _compute_median_centers(coordinates, weights, labels, n_clusters, z)
    else:
        centers = _optimize_starting_centers(model, labels, coordinates.shape[1], n_clusters)

    for (j, r), variable in x.items():
        variable.Start = int(labels[j] == r)

    for (i, r, v), variable in z.items():
        variable.Start = int(centers[r, i] == v)


def _choose_cluster_medoids(
    coordinates: NDArray, weights: NDArray, labels: list[int], n_clusters: int
) -> list[int]:
    """Choose the lowest-cost member of each fixed cluster, breaking ties by ballot index.

    Args:
        coordinates (NDArray): Finite embedded ballot matrix in model order.
        weights (NDArray): Nonnegative integer frequencies with positive total weight.
        labels (list[int]): Validated cluster indices in ballot order.
        n_clusters (int): Number of nonempty starting clusters.

    Returns:
        list[int]: Distinct medoid ballot indices in cluster order, each owning its cluster.

    Raises:
        ValueError: If coordinates or weights are invalid, or any cluster has no members.
    """
    if coordinates.ndim != 2 or not np.isfinite(coordinates).all():
        raise ValueError("Warm-start coordinates must be a finite matrix")
    if (
        weights.shape != (len(coordinates),)
        or not np.isfinite(weights).all()
        or (weights < 0).any()
        or (weights != np.floor(weights)).any()
        or weights.sum() <= 0
    ):
        raise ValueError("Warm-start weights must be nonnegative integer frequencies")

    medoids = []
    for cluster in range(n_clusters):
        members = np.flatnonzero(np.asarray(labels) == cluster)
        if not len(members):
            raise ValueError("Cast-ballot warm starts require nonempty clusters")

        costs = pairwise_manhattan(coordinates[members]) @ weights[members]
        medoids.append(int(members[costs.argmin()]))

    return medoids


def _order_assignments(assignments: Sequence[int], n_ballots: int, n_clusters: int) -> list[int]:
    """Validate cluster labels and relabel them by increasing distinct ballot count.

    Args:
        assignments (Sequence[int]): One integer cluster label per ballot.
        n_ballots (int): Expected number of assignments.
        n_clusters (int): Positive number of clusters, including empty clusters.

    Returns:
        list[int]: Relabeled assignments; ties in size retain original cluster order.

    Raises:
        ValueError: If labels are nonintegral, outside the cluster range, or have the wrong length.
    """
    try:
        labels = [index(label) for label in assignments]
    except TypeError as exc:
        raise ValueError("Warm-start assignments must be integer cluster labels") from exc

    if len(labels) != n_ballots or n_clusters < 1:
        raise ValueError("Warm-start assignment dimensions are invalid")

    if any(not 0 <= label < n_clusters for label in labels):
        raise ValueError("Warm-start cluster label is outside the target range")

    sizes = np.bincount(labels, minlength=n_clusters)
    order = sorted(range(n_clusters), key=lambda r: int(sizes[r]))
    relabel = {old: new for new, old in enumerate(order)}

    return [relabel[label] for label in labels]


def _index_indicator_variables(model: gp.Model, prefix: str) -> dict[tuple[int, ...], gp.Var]:
    """Index a model's named indicator group by its integer subscripts.

    Args:
        model (gurobipy.Model): Updated model built by this package.
        prefix (str): Assignment or coordinate-indicator variable name without subscripts.

    Returns:
        dict[tuple[int, ...], gurobipy.Var]: Matching variables keyed by their model indices.
    """
    variables = {}
    for variable in model.getVars():
        if variable.VarName.startswith(prefix + "["):
            subscripts = variable.VarName[len(prefix) + 1 : -1]
            variables[tuple(map(int, subscripts.split(",")))] = variable

    return variables


def _validate_dimensions(
    x: dict[tuple[int, ...], gp.Var],
    z: dict[tuple[int, ...], gp.Var],
    coordinates: NDArray,
    weights: NDArray,
    n_clusters: int,
) -> None:
    """Check profile and variable dimensions before assigning any start values.

    Args:
        x (dict[tuple[int, ...], gurobipy.Var]): Indicators indexed by (ballot, cluster).
        z (dict[tuple[int, ...], gurobipy.Var]): Indicators indexed by (coordinate, cluster, value).
        coordinates (NDArray): Embedded ballots supplied for this model.
        weights (NDArray): Corresponding nonnegative integer frequencies.
        n_clusters (int): Expected number of clusters.

    Returns:
        None: Leave valid inputs unchanged.

    Raises:
        ValueError: If the profile or variable dimensions are incompatible.
    """
    if coordinates.ndim != 2 or not np.isfinite(coordinates).all():
        raise ValueError("Warm-start coordinates must be a finite matrix")

    if (
        weights.shape != (len(coordinates),)
        or not np.isfinite(weights).all()
        or (weights < 0).any()
        or (weights != np.floor(weights)).any()
        or weights.sum() <= 0
    ):
        raise ValueError("Warm-start weights must be nonnegative integer frequencies")

    if x.keys() != {(j, r) for j in range(len(coordinates)) for r in range(n_clusters)}:
        raise ValueError("Warm-start ballot or cluster count does not match the model")

    if not np.isin(coordinates, list({v for _, _, v in z})).all():
        raise ValueError("Warm-start coordinates are outside the model's allowed values")

    expected = {(i, r) for i in range(coordinates.shape[1]) for r in range(n_clusters)}
    if {(i, r) for i, r, _ in z} != expected:
        raise ValueError("Warm-start coordinate dimensions do not match the model")


def _compute_median_centers(
    coordinates: NDArray,
    weights: NDArray,
    labels: list[int],
    n_clusters: int,
    z: dict[tuple[int, ...], gp.Var],
) -> NDArray:
    """Compute lower weighted medians, using the smallest allowed value for empty clusters.

    Args:
        coordinates (NDArray): Embedded ballots in model order.
        weights (NDArray): Validated ballot frequencies.
        labels (list[int]): Ordered cluster assignments.
        n_clusters (int): Number of clusters.
        z (dict[tuple[int, ...], gurobipy.Var]): Model center indicators defining allowed values.

    Returns:
        NDArray: Center coordinates of shape (n_clusters, dimensions).

    Raises:
        ValueError: If an empty cluster has no allowed value for a coordinate.
    """
    centers = np.empty((n_clusters, coordinates.shape[1]))
    labels_array = np.array(labels)
    for r in range(n_clusters):
        members = labels_array == r
        cluster_weights = weights[members]
        total = cluster_weights.sum()

        for i in range(coordinates.shape[1]):
            if total == 0:
                centers[r, i] = min(v for coord, cluster, v in z if (coord, cluster) == (i, r))
                continue

            values = coordinates[members, i]
            order = np.argsort(values)
            cumulative = cluster_weights[order].cumsum()
            median = np.searchsorted(cumulative, total / 2, side="left")
            centers[r, i] = values[order[median]]

    return centers


def _optimize_starting_centers(
    model: gp.Model, labels: list[int], dimension: int, n_clusters: int
) -> NDArray:
    """Optimize valid ranking centers with the starting partition fixed in a temporary model.

    Args:
        model (gurobipy.Model): Updated all-ballot model with desired solver parameters.
        labels (list[int]): Ordered starting cluster labels.
        dimension (int): Number of coordinates per center.
        n_clusters (int): Number of clusters.

    Returns:
        NDArray: Feasible center coordinates of shape (n_clusters, dimension). An auxiliary
        time limit may return an incumbent without proving the best centers for this partition.

    Raises:
        ValueError: If the auxiliary solve produces no incumbent.
        gurobipy.GurobiError: If copying or solving the model fails.
    """
    with model.copy() as fixed:
        fixed.Params.LogFile = ""
        fixed.Params.OutputFlag = 0
        for (j, r), variable in _index_indicator_variables(
            fixed, "ballot_j_to_cluster_r_indicator"
        ).items():
            variable.LB = variable.UB = int(labels[j] == r)

        fixed.optimize()
        if fixed.SolCount == 0:
            raise ValueError(f"No feasible warm-start centers found (status {fixed.Status})")

        centers = np.empty((n_clusters, dimension))
        for (i, r, value), variable in _index_indicator_variables(
            fixed, "coord_i_in_centroid_r_is_v"
        ).items():
            if variable.X > 0.5:
                centers[r, i] = value

    return centers
