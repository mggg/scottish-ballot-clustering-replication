"""Exercise portable solution conversion and validation without invoking a solver."""

import json
from itertools import product
from pathlib import Path

import pytest
from click.testing import CliRunner

from analysis_scripts.convert_solution import main
from scottish_ballot_clustering.load_election import load_election
from scottish_ballot_clustering.metrics import ballot_borda_vector, ballot_hh_vector
from scottish_ballot_clustering.saved_solutions import (
    convert_sol_to_saved_solution,
    load_saved_solution,
    load_saved_solutions,
    save_solution,
)
from scottish_ballot_clustering.solution_types import EmbeddingName, ModelFamily, SavedSolution


@pytest.mark.parametrize("model", ["coordinate", "all_ballot", "cast_ballot"])
@pytest.mark.parametrize("embedding", ["borda_pessimistic", "head_to_head"])
def test_current_sol_round_trip_preserves_centers(
    tmp_path: Path, model: ModelFamily, embedding: EmbeddingName
) -> None:
    """Retain solver assignments, empty centers, and paired representations across JSON export."""
    election = tmp_path / "town.csv"
    election.write_text(
        '3,1\n4,3\n2,1,2\n"Candidate 1","Alice","P"\n'
        '"Candidate 2","Bob","P"\n"Candidate 3","Carol","P"\n"Town"\n'
    )
    ballots, weights, candidates = load_election(election)
    embed = ballot_hh_vector if embedding == "head_to_head" else ballot_borda_vector
    carol_index = ballots.index((2,))
    expected = embed(ballot=(2,), n_candidates=3).tolist()
    lines = [f"# Solution for model {model}_{embedding}", "# Objective value = 10"]
    if model == "cast_ballot":
        lines += [f"centroid_indicator[{j}] {int(j == carol_index)}" for j in range(len(ballots))]
        lines += [
            f"cluster_assignment[{center},{ballot}] {int(center == carol_index)}"
            for center, ballot in product(range(len(ballots)), repeat=2)
        ]
    else:
        # The second center is a duplicate with no assigned ballots; both slots must survive.
        lines += [
            f"ballot_j_to_cluster_r_indicator[{j},{r}] {int(r == 0)}"
            for j, r in product(range(len(ballots)), range(2))
        ]
        allowed = range(-1, 2) if embedding == "head_to_head" else range(3)
        lines += [
            f"coord_i_in_centroid_r_is_v[{i},{r},{value}] {int(value == expected[i])}"
            for i, r, value in product(range(3), range(2), allowed)
        ]

    source = tmp_path / "arbitrary_filename.sol"
    source.write_text("\n".join(lines) + "\n")
    destination = tmp_path / "centers.json"
    result = CliRunner().invoke(main, [str(source), str(election), str(destination)])
    assert result.exit_code == 0, result.output
    solution = load_saved_solution(destination)
    assert solution == {
        "election": "town",
        "candidates": candidates,
        "embedding": embedding,
        "optimization_model": model,
        "centers": [expected] * (1 if model == "cast_ballot" else 2),
        "ballot_clusters_in_coordinates": [
            [[embed(ballot=b, n_candidates=3).tolist(), int(w)] for b, w in zip(ballots, weights)]
        ]
        + ([] if model == "cast_ballot" else [[]]),
        "ballot_clusters_from_cvr": [
            [[[i + 1 for i in b], int(w)] for b, w in zip(ballots, weights)]
        ]
        + ([] if model == "cast_ballot" else [[]]),
    }
    assert load_saved_solutions(destination) == [solution]
    collection = tmp_path / "collection.json"
    collection.write_text(json.dumps([solution, solution]))
    assert load_saved_solutions(collection) == [solution, solution]
    with pytest.raises(FileExistsError):
        save_solution(solution, destination)

    incomplete = source.read_text().replace("# Objective value = 10", "# Objective value = nan")
    source.write_text(incomplete)
    with pytest.raises(ValueError):
        convert_sol_to_saved_solution(source, election)


