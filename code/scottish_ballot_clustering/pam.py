"""Cluster weighted ballot embeddings using Partitioning Around Medoids."""

from collections.abc import Iterator
from operator import index
from time import perf_counter
from typing import Literal, SupportsIndex, TypedDict

import numpy as np
from numpy.typing import NDArray

from .metrics import pairwise_manhattan

type PAMStatus = Literal["local_optimum", "iteration_limit", "time_limit"]


class PAMResult(TypedDict):
    """Weighted medoid clustering with explicit search termination and membership columns."""

    medoid_indices: list[int]
    assignment_weights: list[list[float]]
    objective: float
    status: PAMStatus
    iterations: int
    runtime_seconds: float


def pam(
    coordinates: NDArray,
    weights: NDArray,
    n_clusters: SupportsIndex = 2,
    *,
    max_iter: SupportsIndex = 300,
    time_limit: float | None = None,
    share_ties: bool = True,
) -> PAMResult:
    """Find cast-ballot medoids by weighted greedy BUILD and best-improvement SWAP.

    BUILD adds the ballot giving the lowest weighted cost until n_clusters centers have been
    chosen. Each SWAP pass evaluates every replacement of one medoid by a nonmedoid and applies
    the best strict improvement. Candidates are scanned in input order and medoid slots in
    selection order, making ties deterministic. A completed pass without an improving swap
    establishes a one-swap local optimum, not a global optimum.

    Args:
        coordinates (NDArray): Finite ballot embeddings of shape ``(n_ballots, dimensions)``.
        weights (NDArray): Positive, finite ballot weights of shape ``(n_ballots,)``.
        n_clusters (SupportsIndex): Distinct medoid count, between 1 and n_ballots inclusive.
            Python integers, NumPy integers, and other objects implementing __index__ are accepted.
        max_iter (SupportsIndex): Maximum accepted swaps. Zero returns the BUILD solution.
        time_limit (float | None): Positive time limit in seconds for SWAP, checked between
            candidate evaluations. Distance computation and BUILD are excluded; None is unlimited.
        share_ties (bool): Whether to split each ballot's weight equally among nearest centers.
            If False, use the lowest-indexed nearest medoid, with medoids owning themselves.

    Returns:
        dict: Sorted medoid_indices, assignment_weights of shape ``(n_ballots, n_clusters)``,
        weighted objective, accepted-swap iterations, total runtime_seconds, and status:
        "local_optimum", "iteration_limit", or "time_limit". All terminations return a feasible
        clustering. Assignment columns correspond to medoid_indices and row sums equal weights.

    Raises:
        ValueError: If array shapes, values, cluster count, iteration count, or time limit are
            invalid, or the weighted distance bound overflows. Counts must support exact integer
            conversion through __index__; floats are rejected. max_iter must be nonnegative.
    """
    started = perf_counter()
    try:
        cluster_count = index(n_clusters)
        iteration_limit = index(max_iter)
    except TypeError as exc:
        raise ValueError("n_clusters and max_iter must support exact integer conversion") from exc

    coordinates, weights = _validate_inputs(
        coordinates, weights, cluster_count, iteration_limit, time_limit
    )
    distances = _compute_checked_distances(coordinates, weights)
    medoids = _build_medoids(distances, weights, cluster_count)

    deadline = np.inf if time_limit is None else perf_counter() + time_limit
    medoids, iterations, status = _swap_medoids(
        distances, weights, medoids, iteration_limit, deadline
    )
    sorted_medoids = np.array(sorted(medoids))
    assignments, objective = _assign_memberships(distances, weights, sorted_medoids, share_ties)

    return {
        "medoid_indices": sorted_medoids.tolist(),
        "assignment_weights": assignments.tolist(),
        "objective": objective,
        "status": status,
        "iterations": iterations,
        "runtime_seconds": perf_counter() - started,
    }


