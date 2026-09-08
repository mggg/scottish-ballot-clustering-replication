"""Embed partial rankings and measure weighted clustering distances."""

from collections.abc import Sequence
from itertools import combinations
from math import comb
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class BallotDistance(Protocol):
    """Describe a ballot-distance callable with its metric parameters already bound."""

    def __call__(self, *, ballot1: Sequence[int], ballot2: Sequence[int]) -> float:
        """Measure the distance between two indexed partial rankings.

        Args:
            ballot1 (Sequence[int]): First partial ranking in preference order.
            ballot2 (Sequence[int]): Second ranking in the same candidate indexing.

        Returns:
            float: Distance under the callable's bound embedding and metric parameters.
        """
        ...


def pairwise_manhattan(
    coordinates: NDArray, other_coordinates: NDArray | None = None
) -> NDArray[np.float64]:
    """Return Manhattan distances between rows of one or two embedding arrays.

    Args:
        coordinates (NDArray): Finite numeric embeddings of shape ``(n_ballots, dimensions)``.
            The caller must validate shape and values.
        other_coordinates (NDArray | None): Finite numeric embeddings of shape
            ``(n_targets, dimensions)`` in the same coordinate system. None uses coordinates.
            The caller must validate shape and values.

    Returns:
        NDArray[np.float64]: Distance matrix of shape ``(n_ballots, n_targets)``, preserving row
        order from each input. With one input, the matrix is square and symmetric with a zero
        diagonal.
    """
    if other_coordinates is None:
        other_coordinates = coordinates

    distances = np.empty((len(coordinates), len(other_coordinates)))

    for i, point in enumerate(coordinates):
        distances[i] = np.abs(other_coordinates - point).sum(axis=1)

    return distances


def _preference_coordinate(winner: int, loser: int, n_candidates: int) -> tuple[int, int]:
    """Locate and encode one strict preference in lexicographic candidate-pair order.

    Args:
        winner (int): Preferred candidate index in 0..n_candidates-1.
        loser (int): Less-preferred candidate index, distinct from winner.
        n_candidates (int): Total candidate count. Indices are assumed valid and not checked.

    Returns:
        tuple[int, int]: Coordinate index and sign. A win by the lower-indexed candidate is 1;
        a win by the higher-indexed candidate is -1.
    """
    first, second = sorted((winner, loser))
    index = first * (2 * n_candidates - first - 1) // 2 + second - first - 1

    return index, 1 if winner < loser else -1


def ballot_hh_vector(*, ballot: Sequence[int], n_candidates: int) -> NDArray[np.float64]:
    """Return the head-to-head embedding of a partial ranking.

    Coordinates follow lexicographic candidate-pair order: ``(0, 1), (0, 2), ...``. For a pair
    ``(i, j)``, the value is 1 when i is preferred to j, -1 when j is preferred to i, and 0 when
    both are unranked. Every ranked candidate is preferred to every unranked candidate. An empty
    ballot produces an all-zero vector.

    Args:
        ballot (Sequence[int]): Candidate indices in preference order, best first. Indices must be
            distinct and lie in ``0..n_candidates-1``; this is not validated.
        n_candidates (int): Nonnegative total number of candidates, including those absent from the
            ballot.

    Returns:
        NDArray: A new float vector of shape ``(n_candidates * (n_candidates - 1) // 2,)``, with
        values in ``{-1, 0, 1}``.

    Raises:
        ValueError: If n_candidates is negative.
    """
    hh_vector = np.zeros(comb(n_candidates, 2))
    not_on_ballot = set(range(n_candidates)) - set(ballot)

    for winner, loser in combinations(ballot, 2):
        index, value = _preference_coordinate(winner, loser, n_candidates)
        hh_vector[index] = value

    for winner in ballot:
        for candidate in not_on_ballot:
            index, value = _preference_coordinate(winner, candidate, n_candidates)
            hh_vector[index] = value

    return hh_vector


def ballot_borda_vector(
    *, ballot: Sequence[int], n_candidates: int, borda_vector: NDArray | None = None
) -> NDArray:
    """Return candidate scores for a partial ranking.

    Scores are assigned by rank, with the first score going to the most-preferred candidate.
    Unranked candidates receive zero. The default scores are pessimistic Borda scores
    ``n_candidates-1, ..., 0``; no points are shared among omitted candidates.

    Args:
        ballot (Sequence[int]): Distinct candidate indices, best first. Indices must lie in
            ``0..n_candidates-1``; their validity is not checked.
        n_candidates (int): Nonnegative total number of candidates.
        borda_vector (NDArray | None): One-dimensional scores in rank order. If supplied, its length
            must be at least the ballot length and at most n_candidates. None selects the default
            pessimistic Borda scores.

    Returns:
        NDArray: A new float vector of shape ``(n_candidates,)``, indexed by candidate.

    Raises:
        ValueError: If the ballot or scoring vector is longer than n_candidates, or n_candidates is
            negative.
        IndexError: If the scoring vector is shorter than the ballot or a candidate index is outside
            NumPy's valid index range.
    """
    if borda_vector is None:
        borda_vector = np.arange(n_candidates - 1, -1, -1)

    if len(borda_vector) > n_candidates:
        raise ValueError("borda_vector is longer than number of candidates")

    if len(ballot) > n_candidates:
        raise ValueError("ballot is longer than number of candidates")

    ballot_vector = np.zeros(n_candidates)

    for idx, candidate in enumerate(ballot):
        ballot_vector[candidate] = borda_vector[idx]

    return ballot_vector


