"""Check saved warm-start identity and preserve stored memberships independently of ballot order."""

import json
from pathlib import Path

import numpy as np
import pytest

from scottish_ballot_clustering.extract_results import build_ballot_clusters
from scottish_ballot_clustering.metrics import ballot_borda_vector, ballot_hh_vector
from scottish_ballot_clustering.saved_solutions import save_solution
from scottish_ballot_clustering.solution_types import EmbeddingName, SavedSolution
from scottish_ballot_clustering.warm_start import load_starting_assignments


def build_tied_solution(embedding: EmbeddingName) -> SavedSolution:
    """Build a partition with two distinct medoid rankings that have identical embeddings."""
    ballots = [(0, 1), (0, 1, 2), (1,)]
    embed = ballot_borda_vector if embedding == "borda_pessimistic" else ballot_hh_vector
    coordinates = [embed(ballot=ballot, n_candidates=3).tolist() for ballot in ballots]
    assert coordinates[0] == coordinates[1]

    return {
        "election": "town",
        "candidates": ["Alice", "Bob", "Carol"],
        "embedding": embedding,
        "optimization_model": "cast_ballot",
        "centers": coordinates[:2],
        **build_ballot_clusters(ballots, [3, 2, 1], coordinates, [0, 1, 1], 2),
    }


@pytest.mark.parametrize("embedding", ["borda_pessimistic", "head_to_head"])
def test_saved_start_preserves_ties_and_matches_reordered_ballots(
    tmp_path: Path, embedding: EmbeddingName
) -> None:
    """Use stored memberships even when every ballot is equally near both centers."""
    solution = build_tied_solution(embedding)
    path = tmp_path / "start.json"
    save_solution(solution, path)
    before = path.read_bytes()
    run_type = "borda" if embedding == "borda_pessimistic" else "head_to_head"

    assignments = load_starting_assignments(
        path,
        [(1,), (0, 1), (0, 1, 2)],
        np.array([1, 3, 2]),
        solution["candidates"],
        run_type,
        2,
    )

    assert assignments == [1, 0, 1]
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    ["candidates", "metric", "model", "clusters", "weight", "missing", "extra", "duplicate"],
)
def test_saved_start_rejects_mismatched_metadata_and_ballots(tmp_path: Path, change: str) -> None:
    """Reject unrelated profiles and incompatible source metadata before a model is prepared."""
    solution = build_tied_solution("borda_pessimistic")
    ballots = [(0, 1), (0, 1, 2), (1,)]
    weights = [3, 2, 1]
    candidates = solution["candidates"].copy()
    run_type, n_clusters = "borda", 2

    match change:
        case "candidates":
            candidates.reverse()
        case "metric":
            run_type = "head_to_head"
        case "model":
            solution["optimization_model"] = "coordinate"
        case "clusters":
            n_clusters = 3
        case "weight":
            weights[0] += 1
        case "missing":
            ballots.pop()
            weights.pop()
        case "extra":
            ballots.append((2,))
            weights.append(1)
        case "duplicate":
            ballots.append(ballots[0])
            weights.append(weights[0])

    path = tmp_path / "start.json"
    path.write_text(json.dumps(solution), encoding="utf-8")
    with pytest.raises(ValueError):
        load_starting_assignments(
            path, ballots, np.array(weights), candidates, run_type, n_clusters
        )