def _validate_inputs(
    coordinates: NDArray, weights: NDArray, n_clusters: int, max_iter: int, time_limit: float | None
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Normalize PAM arrays and validate their shapes, values, and search limits.

    Args:
        coordinates (NDArray): Ballot embeddings to convert to a two-dimensional float array.
        weights (NDArray): Positive ballot weights to convert to a float vector.
        n_clusters (int): Requested number of medoids.
        max_iter (int): Maximum accepted swaps.
        time_limit (float | None): Positive SWAP time limit, or None for no limit.

    Returns:
        tuple[NDArray, NDArray]: Validated coordinates and weights. Inputs are never mutated.

    Raises:
        ValueError: If shapes, numeric values, counts, or the time limit are invalid.
    """
    coordinates = np.asarray(coordinates, dtype=float)
    weights = np.asarray(weights, dtype=float)

    if coordinates.ndim != 2 or len(coordinates) == 0 or not np.isfinite(coordinates).all():
        raise ValueError("coordinates must be a nonempty, finite two-dimensional array")

    n_ballots = len(coordinates)

    if weights.shape != (n_ballots,) or not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("weights must contain one positive finite value per ballot")

    if not 1 <= n_clusters <= n_ballots:
        raise ValueError("n_clusters must be an integer between 1 and the ballot count")

    if max_iter < 0:
        raise ValueError("max_iter must be a nonnegative integer")

    if time_limit is not None and (not np.isfinite(time_limit) or time_limit <= 0):
        raise ValueError("time_limit must be positive and finite")

    return coordinates, weights


def _compute_checked_distances(coordinates: NDArray, weights: NDArray) -> NDArray:
    """Compute Manhattan distances and check that weighted costs fit in floating point.

    Args:
        coordinates (NDArray): Validated finite ballot embeddings.
        weights (NDArray): Corresponding positive finite weights.

    Returns:
        NDArray: Square, unweighted pairwise distance matrix.

    Raises:
        ValueError: If the largest distance times total weight overflows.
    """
    with np.errstate(over="ignore", invalid="ignore"):
        distances = pairwise_manhattan(coordinates)
        cost_bound = distances.max() * weights.sum()

    if not np.isfinite(cost_bound):
        raise ValueError("weighted distances exceed floating-point range")

    return distances


def _build_medoids(distances: NDArray, weights: NDArray, n_clusters: int) -> list[int]:
    """Choose medoids by deterministic weighted greedy BUILD.

    Args:
        distances (NDArray): Square pairwise distances with finite weighted costs.
        weights (NDArray): Positive weights in distance-matrix row order.
        n_clusters (int): Medoid count between one and the ballot count.

    Returns:
        list[int]: Distinct medoid indices in selection order. Equal costs prefer input order.
    """
    medoids = []
    nearest = np.full(len(weights), np.inf)

    for _ in range(n_clusters):
        candidates = [i for i in range(len(weights)) if i not in medoids]
        chosen = min(
            candidates, key=lambda i: float(weights @ np.minimum(nearest, distances[:, i]))
        )

        medoids.append(chosen)
        nearest = np.minimum(nearest, distances[:, chosen])

    return medoids


def _swap_candidates(distances: NDArray, medoids: list[int]) -> Iterator[tuple[int, int, NDArray]]:
    """Enumerate replacement candidates with distances to the medoids that would remain.

    Args:
        distances (NDArray): Square pairwise distance matrix.
        medoids (list[int]): Distinct medoid indices in selection order; not mutated.

    Yields:
        tuple[int, int, NDArray]: Medoid slot, replacement ballot, and each ballot's nearest
        remaining distance. A single-medoid replacement uses infinity for remaining distances.
        Slots precede candidate indices in iteration order, preserving deterministic ties.
    """
    to_medoids = distances[:, medoids]
    labels = to_medoids.argmin(axis=1)
    nearest = to_medoids.min(axis=1)
    second = (
        np.partition(to_medoids, 1, axis=1)[:, 1]
        if len(medoids) > 1
        else np.full(len(distances), np.inf)
    )
    candidates = [i for i in range(len(distances)) if i not in medoids]

    for slot in range(len(medoids)):
        without = np.where(labels == slot, second, nearest)

        for candidate in candidates:
            yield slot, candidate, without


def _swap_medoids(
    distances: NDArray, weights: NDArray, medoids: list[int], max_iter: int, deadline: float
) -> tuple[list[int], int, PAMStatus]:
    """Apply best-improvement swaps while respecting the iteration and wall-clock limits.

    Args:
        distances (NDArray): Square pairwise distances with finite weighted costs.
        weights (NDArray): Positive ballot weights.
        medoids (list[int]): Initial medoid indices; a copy is used for the search.
        max_iter (int): Nonnegative maximum accepted swaps.
        deadline (float): Absolute perf_counter deadline, or infinity for no time limit.

    Returns:
        tuple[list[int], int, str]: Final medoids, accepted swaps, and termination status. An
        interrupted pass discards its proposed swap and returns the last completed clustering.
    """
    medoids = list(medoids)

    for iteration in range(max_iter):
        best_cost = float(weights @ distances[:, medoids].min(axis=1))
        best_swap = None

        for slot, candidate, without in _swap_candidates(distances, medoids):
            if perf_counter() >= deadline:
                return medoids, iteration, "time_limit"

            cost = float(weights @ np.minimum(without, distances[:, candidate]))

            if cost < best_cost:
                best_cost, best_swap = cost, (slot, candidate)

        if best_swap is None:
            return medoids, iteration, "local_optimum"

        slot, candidate = best_swap
        medoids[slot] = candidate

    return medoids, max_iter, "iteration_limit"


def _assign_memberships(
    distances: NDArray, weights: NDArray, medoids: NDArray[np.integer], share_ties: bool
) -> tuple[NDArray, float]:
    """Assign ballot weights to nearest medoids without modifying the input arrays.

    Args:
        distances (NDArray): Square pairwise distance matrix.
        weights (NDArray): Positive ballot weights.
        medoids (NDArray): Medoid indices in ascending order.
        share_ties (bool): Split ties equally if True; otherwise use the first nearest medoid,
            with medoid ballots assigned to themselves.

    Returns:
        tuple[NDArray, float]: Membership weights in ballot-by-medoid order and weighted objective.
        Membership row sums equal the supplied weights.
    """
    to_medoids = distances[:, medoids]
    nearest = to_medoids.min(axis=1)

    if share_ties:
        tied = to_medoids == nearest[:, None]
        assignments = weights[:, None] * tied / tied.sum(axis=1)[:, None]
    else:
        labels = to_medoids.argmin(axis=1)
        labels[medoids] = np.arange(len(medoids))
        assignments = np.zeros((len(weights), len(medoids)))
        assignments[np.arange(len(weights)), labels] = weights

    return assignments, float(weights @ nearest)
