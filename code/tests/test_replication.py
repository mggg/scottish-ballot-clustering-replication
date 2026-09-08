"""Run with: uv run pytest."""

import unittest
from itertools import combinations, permutations, product
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import gurobipy as gp
import numpy as np
from click.testing import CliRunner

from scottish_ballot_clustering.extract_results import extract_solution
from scottish_ballot_clustering.load_election import load_election
from scottish_ballot_clustering.metrics import ballot_borda_vector, ballot_hh_vector, borda_distance
from scottish_ballot_clustering.run_clustering import build_model, main

ROOT = Path(__file__).resolve().parents[2]
ELECTION = ROOT / "data/scot-elex/03_cands/eilean_siar_2022_ward3.csv"


def embed(ballot: tuple[int, ...], metric: str) -> tuple[int, ...]:
    """Return an independently computed embedding for a three-candidate ballot.

    This reference calculation uses rank positions directly so exhaustive-search checks do not
    depend on the production embedding functions.

    Args:
        ballot (tuple[int, ...]): Partial ranking of distinct indices from ``{0, 1, 2}``.
        metric (str): "borda" for scores or "head_to_head" for pairwise preferences. The helper
            treats any value other than "borda" as head-to-head.

    Returns:
        tuple[int, ...]: Three coordinates, ordered by candidate for Borda or by the pairs
        ``(0, 1), (0, 2), (1, 2)`` for head-to-head.
    """
    if metric == "borda":
        return tuple(2 - ballot.index(i) if i in ballot else 0 for i in range(3))

    ranks = [ballot.index(i) if i in ballot else 3 for i in range(3)]

    return tuple(
        int(ranks[j] > ranks[i]) - int(ranks[j] < ranks[i]) for i, j in combinations(range(3), 2)
    )


def _reference_centers(ballots: list[tuple], metric: str, family: str) -> np.ndarray:
    """Enumerate allowed centers independently for a three-candidate model.

    Args:
        ballots (list[tuple]): Cast rankings using candidate indices 0, 1, and 2.
        metric (str): Borda or head_to_head embedding name.
        family (str): Cast_ballot, all_ballot, or coordinate center family, in lowercase.

    Returns:
        np.ndarray: Rows of distinct candidate centers for the exhaustive-search reference.

    Raises:
        KeyError: If family is not recognized.
    """
    possible_ballots = [b for length in range(4) for b in permutations(range(3), length)]
    centers = {
        "cast_ballot": [embed(ballot, metric) for ballot in ballots],
        "all_ballot": sorted({embed(ballot, metric) for ballot in possible_ballots}),
        "coordinate": list(product(range(3) if metric == "borda" else [-1, 0, 1], repeat=3)),
    }

    return np.array(centers[family])


