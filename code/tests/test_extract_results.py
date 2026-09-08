"""Check SOL extraction, weighted reconstruction, CSV export, and profile summaries."""

import csv
import json
import tempfile
import unittest
from itertools import product
from pathlib import Path

import numpy as np

from scottish_ballot_clustering.extract_results import (
    extract_solution,
    rebuild_clusters,
    solutions_to_csv,
    validate_solution_profile,
)
from scottish_ballot_clustering.metrics import ballot_borda_vector, ballot_hh_vector
from scottish_ballot_clustering.run_clustering import build_model
from scottish_ballot_clustering.solution_types import BallotCluster, ExtractedSolution
from scottish_ballot_clustering.summarize_profiles import summarize_clusters, summarize_election


def _solve_fixture(path: Path, family: str, metric: str) -> tuple[ExtractedSolution, dict]:
    """Solve and extract a small weighted profile using the requested IP variant.

    Args:
        path (Path): Temporary SOL destination.
        family (str): IP model family.
        metric (str): Borda or head_to_head embedding name.

    Returns:
        tuple[dict, dict]: Extracted solution and matching profile metadata with solver objective.

    Raises:
        gurobipy.GurobiError: If model creation, solving, or writing fails.
        ValueError: If extraction rejects the written solution.
        OSError: If the SOL cannot be read.
    """
    ballots = [(0, 1, 2), (1, 2), (2, 0), (0,)]
    weights = np.array([5, 3, 2, 1])

    with build_model(ballots, weights, 3, metric, family, 2) as model:
        model.Params.OutputFlag = 0
        model.optimize()
        model.write(str(path))
        objective = model.ObjVal

    metadata = {
        "ballots": ballots,
        "weights": weights,
        "candidates": ["A", "B", "C"],
        "n_clusters": 2,
        "opt_type": family,
        "run_type": metric,
        "objective": objective,
    }

    return extract_solution(path), metadata


def _cluster_cost(clusters: list[BallotCluster], metric: str) -> float:
    """Recompute weighted Manhattan costs from reconstructed cluster members.

    Args:
        clusters (list[dict]): Reconstructed clusters with rankings, weights, and centers.
        metric (str): Borda or head_to_head embedding name for the three-candidate fixture.

    Returns:
        float: Total weighted distance, independently of the SOL's reported objective.
    """
    embedding = ballot_borda_vector if metric == "borda" else ballot_hh_vector
    cost = 0.0

    for cluster in clusters:
        center = np.asarray(cluster["center"], dtype=float)

        if cluster["center_kind"] == "ranking":
            center = embedding(ballot=cluster["center"], n_candidates=3)

        for ballot, weight in zip(cluster["ballots"], cluster["weights"]):
            coordinates = embedding(ballot=ballot, n_candidates=3)
            cost += weight * np.abs(coordinates - center).sum()

    return float(cost)


