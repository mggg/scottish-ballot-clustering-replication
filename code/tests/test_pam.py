"""Check weighted PAM, tie handling, termination, and command-line integration."""

import json
import unittest
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

import numpy as np
from click.testing import CliRunner

from scottish_ballot_clustering.load_election import load_election
from scottish_ballot_clustering.pam import pam
from scottish_ballot_clustering.run_clustering import main


class IndexTwo:
    """Supply an exact integer through __index__ without inheriting from an integer class."""

    def __index__(self) -> int:
        """Return the fixture's exact count.

        Returns:
            int: Two.
        """
        return 2


class PamCheck(unittest.TestCase):
    """Verify heuristic clustering behavior without creating a Gurobi model."""

    def test_weighted_build_and_swap(self) -> None:
        """Check weighted improvements, feasible assignments, and one-swap local optimality.

        The six-point fixture requires a SWAP after BUILD. Candidate swaps are independently
        enumerated to check local optimality; integer weights are also expanded into repeated rows
        to check the weighted objective.

        Returns:
            None: Assertions report violations of the clustering or termination contract.

        Raises:
            AssertionError: If the objective, assignments, local optimality, or status is incorrect.
        """
        points = np.array([[9, 17], [28, 27], [14, 6], [7, 25], [17, 5], [26, 28]])
        weights = np.array([9, 6, 9, 6, 5, 9])
        points.setflags(write=False)
        weights.setflags(write=False)

        built = pam(points, weights, 2, max_iter=0)
        result = pam(points, weights, 2)
        self.assertEqual(built["objective"], 322)
        self.assertEqual(result["objective"], 314)
        self.assertEqual(result["medoid_indices"], [2, 5])
        self.assertEqual(result["iterations"], 1)
        self.assertEqual(result["status"], "local_optimum")
        distances = np.array([[sum(abs(a - b)) for b in points] for a in points])
        medoids = result["medoid_indices"]

        for slot in range(2):
            for candidate in set(range(len(points))) - set(medoids):
                changed = medoids.copy()
                changed[slot] = candidate
                self.assertGreaterEqual(weights @ distances[:, changed].min(axis=1), 314)

        repeated = np.repeat(points, weights, axis=0)
        expanded_cost = sum(min(sum(abs(point - points[i])) for i in medoids) for point in repeated)
        self.assertEqual(expanded_cost, result["objective"])
        np.testing.assert_allclose(np.array(result["assignment_weights"]).sum(axis=1), weights)

    def test_search_limits(self) -> None:
        """Stop at an iteration or time limit without applying an unfinished swap pass."""
        points = np.array([[9, 17], [28, 27], [14, 6], [7, 25], [17, 5], [26, 28]])
        weights = np.array([9, 6, 9, 6, 5, 9])
        built = pam(points, weights, 2, max_iter=0)
        self.assertEqual(pam(points, weights, 2, max_iter=1)["status"], "iteration_limit")
        self.assertIs(type(pam(points, weights, 2, max_iter=np.int64(1))["iterations"]), int)

        with patch("scottish_ballot_clustering.pam.perf_counter", side_effect=[0, 0, 1, 1]):
            limited = pam(points, weights, 2, time_limit=0.5)

        self.assertEqual(limited["status"], "time_limit")
        self.assertEqual(limited["medoid_indices"], built["medoid_indices"])

    def test_ties_and_boundary_cluster_counts(self) -> None:
        """Preserve tied weight and attain the optimum at the boundary cluster counts."""
        points = np.array([[9, 17], [28, 27], [14, 6], [7, 25], [17, 5], [26, 28]])
        weights = np.array([9, 6, 9, 6, 5, 9])
        distances = np.array([[sum(abs(a - b)) for b in points] for a in points])
        one = pam(np.array([[0], [10], [11]]), np.array([100, 1, 1]), 1)
        self.assertEqual(one["medoid_indices"], [0])
        self.assertEqual(one["objective"], 21)

        for k in (1, len(points)):
            answer = pam(points, weights, k)
            optimum = min(
                weights @ distances[:, choice].min(axis=1)
                for choice in combinations(range(len(points)), k)
            )
            self.assertEqual(answer["objective"], optimum)

        tied = pam(np.array([[0], [1], [2]]), np.array([10, 1, 10]), 2)
        self.assertEqual(tied["medoid_indices"], [0, 2])
        self.assertEqual(tied["assignment_weights"], [[10, 0], [0.5, 0.5], [0, 10]])
        duplicates = pam(np.zeros((3, 1)), np.ones(3), 3, share_ties=False)
        np.testing.assert_array_equal(duplicates["assignment_weights"], np.eye(3))

    def test_index_protocol_counts(self) -> None:
        """Accept exact integer-like counts and reject coercions that would truncate or parse."""
        points = np.array([[0], [1], [2]])
        weights = np.array([10, 1, 10])
        expected = pam(points, weights, 2, max_iter=2)

        for count in (2, np.int64(2), np.uint64(2), IndexTwo()):
            result = pam(points, weights, count, max_iter=count)
            for field in (
                "medoid_indices",
                "assignment_weights",
                "objective",
                "status",
                "iterations",
            ):
                self.assertEqual(result[field], expected[field])

            self.assertIs(type(result["iterations"]), int)

        for count in (2.0, 2.5, "2", np.float64(2.0)):
            self.assertRaises(ValueError, pam, points, weights, count)
            self.assertRaises(ValueError, pam, points, weights, 2, max_iter=count)

    def test_invalid_inputs(self) -> None:
        """Reject invalid search limits, weights, coordinates, and weighted-cost overflow."""
        points = np.array([[9, 17], [28, 27], [14, 6], [7, 25], [17, 5], [26, 28]])
        weights = np.array([9, 6, 9, 6, 5, 9])

        for n_clusters in (0, 7):
            with self.assertRaises(ValueError):
                pam(points, weights, n_clusters=n_clusters)

        with self.assertRaises(ValueError):
            pam(points, weights, max_iter=-1)

        with self.assertRaises(ValueError):
            pam(points, weights, time_limit=float("inf"))

        for invalid in (np.ones(2), np.zeros(6), np.full(6, np.nan)):
            with self.assertRaises(ValueError):
                pam(points, invalid)

        for invalid_points in (
            np.array([1, 2]),
            np.array([[np.inf], [0]]),
            np.array([[1e308], [-1e308]]),
        ):
            with self.assertRaises(ValueError):
                pam(invalid_points, np.ones(2), 1)

    def test_pam_cli_both_metrics_without_gurobi(self) -> None:
        """Check PAM's weighted results for both embeddings without a solver license.

        Both embeddings run with Gurobi model construction disabled to ensure the heuristic does
        not require a solver license. Assignment weights are checked against input frequencies.

        Returns:
            None: CLI failures or invalid outputs are reported as assertions.

        Raises:
            AssertionError: If a command fails, uses Gurobi, or violates its output contract.
            OSError: If election data cannot be read.
        """
        election = (
            Path(__file__).resolve().parents[2]
            / "data/scot-elex/03_cands/eilean_siar_2022_ward3.csv"
        )
        runner = CliRunner()

        with patch(
            "scottish_ballot_clustering.run_clustering.gp.Model",
            side_effect=AssertionError("Gurobi used"),
        ):
            for metric in ("borda", "head_to_head"):
                args = [
                    "pam",
                    "--file",
                    str(election),
                    "--run-type",
                    metric,
                    "-k",
                    "2",
                ]
                result = runner.invoke(main, args)
                self.assertEqual(result.exit_code, 0, result.output)
                summary = json.loads(result.output)
                self.assertEqual(summary["status"], "local_optimum")
                self.assertEqual(len(summary["medoid_indices"]), 2)
                self.assertGreaterEqual(summary["objective"], 812)
                np.testing.assert_allclose(
                    np.array(summary["assignment_weights"]).sum(axis=1), load_election(election)[1]
                )


if __name__ == "__main__":
    unittest.main()