class ReplicationCheck(unittest.TestCase):
    """Check model optima and result-writing behavior using a working Gurobi license."""

    def test_models_against_exhaustive_search(self) -> None:
        """Check all model families against exhaustively enumerated clustering costs.

        The weighted three-candidate profile exercises both embeddings at one, two, and three
        clusters. Centers are enumerated from independent reference embeddings, including the
        empty ballot for all-ballot models.

        Returns:
            None: Failures are recorded by unittest's subtests or raised as assertions.

        Raises:
            AssertionError: If a solve is not optimal or its objective differs from the
                exhaustive-search optimum.
            gurobipy.GurobiError: If the solver cannot initialize, construct, or solve a model.
        """
        ballots = [(0,), (1, 0), (2,), (0, 2, 1)]
        weights = np.array([5, 3, 2, 1])
        variants = product(
            ("borda", "head_to_head"), ("cast_ballot", "all_ballot", "coordinate"), (1, 2, 3)
        )
        for metric, family, k in variants:
            points = np.array([embed(ballot, metric) for ballot in ballots])
            centers = _reference_centers(ballots, metric, family)
            distances = np.abs(points[:, None, :] - centers[None, :, :]).sum(axis=2)
            expected = min(
                int(weights @ distances[:, selection].min(axis=1))
                for selection in combinations(range(len(centers)), k)
            )

            with (
                self.subTest(metric=metric, family=family, k=k),
                build_model(ballots, weights, 3, metric, family, k) as model,
            ):
                model.Params.OutputFlag = 0
                model.Params.MIPGap = 0
                model.optimize()
                self.assertEqual(model.Status, gp.GRB.OPTIMAL)
                self.assertAlmostEqual(model.ObjVal, expected)

    def test_partial_ballot_embeddings(self) -> None:
        """Check all three-candidate partial-ballot embeddings against an independent reference."""
        possible_ballots = [b for length in range(4) for b in permutations(range(3), length)]
        for metric, ballot in product(("borda", "head_to_head"), possible_ballots):
            embedding = ballot_borda_vector if metric == "borda" else ballot_hh_vector
            np.testing.assert_array_equal(
                embedding(ballot=list(ballot), n_candidates=3), embed(ballot, metric)
            )

    def test_saved_election_objectives(self) -> None:
        """Check reference election objectives across metrics and center families.

        Reference objectives cover both metrics and all center families at one, two, and three
        clusters. The Borda distance check also pins down the custom-score convention.

        Returns:
            None: Failures are recorded by unittest's subtests or raised as assertions.

        Raises:
            AssertionError: If a reference objective, solver status, or distance convention fails.
            gurobipy.GurobiError: If a directly invoked solver cannot initialize or solve.
            OSError: If election data cannot be accessed.
        """
        ballots, weights, candidates = load_election(ELECTION)

        for metric, family, k in product(
            ("borda", "head_to_head"), ("cast_ballot", "all_ballot", "coordinate"), (1, 2, 3)
        ):
            expected = {1: 1420 if metric == "head_to_head" else 1354, 2: 812, 3: 381}[k]

            if metric == "borda" and family == "coordinate" and k == 1:
                expected = 1245

            with (
                self.subTest(metric=metric, family=family, k=k),
                build_model(ballots, weights, len(candidates), metric, family, k) as model,
            ):
                model.Params.OutputFlag = 0
                model.optimize()
                self.assertEqual(model.Status, gp.GRB.OPTIMAL)
                self.assertAlmostEqual(model.ObjVal, expected)

        self.assertEqual(
            borda_distance(ballot1=[0], ballot2=[1], borda_vector=np.array([2, 1, 0])), 4
        )

    def test_solution_overwrite_and_failed_solve(self) -> None:
        """Require explicit overwrite and remove stale solutions when a replacement solve fails."""
        runner = CliRunner()

        with TemporaryDirectory() as output:
            args = [
                "coordinate",
                "--file",
                str(ELECTION),
                "--run-type",
                "borda",
                "-k",
                "1",
                "--output-dir",
                output,
                "--write-model",
            ]
            result = runner.invoke(main, args)
            self.assertEqual(result.exit_code, 0, result.output)
            solution_path = next(Path(output).rglob("*.sol"))
            model_path = next(Path(output).rglob("*.mps"))
            solution_bytes = solution_path.read_bytes()
            self.assertEqual(extract_solution(solution_path)["objective"], 1245)

            result = runner.invoke(main, args)
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(solution_path.read_bytes(), solution_bytes)

            rerun_args = [arg for arg in args if arg != "--write-model"] + ["--overwrite"]
            result = runner.invoke(main, rerun_args)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(extract_solution(solution_path)["objective"], 1245)
            self.assertFalse(model_path.exists())

            infeasible = gp.Model()
            infeasible.Params.OutputFlag = 0
            infeasible.addConstr(gp.LinExpr(0) == 1)
            model_path.write_text("old model marker")

            with patch(
                "scottish_ballot_clustering.run_clustering.build_model", return_value=infeasible
            ):
                result = runner.invoke(main, rerun_args)

            self.assertNotEqual(result.exit_code, 0)
            self.assertFalse(solution_path.exists())
            self.assertFalse(model_path.exists())

    def test_nonoptimal_incumbent_is_not_saved(self) -> None:
        """Reject unfinished solves even when Gurobi has a feasible incumbent."""
        runner = CliRunner()

        for status in (gp.GRB.TIME_LIMIT, gp.GRB.INTERRUPTED, gp.GRB.SUBOPTIMAL):
            model = MagicMock()
            model.__enter__.return_value = model
            model.Status = status
            model.SolCount = 1

            with (
                self.subTest(status=status),
                TemporaryDirectory() as output,
                patch("scottish_ballot_clustering.run_clustering.build_model", return_value=model),
            ):
                result = runner.invoke(
                    main,
                    [
                        "coordinate",
                        "--file",
                        str(ELECTION),
                        "--run-type",
                        "borda",
                        "--output-dir",
                        output,
                    ],
                )

                model.optimize.assert_called_once_with()
                model.write.assert_not_called()
                self.assertNotEqual(result.exit_code, 0)
                self.assertFalse(list(Path(output).rglob("*.sol")))


if __name__ == "__main__":
    unittest.main()