def test_saved_json_rejects_invalid_metadata_and_coordinates(tmp_path: Path) -> None:
    """Reject malformed center metadata and repeated JSON fields."""
    solution = {
        "election": "town",
        "candidates": ["Alice", "Bob", "Carol"],
        "embedding": "borda_pessimistic",
        "optimization_model": "coordinate",
        "centers": [[2, 1, 0]],
        "ballot_clusters_in_coordinates": [[[[2, 1, 0], 2]]],
        "ballot_clusters_from_cvr": [[[[1, 2], 2]]],
    }
    path = tmp_path / "solution.json"
    path.write_text(json.dumps(solution))
    assert load_saved_solution(path) == solution
    invalid_solutions = [
        {**solution, "embedding": "borda_average"},
        {**solution, "optimization_model": "unknown"},
        {**solution, "candidates": ["Alice", "Alice", "Carol"]},
        {**solution, "election": ""},
        {**solution, "centers": []},
        {**solution, "centers": [[2, 1]]},
        {**solution, "centers": [[2, 1, 0.5]]},
        {**solution, "centers": [[2, 1, True]]},
        {**solution, "centers": [[2, 1, float("nan")]]},
        {**solution, "centers": [[2, 1, float("inf")]]},
        {**solution, "centers": [[3, 1, 0]]},
        {**solution, "embedding": "head_to_head", "candidates": ["A", "B", "C", "D"]},
        {**solution, "extra": 1},
    ]
    for invalid in invalid_solutions:
        path.write_text(json.dumps(invalid))
        with pytest.raises(ValueError):
            load_saved_solution(path)
    path.write_text(
        json.dumps(solution).replace('"election": "town"', '"election":"old","election":"town"')
    )
    with pytest.raises(ValueError, match="Repeated JSON field"):
        load_saved_solution(path)


@pytest.mark.parametrize(
    "missing_fields",
    [
        ("ballot_clusters_in_coordinates",),
        ("ballot_clusters_from_cvr",),
        ("ballot_clusters_in_coordinates", "ballot_clusters_from_cvr"),
    ],
)
def test_saved_solution_requires_both_membership_fields(
    tmp_path: Path, missing_fields: tuple[str, ...]
) -> None:
    """Reject incomplete solutions even when their center metadata is valid."""
    solution = {
        "election": "town",
        "candidates": ["Alice"],
        "embedding": "borda_pessimistic",
        "optimization_model": "coordinate",
        "centers": [[0]],
        "ballot_clusters_in_coordinates": [[[[0], 7]]],
        "ballot_clusters_from_cvr": [[[[1], 7]]],
    }
    for field in missing_fields:
        del solution[field]

    path = tmp_path / "solution.json"
    path.write_text(json.dumps(solution))
    with pytest.raises(ValueError, match="both cluster fields"):
        load_saved_solution(path)


def test_paired_clusters_preserve_ties_and_equivalent_rankings(tmp_path: Path) -> None:
    """Preserve paired memberships while rejecting mismatched weights, rankings, and coordinates."""
    from scottish_ballot_clustering.saved_solutions import validate_saved_solution

    solution: SavedSolution = {
        "election": "town",
        "candidates": ["Alice", "Bob", "Carol"],
        "embedding": "borda_pessimistic",
        "optimization_model": "coordinate",
        "centers": [[2, 1, 0], [2, 1, 0], [0, 0, 0]],
        "ballot_clusters_in_coordinates": [[[[2, 1, 0], 7]], [[[2, 1, 0], 3]], []],
        "ballot_clusters_from_cvr": [[[[1, 2], 7]], [[[1, 2, 3], 3]], []],
    }
    path = tmp_path / "clusters.json"
    save_solution(solution, path)
    assert load_saved_solution(path) == solution
    for change in ("weight", "coordinate", "id", "duplicate", "missing_cluster", "missing_field"):
        broken = json.loads(json.dumps(solution))
        if change == "weight":
            broken["ballot_clusters_from_cvr"][0][0][1] = 8
        elif change == "coordinate":
            broken["ballot_clusters_in_coordinates"][0][0][0] = [2, 0, 0]
        elif change == "id":
            broken["ballot_clusters_from_cvr"][0][0][0] = [0, 1]
        elif change == "duplicate":
            broken["ballot_clusters_from_cvr"][1][0][0] = [1, 2]
        elif change == "missing_cluster":
            broken["ballot_clusters_from_cvr"].pop()
        else:
            del broken["ballot_clusters_from_cvr"]
        with pytest.raises(ValueError):
            validate_saved_solution(broken)