def hh_distance(
    *,
    ballot1: Sequence[int],
    ballot2: Sequence[int],
    n_candidates: int,
) -> float:
    """Return the Manhattan distance between two head-to-head embeddings.

    Args:
        ballot1 (Sequence[int]): First partial ranking, using distinct zero-based candidate indices
            in preference order.
        ballot2 (Sequence[int]): Second partial ranking using the same candidate indexing.
        n_candidates (int): Total number of candidates, including unranked candidates.

    Returns:
        float: Sum of the absolute coordinate differences between the embeddings.

    Raises:
        TypeError: If n_candidates is not an integer.
        ValueError: If n_candidates is negative.
    """
    hh_vector1 = ballot_hh_vector(ballot=ballot1, n_candidates=n_candidates)
    hh_vector2 = ballot_hh_vector(ballot=ballot2, n_candidates=n_candidates)

    return float(np.linalg.norm(hh_vector1 - hh_vector2, ord=1))


def borda_distance(
    *,
    ballot1: Sequence[int],
    ballot2: Sequence[int],
    borda_vector: NDArray | None = None,
    n_candidates: int | None = None,
) -> float:
    """Return the Manhattan distance between two Borda score vectors.

    Supply exactly one of n_candidates and borda_vector. A candidate count selects pessimistic Borda
    scores; a custom scoring vector also determines the candidate count through its length. Unranked
    candidates receive zero in both cases.

    Args:
        ballot1 (Sequence[int]): First partial ranking, using distinct zero-based candidate indices
            in preference order.
        ballot2 (Sequence[int]): Second partial ranking using the same candidate indexing.
        borda_vector (NDArray | None): One-dimensional scores in rank order, or None to use
            n_candidates and the default scores.
        n_candidates (int | None): Nonnegative candidate count for default scoring, or None when a
            custom scoring vector is supplied.

    Returns:
        float: Sum of the absolute differences between corresponding candidate scores.

    Raises:
        ValueError: If both scoring arguments are supplied, neither is supplied, n_candidates is
            negative, or a ballot exceeds the candidate count.
        IndexError: If a candidate index is outside NumPy's valid index range.
    """
    if borda_vector is not None:
        if n_candidates is not None:
            raise ValueError("Both borda_vector and n_candidates cannot be provided")

        n_candidates = len(borda_vector)
    elif n_candidates is None:
        raise ValueError("Either borda_vector or n_candidates must be provided")

    ballot1_vector = ballot_borda_vector(
        ballot=ballot1, n_candidates=n_candidates, borda_vector=borda_vector
    )
    ballot2_vector = ballot_borda_vector(
        ballot=ballot2, n_candidates=n_candidates, borda_vector=borda_vector
    )

    return float(np.linalg.norm(ballot1_vector - ballot2_vector, ord=1))


def compute_cluster_cost(
    *,
    cluster_set: frozenset[int],
    centroid_idx: int,
    ballot_list: list[tuple[int, ...]],
    weight_vector: NDArray,
    distance_function: BallotDistance,
) -> float:
    """Return a cluster's weighted distance to a specified cast ballot.

    The centroid is identified by its position in ballot_list, not by a coordinate vector. The
    distance function must already have any required metric parameters, such as candidate count,
    bound.

    Args:
        cluster_set (frozenset[int]): Indices of the ballots assigned to the cluster.
        centroid_idx (int): Index of the representative ballot in ballot_list.
        ballot_list (list[tuple[int, ...]]): Rankings in a common candidate indexing.
        weight_vector (NDArray): Nonnegative ballot weights of shape ``(len(ballot_list),)`` in the
            same order as ballot_list.
        distance_function (BallotDistance): Callable accepting ballot1 and ballot2 as keywords and
            returning their distance. Its exceptions propagate.

    Returns:
        float: Sum of weight times distance for cluster members, or 0.0 for an empty cluster.

    Raises:
        IndexError: If an accessed ballot or weight index is outside its sequence's range.
    """
    cluster_cost = 0

    for ballot_idx in cluster_set:
        cluster_cost += (
            distance_function(
                ballot1=ballot_list[ballot_idx],
                ballot2=ballot_list[centroid_idx],
            )
            * weight_vector[ballot_idx]
        )

    return float(cluster_cost)
