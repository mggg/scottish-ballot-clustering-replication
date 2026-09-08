"""Load Scottish CSV profiles using the same ballot ordering as VoteKit."""

from collections.abc import Sequence
from numbers import Integral
from pathlib import Path
from typing import SupportsIndex

import numpy as np
from numpy.typing import ArrayLike, NDArray
from votekit.cvr_loaders import load_scottish


def load_election(path: str | Path) -> tuple[list[tuple[int, ...]], NDArray[np.int64], list[str]]:
    """Load a Scottish election CSV as indexed rankings and integer weights.

    Args:
        path (str | Path): Path to a Scottish election CSV file.

    Returns:
        tuple[list[tuple[int, ...]], NDArray, list[str]]: Rankings, an int64 weight vector of shape
        ``(len(rankings),)``, and candidate names. A candidate index refers to its position in the
        names list; weights correspond positionally to rankings.

    Raises:
        OSError: If the CSV file cannot be opened or read.
        pandas.errors.EmptyDataError: If the local CSV file is empty.
        pandas.errors.DataError: If election metadata or candidate records are inconsistent.
        ValueError: If the path is invalid, the profile has no candidates or ballots, a ranking is
            missing or contains ties or repeated candidates, or a ballot weight is not a positive
            integer.
        KeyError: If a ballot references an undeclared candidate.
        OverflowError: If a ballot weight cannot be represented as int64.
    """
    profile, _, candidates, _, _ = load_scottish(str(path))

    if not candidates or not profile.ballots:
        raise ValueError("Election must contain candidates and ballots")

    candidate_index = {candidate: i for i, candidate in enumerate(candidates)}
    ballots = []
    weights = []

    for ballot in profile.ballots:
        if ballot.ranking is None or any(rank is None or len(rank) != 1 for rank in ballot.ranking):
            raise ValueError("Each ranked position must contain exactly one candidate")

        ranking = tuple(candidate_index[next(iter(rank))] for rank in ballot.ranking)

        if len(set(ranking)) != len(ranking):
            raise ValueError("A candidate cannot appear twice in a ballot")

        if ballot.weight <= 0 or int(ballot.weight) != ballot.weight:
            raise ValueError("Ballot weights must be positive integers")

        ballots.append(ranking)
        weights.append(int(ballot.weight))

    return ballots, np.array(weights, dtype=np.int64), list(candidates)


def validate_profile(
    ballots: Sequence[Sequence[SupportsIndex]], weights: ArrayLike, n_candidates: int
) -> NDArray[np.float64]:
    """Validate a weighted profile and return its numeric frequencies without changing ballot order.

    Args:
        ballots (Sequence[Sequence[int]]): Partial rankings of distinct zero-based candidate IDs.
        weights (ArrayLike): Finite, nonnegative frequencies, one per ballot. Fractional weights
            and empty profiles are supported for cluster summaries.
        n_candidates (int): Number of candidates in the common indexing.

    Returns:
        NDArray[np.float64]: Frequencies in input order. Inputs are not modified.

    Raises:
        ValueError: If frequencies, their total, dimensions, or rankings are invalid.
    """
    frequencies = np.asarray(weights, dtype=float)
    if (
        frequencies.shape != (len(ballots),)
        or not np.isfinite(frequencies).all()
        or (frequencies < 0).any()
    ):
        raise ValueError("Weights must be finite, nonnegative, and match the ballot count")

    for ballot in ballots:
        if any(
            not isinstance(candidate, Integral) or not 0 <= int(candidate) < n_candidates
            for candidate in ballot
        ):
            raise ValueError("Ballot candidate indices are outside the candidate list")
        if len(set(ballot)) != len(ballot):
            raise ValueError("Ballots cannot repeat candidates")

    if not np.isfinite(sum(map(float, frequencies))):
        raise ValueError("Aggregate ballot weight must be finite")

    return frequencies
