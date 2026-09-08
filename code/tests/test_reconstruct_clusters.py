"""Check nearest-center reconstruction, ZIP reconstruction, and safe JSON replacement."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Literal

import numpy as np
import pytest

from analysis_scripts.reconstruct_clusters import (
    reconstruct_collection,
    reconstruct_solution,
    replace_json,
)
from scottish_ballot_clustering.extract_results import build_ballot_clusters
from scottish_ballot_clustering.metrics import ballot_borda_vector, ballot_hh_vector
from scottish_ballot_clustering.saved_solutions import (
    SavedSolution,
    iter_archived_solutions,
    load_saved_solution,
    save_solution_archive,
)


@pytest.mark.parametrize("embedding", ["borda_pessimistic", "head_to_head"])
def test_reconstruction_preserves_weights_rankings_and_duplicate_centers(
    embedding: Literal["borda_pessimistic", "head_to_head"],
) -> None:
    """Keep equivalent CVRs separate and assign distance ties to the first stored center."""
    ballots = [(0, 1), (0, 1, 2), (2,), (1,)]
    weights = np.array([7, 3, 2, 4], dtype=np.int64)
    embed = ballot_borda_vector if embedding == "borda_pessimistic" else ballot_hh_vector
    coordinates = np.asarray([embed(ballot=b, n_candidates=3) for b in ballots], dtype=np.int64)
    centers = [coordinates[0].tolist(), coordinates[0].tolist(), coordinates[2].tolist()]
    original: SavedSolution = {
        "election": "town",
        "candidates": ["Alice", "Bob", "Carol"],
        "embedding": embedding,
        "optimization_model": "coordinate",
        "centers": centers,
        **build_ballot_clusters(
            ballots, weights.tolist(), coordinates.tolist(), [1] * len(ballots), len(centers)
        ),
    }
    before = deepcopy(original)

    result = reconstruct_solution(original, ballots, weights, coordinates)
    assert original == before
    for key in ("election", "candidates", "embedding", "optimization_model", "centers"):
        assert result[key] == original[key]
    assert original["ballot_clusters_from_cvr"][1]
    assert result["ballot_clusters_from_cvr"][1] == []
    observed = {}
    for cluster, entries in enumerate(result["ballot_clusters_from_cvr"]):
        for ranking, weight in entries:
            assert isinstance(ranking, list)
            assert isinstance(weight, int)
            observed[tuple(candidate - 1 for candidate in ranking)] = (cluster, weight)

    for ballot, weight, point in zip(ballots, weights, coordinates):
        expected = min(
            range(len(centers)), key=lambda r: sum(abs(a - b) for a, b in zip(point, centers[r]))
        )
        assert observed[ballot] == (expected, int(weight))
    assert len(observed) == len(ballots)


@pytest.mark.parametrize("archived", [False, True])
def test_collection_preserves_solutions_and_names(tmp_path: Path, archived: bool) -> None:
    """Reconstruct loose files or ZIP members while preserving metadata, filenames, and weights."""
    elections = tmp_path / "elections"
    elections.mkdir()
    (elections / "town.csv").write_text(
        '3,1\n4,3\n2,1,2\n"Candidate 1","Alice","P"\n'
        '"Candidate 2","Bob","P"\n"Candidate 3","Carol","P"\n"Town"\n'
    )
    results = tmp_path / "results"
    results.mkdir()
    original: list[SavedSolution] = [
        SavedSolution(
            election="town",
            candidates=["Alice", "Bob", "Carol"],
            embedding="borda_pessimistic",
            optimization_model="coordinate",
            centers=[[float(value) for value in center] for center in centers],
            ballot_clusters_in_coordinates=[[[[0, 0, 2], 4], [[2, 1, 0], 2]]]
            + [[] for _ in centers[1:]],
            ballot_clusters_from_cvr=[[[[3], 4], [[1, 2], 2]]] + [[] for _ in centers[1:]],
        )
        for centers in ([[2, 1, 0]], [[2, 1, 0], [0, 0, 2]])
    ]
    names = [f"{index + 1}_clusters/3_candidates/town.json" for index in range(2)]
    archive = results / "solutions.zip"
    if archived:
        save_solution_archive(zip(names, original), archive)
    else:
        for name, solution in zip(names, original):
            path = results / name
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(solution))

    reconstruct_collection(results, elections)

    if archived:
        contents = list(iter_archived_solutions(archive))
        assert [name for name, _ in contents] == names
        individuals = [solution for _, solution in contents]
        assert list(results.iterdir()) == [archive]
    else:
        individuals = [load_saved_solution(results / name) for name in names]

    for before, after in zip(original, individuals):
        for key in ("election", "candidates", "embedding", "optimization_model", "centers"):
            assert after[key] == before[key]
        if len(after["centers"]) == 2:
            assert after["ballot_clusters_from_cvr"] == [[[[1, 2], 2]], [[[3], 4]]]
        total_weight = 0
        for cluster in after["ballot_clusters_from_cvr"]:
            for _, weight in cluster:
                assert isinstance(weight, int)
                total_weight += weight
        assert total_weight == 6


def test_failed_json_replacement_preserves_original(tmp_path: Path) -> None:
    """Keep the existing file and remove the temporary file if JSON serialization fails."""
    path = tmp_path / "solution.json"
    original = '{"unchanged": true}\n'
    path.write_text(original)
    invalid: SavedSolution = {
        "election": "town",
        "candidates": ["Alice"],
        "embedding": "borda_pessimistic",
        "optimization_model": "coordinate",
        "centers": [[float("nan")]],
        "ballot_clusters_in_coordinates": [[]],
        "ballot_clusters_from_cvr": [[]],
    }

    with pytest.raises(ValueError):
        replace_json(path, invalid)
    assert path.read_text() == original
    assert list(tmp_path.iterdir()) == [path]