class ResultTests(unittest.TestCase):
    """Verify result processing against solver output and malformed text fixtures."""

    def test_solver_round_trip(self) -> None:
        """Recover all six model families and independently recompute their weighted objectives."""
        solutions = []
        variants = product(("cast_ballot", "coordinate", "all_ballot"), ("borda", "head_to_head"))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            for family, metric in variants:
                with self.subTest(family=family, metric=metric):
                    solution, metadata = _solve_fixture(
                        root / f"{family}_{metric}.sol", family, metric
                    )
                    solutions.append(solution)
                    clusters = rebuild_clusters(
                        solution, metadata["ballots"], metadata["weights"], metadata["candidates"]
                    )

                    self.assertAlmostEqual(_cluster_cost(clusters, metric), metadata["objective"])
                    self.assertAlmostEqual(solution["objective"], metadata["objective"])
                    self.assertEqual(
                        sum(s["total_weight"] for s in summarize_clusters(clusters)), 11
                    )
                    self.assertEqual(
                        sorted(j for c in clusters for j in c["ballot_indices"]), list(range(4))
                    )

                    with self.assertRaises(ValueError):
                        rebuild_clusters(
                            solution,
                            metadata["ballots"][:-1],
                            metadata["weights"][:-1],
                            metadata["candidates"],
                        )

            destination = root / "solutions.csv"
            self.assertEqual(solutions_to_csv(iter(solutions), destination), 6)

            with destination.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))

            for row, solution in zip(rows, solutions):
                self.assertEqual(json.loads(row["centers"]), solution["centers"])
                self.assertEqual(json.loads(row["assignments"]), solution["assignments"])

            with self.assertRaises(FileExistsError):
                solutions_to_csv(solutions, destination)

    def test_empty_clusters_and_invalid_files(self) -> None:
        """Preserve empty clusters, accept numeric tolerances, and reject broken indicators."""
        text = """# Solution for model coordinate_borda_pessimistic
# Objective value = 0e+00

ballot_j_to_cluster_r_indicator[0,0] -0
ballot_j_to_cluster_r_indicator[0,1] 9.99999999e-1
coord_i_in_centroid_r_is_v[0,0,0] 1
coord_i_in_centroid_r_is_v[0,1,0] 1
"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solution.sol"
            path.write_text(text)
            solution = extract_solution(path)
            clusters = rebuild_clusters(solution, [[0]], [2], ["A"])
            self.assertEqual(clusters[0]["ballots"], [])
            self.assertEqual(summarize_clusters(clusters)[0]["mean_ballot_length"], None)

            for invalid in (
                text.replace("9.99999999e-1", "0.5"),
                text.replace("9.99999999e-1", "nan"),
                text.replace("[0,0] -0", "[0,0] 1"),
                text.replace("coord_i_in_centroid_r_is_v[0,1,0] 1", ""),
                text + "ballot_j_to_cluster_r_indicator[0,0] 0\n",
                text.replace("# Objective value = 0e+00", "# Objective value = inf"),
                text.replace("coordinate_borda_pessimistic", "unknown"),
            ):
                with self.subTest(invalid=invalid):
                    path.write_text(invalid)

                    with self.assertRaises(ValueError):
                        extract_solution(path)

    def test_weighted_summaries(self) -> None:
        """Aggregate duplicates and fractional weights while retaining unranked candidates."""
        result = summarize_election(
            [(0,), (0,), (), (1, 0), (1,)], [2, 0.5, 1, 1.5, 0], ["A", "B", "C"], top_n=2
        )
        numpy_result = summarize_election(
            [(np.int64(0),), (np.int64(0),), (), (np.int64(1), np.int64(0)), (np.int64(1),)],
            np.array([2, 0.5, 1, 1.5, 0]),
            ["A", "B", "C"],
            top_n=2,
        )
        self.assertEqual(numpy_result, result)

        self.assertEqual(result["n_candidates"], 3)
        self.assertEqual(result["n_distinct_ballots"], 3)
        self.assertEqual(result["total_weight"], 5)
        self.assertEqual(result["mean_ballot_length"], 1.1)
        self.assertEqual(result["first_preference_weights"], [2.5, 1.5, 0])
        self.assertEqual(result["most_common_ballots"][0], {"ranking": [0], "weight": 2.5})
        self.assertIsNone(summarize_election([], [], ["A"])["mean_ballot_length"])

        for ballots, weights in [
            ([(0, 0)], [1]),
            ([(3,)], [1]),
            ([(0,)], [-1]),
            ([(0,)], [float("nan")]),
            ([(0,)], []),
        ]:
            with self.assertRaises(ValueError):
                summarize_election(ballots, weights, ["A"])

    def test_profile_checks_apply_to_empty_clusters_and_zero_weight_ballots(self) -> None:
        """Share profile checks without discarding malformed rankings whose frequency is zero."""
        solution: ExtractedSolution = {
            "source": "fixture.sol",
            "model": "coordinate_borda_pessimistic",
            "objective": 0.0,
            "center_kind": "coordinates",
            "centers": [[0]],
            "assignments": [0],
        }
        for ranking in ((0, 0), (1,)):
            with self.subTest(ranking=ranking), self.assertRaises(ValueError):
                validate_solution_profile(solution, [ranking], [0], ["A"])

        validate_solution_profile(solution, [(0,)], [0], ["A"])
        clusters = rebuild_clusters(solution, [(0,)], [0], ["A"])
        summary = summarize_clusters(clusters)[0]
        self.assertEqual(summary["total_weight"], 0)
        self.assertIsNone(summary["mean_ballot_length"])


if __name__ == "__main__":
    unittest.main()
