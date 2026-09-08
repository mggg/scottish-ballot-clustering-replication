"""Summarize weighted election profiles and reconstructed ballot clusters."""

from collections.abc import Iterable, Sequence
from numbers import Integral
from typing import Literal, SupportsIndex, TypedDict

import numpy as np
from numpy.typing import ArrayLike

from .load_election import validate_profile
from .solution_types import BallotCluster


class RankingFrequency(TypedDict):
    """One distinct zero-based ranking and its combined voter weight."""

    ranking: list[int]
    weight: float


class ElectionSummary(TypedDict):
    """Weighted election statistics in the supplied candidate indexing."""

    candidates: list[str]
    n_candidates: int
    total_weight: float
    n_distinct_ballots: int
    mean_ballot_length: float | None
    weight_by_ballot_length: list[float]
    first_preference_weights: list[float]
    most_common_ballots: list[RankingFrequency]


class ClusterSummary(ElectionSummary):
    """Election statistics for one cluster, retaining its original center and label."""

    cluster_index: int
    center_kind: Literal["ranking", "coordinates"]
    center: list[int]


def summarize_election(
    ballots: Sequence[Sequence[SupportsIndex]],
    weights: ArrayLike,
    candidates: Sequence[str],
    *,
    top_n: int = 10,
) -> ElectionSummary:
    """Summarize a weighted profile without expanding ballot frequencies.

    Duplicate rankings are combined and zero-weight rows are ignored. Fractional weights are
    supported for clusters that split tied ballots. Empty profiles have zero counts and an undefined
    mean ballot length, represented by None. Candidate indexing always follows candidates, including
    candidates absent from every ranking.

    Args:
        ballots (Sequence): Partial rankings of distinct zero-based candidate indices.
        weights (ArrayLike): Finite, nonnegative weights, one per ballot.
        candidates (Sequence[str]): Candidate labels in index order.
        top_n (int): Nonnegative maximum number of common rankings to return, default 10.

    Returns:
        dict: Candidate labels and count, total weight, distinct positive-weight ballot count,
        weighted mean ballot length, weight by ballot length, first-preference weights in candidate
        order, and most_common_ballots. Common ballots contain ranking and weight fields, ordered
        by decreasing weight with lexicographic rankings breaking ties. Empty rankings contribute
        to total weight and length statistics but have no first preference.

    Raises:
        ValueError: If weights, rankings, or top_n are invalid, dimensions disagree, or aggregate
            weight is not finite.
    """
    if not isinstance(top_n, Integral) or top_n < 0:
        raise ValueError("top_n must be a nonnegative integer")

    counts = _count_rankings(ballots, weights, len(candidates))
    total = sum(counts.values())

    if not np.isfinite(total):
        raise ValueError("Aggregate ballot weight must be finite")

    lengths = [0.0] * (len(candidates) + 1)
    first = [0.0] * len(candidates)

    for ranking, weight in counts.items():
        lengths[len(ranking)] += weight
        if ranking:
            first[ranking[0]] += weight

    return {
        "candidates": list(candidates),
        "n_candidates": len(candidates),
        "total_weight": total,
        "n_distinct_ballots": len(counts),
        "mean_ballot_length": sum(i * (weight / total) for i, weight in enumerate(lengths))
        if total
        else None,
        "weight_by_ballot_length": lengths,
        "first_preference_weights": first,
        "most_common_ballots": [
            {"ranking": list(ranking), "weight": weight}
            for ranking, weight in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[
                :top_n
            ]
        ],
    }


def _count_rankings(
    ballots: Sequence[Sequence[SupportsIndex]], weights: ArrayLike, n_candidates: int
) -> dict[tuple[int, ...], float]:
    """Validate a profile and combine the weights of duplicate rankings.

    Args:
        ballots (Sequence): Partial rankings of distinct zero-based candidate indices.
        weights (ArrayLike): Finite nonnegative frequencies, one per ballot.
        n_candidates (int): Number of candidates in the shared indexing.

    Returns:
        dict[tuple[int, ...], float]: Rankings mapped to positive aggregate weights. Zero-weight
        rows are validated but omitted; input sequences are not modified.

    Raises:
        ValueError: If weight dimensions or values are invalid, or a ranking repeats a candidate
            or contains an invalid index.
    """
    frequencies = validate_profile(ballots, weights, n_candidates)
    counts: dict[tuple[int, ...], float] = {}

    for ballot, weight in zip(ballots, frequencies):
        if weight:
            ranking = tuple(map(int, ballot))
            counts[ranking] = counts.get(ranking, 0.0) + float(weight)

    return counts


def summarize_clusters(
    clusters: Iterable[BallotCluster], *, top_n: int = 10
) -> list[ClusterSummary]:
    """Summarize each reconstructed cluster, preserving empty clusters and center order.

    Args:
        clusters (Iterable[BallotCluster]): Cluster dictionaries returned by rebuild_clusters.
            Weighted profiles with the same fields may also contain fractional membership weights.
        top_n (int): Nonnegative maximum common rankings per cluster, default 10.

    Returns:
        list[dict]: Election statistics for each cluster, together with its cluster_index,
        center_kind, and center. Counts and mean lengths use that cluster's membership weights.

    Raises:
        KeyError: If a cluster lacks required profile or center fields.
        ValueError: If a cluster profile or top_n fails summarize_election's validation.
    """
    return [
        {
            **summarize_election(
                cluster["ballots"], cluster["weights"], cluster["candidates"], top_n=top_n
            ),
            "cluster_index": cluster["cluster_index"],
            "center_kind": cluster["center_kind"],
            "center": cluster["center"],
        }
        for cluster in clusters
    ]
